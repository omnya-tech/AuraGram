"""What the eyes get: pictures on the buttons and tabs, chat rows coloured by kind, and chat photos."""
import os
import tempfile
import unittest
from unittest import mock

import wx
from telethon.tl import types

import core.constants as c
import core.settings as s
import ui.chat_list
import ui.main_frame
from tests.harness import FakeTelegramClient, WindowTestCase, get_app, make_channel, make_user, pump
from ui import avatars, icons, themes
from ui.chat_rows import ChatRows

HAS_ICON_FONT = unittest.skipUnless(
    (get_app() and icons.available()), "no Windows icon font on this computer"
)


def with_photo(entity, photo_id):
    entity.photo = types.UserProfilePhoto(photo_id=photo_id, dc_id=2) if isinstance(entity, types.User) \
        else types.ChatPhoto(photo_id=photo_id, dc_id=2)
    return entity


class IconTest(unittest.TestCase):
    def setUp(self):
        get_app()

    @HAS_ICON_FONT
    def test_every_icon_is_drawn_and_shows_something(self):
        for name in icons.GLYPHS:
            bitmap = icons.draw(name, 16, wx.BLACK)
            self.assertEqual(bitmap.GetSize(), wx.Size(16, 16), name)
            alpha = bitmap.ConvertToImage().GetAlpha()
            self.assertTrue(any(alpha), "%s came out empty" % name)

    @HAS_ICON_FONT
    def test_a_picture_pointing_a_way_is_turned_in_a_right_to_left_window(self):
        frame = wx.Frame(None)
        self.addCleanup(frame.Destroy)
        frame.SetLayoutDirection(wx.Layout_RightToLeft)
        button = wx.Button(frame, label="send")
        icons.put_on(button, "send")
        drawn = button.GetBitmap().ConvertToImage()
        turned = icons.draw("send", button.FromDIP(icons.ICON_SIZE), icons.icon_colour()).ConvertToImage().Mirror()
        self.assertEqual(bytes(drawn.GetAlpha()), bytes(turned.GetAlpha()))
        # A search glass points nowhere: the same either way.
        icons.put_on(button, "search")
        plain = icons.draw("search", button.FromDIP(icons.ICON_SIZE), icons.icon_colour()).ConvertToImage()
        self.assertEqual(bytes(button.GetBitmap().ConvertToImage().GetAlpha()), bytes(plain.GetAlpha()))

    def test_without_the_font_buttons_keep_their_words_alone(self):
        frame = wx.Frame(None)
        self.addCleanup(frame.Destroy)
        button = wx.Button(frame, label="Send")
        with mock.patch.object(icons, "font_name", lambda: None):
            icons.put_on(button, "send")
        self.assertFalse(button.GetBitmap().IsOk())
        self.assertEqual(button.GetLabel(), "Send")


class KindColourTest(unittest.TestCase):
    def setUp(self):
        get_app()
        self.addCleanup(themes.set_theme, c.THEME_SYSTEM)

    def test_every_kind_colour_is_easy_to_read_in_every_theme(self):
        for theme in c.THEMES:
            themes.set_theme(theme)
            for category in (c.CATEGORY_BROADCASTS, c.CATEGORY_GROUPS, c.CATEGORY_BOTS):
                colour = themes.kind_colour(category)
                ratio = themes.contrast_ratio(colour, themes.field_background())
                self.assertGreaterEqual(ratio, 4.5, "%s in %s: %.2f" % (category, theme, ratio))

    def test_a_persons_chat_keeps_the_lists_colour(self):
        self.assertIsNone(themes.kind_colour(c.CATEGORY_CONTACTS))
        self.assertIsNone(themes.kind_colour(c.CATEGORY_NON_CONTACTS))


class AvatarTest(unittest.TestCase):
    def setUp(self):
        get_app()

    def test_initials_are_the_first_letters_of_two_words(self):
        self.assertEqual(avatars.initials("Mona Ali"), "MA")
        self.assertEqual(avatars.initials("weather"), "W")
        self.assertEqual(avatars.initials("قناة الأخبار"), "قا")
        self.assertEqual(avatars.initials("🙂 ✨"), "#")

    def test_a_photo_is_cut_round(self):
        path = os.path.join(tempfile.mkdtemp(), "photo.jpg")
        wx.Image(80, 60).SaveFile(path, wx.BITMAP_TYPE_JPEG)
        alpha = avatars.round_photo(path, 32).ConvertToImage().GetAlpha()
        self.assertEqual(alpha[0], 0)
        self.assertEqual(alpha[16 * 32 + 16], 255)
        self.assertIsNone(avatars.round_photo(path + ".missing", 32))

    def test_a_chat_without_its_photo_here_shows_initials_until_it_comes(self):
        folder = tempfile.mkdtemp()
        pictures = avatars.ChatPictures(folder, 32)
        index = pictures.index_for({"id": 5, "photo": 900, "title": "Mona"})
        self.assertEqual(pictures.take_missing(), [(5, 900)])
        self.assertEqual(pictures.take_missing(), [])
        self.assertEqual(pictures.index_for({"id": 5, "photo": 900, "title": "Mona"}), index)
        path = avatars.photo_path(folder, 5, 900)
        wx.Image(40, 40).SaveFile(path, wx.BITMAP_TYPE_JPEG)
        self.assertTrue(pictures.photo_arrived(5, 900, path))
        # A photo of a chat that has since changed it is no longer wanted.
        self.assertFalse(pictures.photo_arrived(5, 899, path))
        self.assertEqual(pictures.image_list.GetImageCount(), 1)


class ChatRowsTest(unittest.TestCase):
    def setUp(self):
        get_app()
        self.frame = wx.Frame(None)
        self.addCleanup(self.frame.Destroy)
        self.rows = ChatRows(self.frame)
        self.events = []
        self.rows.Bind(wx.EVT_LISTBOX, lambda event: self.events.append(("select", event.GetInt())))
        self.rows.Bind(wx.EVT_LISTBOX_DCLICK, lambda event: self.events.append(("open", event.GetInt())))

    def test_it_answers_as_a_list_box_does(self):
        self.rows.Set(["one", "two"])
        self.rows.Append("four")
        self.rows.Insert("three", 2)
        self.assertEqual(self.rows.GetItems(), ["one", "two", "three", "four"])
        self.rows.SetString(0, "first")
        self.rows.Delete(1)
        self.assertEqual(self.rows.GetItems(), ["first", "three", "four"])
        self.assertEqual(self.rows.GetSelection(), wx.NOT_FOUND)
        self.rows.SetSelection(2)
        self.assertEqual(self.rows.GetSelection(), 2)
        self.rows.SetSelection(wx.NOT_FOUND)
        self.assertEqual(self.rows.GetSelection(), wx.NOT_FOUND)
        self.assertEqual(self.rows.GetCount(), 3)
        self.rows.Clear()
        self.assertTrue(self.rows.IsEmpty())

    def test_only_the_users_moves_are_told_as_a_list_box_tells_them(self):
        self.rows.Set(["one", "two"])
        self.rows.SetSelection(1)
        pump(timeout=0.05)
        self.assertEqual(self.events, [])
        selected = wx.ListEvent(wx.wxEVT_LIST_ITEM_SELECTED, self.rows.GetId())
        selected.SetIndex(0)
        self.rows.on_selected(selected)
        activated = wx.ListEvent(wx.wxEVT_LIST_ITEM_ACTIVATED, self.rows.GetId())
        activated.SetIndex(0)
        self.rows.on_activated(activated)
        self.assertEqual(self.events, [("select", 0), ("open", 0)])


async def fake_download(self, owner, file=None, download_big=False):
    FakeTelegramClient.calls.append(("download_profile_photo", owner.id, download_big))
    wx.Image(60, 60).SaveFile(file, wx.BITMAP_TYPE_JPEG)
    return file


class ChatListLookTest(WindowTestCase):
    chats = [
        (with_photo(make_user(11, "Ahmed"), 501), 2, False),
        (make_channel(1000000002, "News"), 0, False),
        (make_channel(1000000003, "Friends", group=True), 0, False),
        (make_user(14, "Weather", bot=True), 0, False),
    ]

    def setUp(self):
        self.photos = tempfile.mkdtemp()
        for patch in (
            mock.patch.object(ui.chat_list, "CHAT_PHOTOS_DIR", self.photos),
            mock.patch.object(ui.main_frame, "CHAT_PHOTOS_DIR", self.photos),
            mock.patch.object(FakeTelegramClient, "download_profile_photo", fake_download, create=True),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        super().setUp()
        self.rows = self.frame.dialogs_list
        self.frame.dialogs_list.pictures = None
        self.frame.set_up_chat_pictures()
        self.frame.render_dialogs()

    def row(self, title):
        return next(index for index, dialog in enumerate(self.frame.dialogs) if dialog["title"] == title)

    def test_rows_are_coloured_by_kind_and_unread_ones_are_bold(self):
        colour = lambda title: self.rows.GetItemTextColour(self.row(title))
        self.assertEqual(colour("News"), themes.kind_colour(c.CATEGORY_BROADCASTS))
        self.assertEqual(colour("Friends"), themes.kind_colour(c.CATEGORY_GROUPS))
        self.assertEqual(colour("Weather"), themes.kind_colour(c.CATEGORY_BOTS))
        self.assertEqual(colour("Ahmed"), self.rows.GetTextColour())
        self.assertEqual(self.rows.GetItemFont(self.row("Ahmed")).GetWeight(), wx.FONTWEIGHT_BOLD)
        self.assertEqual(self.rows.GetItemFont(self.row("News")).GetWeight(), wx.FONTWEIGHT_NORMAL)
        # The words still say it all, for whoever cannot see the colour.
        self.assertIn(self.text(c.CHAT_KIND_CHANNEL), self.rows.GetString(self.row("News")))

    def test_colours_turned_off_leave_every_row_plain(self):
        self.frame.settings.set(s.SETTING_CHAT_COLOURS, False)
        self.rows.paint_rows()
        for index in range(self.rows.GetCount()):
            self.assertEqual(self.rows.GetItemTextColour(index), self.rows.GetTextColour())
            self.assertEqual(self.rows.GetItemFont(index).GetWeight(), wx.FONTWEIGHT_NORMAL)

    def test_every_row_has_a_picture_and_a_photo_is_fetched_once(self):
        for index in range(self.rows.GetCount()):
            self.assertGreaterEqual(self.rows.GetItem(index).GetImage(), 0)
        path = avatars.photo_path(self.photos, 11, 501)
        self.assertTrue(pump(lambda: os.path.exists(path)), "the photo did not come")
        self.assertEqual(self.calls("download_profile_photo"), [("download_profile_photo", 11, False)])
        # Only Ahmed has a photo; the others show their initials and ask for nothing.
        self.frame.render_dialogs()
        pump(timeout=0.5)
        self.assertEqual(len(self.calls("download_profile_photo")), 1)

    def test_a_new_photo_replaces_the_old_one_on_the_disk(self):
        old = avatars.photo_path(self.photos, 11, 400)
        wx.Image(10, 10).SaveFile(old, wx.BITMAP_TYPE_JPEG)
        new = avatars.photo_path(self.photos, 11, 501)
        self.assertTrue(pump(lambda: os.path.exists(new) and not os.path.exists(old)))

    def test_pictures_turned_off_leave_the_list_without_them(self):
        self.frame.settings.set(s.SETTING_CHAT_PHOTOS, False)
        self.frame.apply_text_size()
        self.assertIsNone(self.rows.pictures)
        self.assertIsNone(self.rows.GetImageList(wx.IMAGE_LIST_SMALL))
        # Windows' way of saying "no picture" is a number below zero.
        self.assertLess(self.rows.GetItem(0).GetImage(), 0)

    def test_larger_text_brings_larger_pictures(self):
        size = self.rows.pictures.size
        self.frame.settings.set(s.SETTING_LARGE_TEXT, True)
        self.frame.apply_text_size()
        self.assertGreater(self.rows.pictures.size, size)

    @HAS_ICON_FONT
    def test_buttons_and_tabs_carry_pictures(self):
        for button in (self.frame.send_btn, self.frame.attach_btn, self.frame.record_btn, self.frame.list_search_btn,
                       *self.frame.mouse_buttons, *self.frame.view_tabs.buttons):
            self.assertTrue(button.GetBitmap().IsOk(), button.GetLabel())
