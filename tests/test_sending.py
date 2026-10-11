"""Everything that can be sent besides plain text: files and albums, stickers, contacts, places, mentions."""
import os
import tempfile
from unittest import mock

import wx
from telethon.tl import types

import core.constants as c
from tests.harness import (
    FakeChooser, FakeTelegramClient, Record, WindowTestCase, make_channel, make_member, make_message, make_user, pump
)

ALI = make_user(1, "Ali")
TEAM = make_channel(4, "Team", group=True)
ZAKI = types.User(id=9, first_name="Zaki", last_name="Omar", phone="201000000009", contact=True, access_hash=1)
SHY = types.User(id=10, first_name="Shy", contact=True, access_hash=1)
MONA = make_member(5, "Mona")
MONA.username = "mona_s"
SAMI = make_member(6, "Sami")
ME = make_member(7, "Me", is_self=True)


class ClipboardWith:
    """A clipboard holding copied files, a picture, or text, without touching the real one."""

    def __init__(self, files=(), bitmap=None, text=False):
        self.files, self.bitmap, self.text = files, bitmap, text

    def Open(self):
        return True

    def Close(self):
        pass

    def IsSupported(self, data_format):
        return {
            wx.DF_FILENAME: bool(self.files), wx.DF_BITMAP: self.bitmap is not None, wx.DF_UNICODETEXT: self.text
        }.get(data_format.GetType(), False)

    def GetData(self, data):
        if isinstance(data, wx.FileDataObject):
            for path in self.files:
                data.AddFile(path)
        else:
            data.SetBitmap(self.bitmap)
        return True


class SendingTest(WindowTestCase):
    chats = [(ALI, 0, False), (TEAM, 0, False)]
    history = {1: [
        make_message(1, "first", sender=ALI),
        make_message(2, sender=ALI, sticker=Record(attributes=[
            types.DocumentAttributeSticker(alt="😺", stickerset=types.InputStickerSetEmpty())
        ])),
        make_message(3, sender=ALI, contact=Record(first_name="Zaki", last_name="Omar", phone_number="+2010")),
        make_message(4, sender=ALI, geo=Record(lat=30.5, long=31.25)),
    ]}

    def setUp(self):
        super().setUp()
        self.open_chat(0)

    def sent(self):
        return self.calls("send_file")

    def test_several_pictures_go_as_one_album_with_the_caption(self):
        FakeChooser.values = ["our trip"]
        FakeChooser.selection = 0
        self.frame.send_paths(["a.jpg", "b.png"])
        self.assertTrue(pump(lambda: len(self.sent()) == 1))
        self.assertEqual(self.sent()[0], ("send_file", 1, ["a.jpg", "b.png"], "our trip", False, None))
        self.assertEqual(FakeChooser.last_choices, [self.text(c.SEND_AS_MEDIA_KEY), self.text(c.SEND_AS_FILES_KEY)])
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.text(c.MSG_FILES_SENT_FORMAT_KEY).format(count=2)]))

    def test_pictures_can_go_as_files_and_documents_are_never_asked(self):
        FakeChooser.values = ["", ""]
        FakeChooser.selection = 1
        self.frame.send_paths(["a.jpg"])
        self.assertTrue(pump(lambda: len(self.sent()) == 1))
        self.assertEqual(self.sent()[0][2:5], ("a.jpg", None, True))

        FakeChooser.last_choices = None
        self.frame.send_paths(["notes.pdf"])
        self.assertTrue(pump(lambda: len(self.sent()) == 2))
        self.assertIsNone(FakeChooser.last_choices)
        self.assertEqual(self.sent()[1][2:5], ("notes.pdf", None, False))

    def test_backing_out_of_the_caption_sends_nothing(self):
        FakeChooser.confirmed = False
        self.frame.send_paths(["a.jpg"])
        pump(timeout=0.2)
        self.assertEqual(self.sent(), [])
        self.assertFalse(self.frame.is_busy)

    def test_files_answer_the_message_being_replied_to(self):
        self.frame.set_compose(reply_to=self.frame.messages[0])
        FakeChooser.values = [""]
        self.frame.send_paths(["notes.pdf"])
        self.assertTrue(pump(lambda: len(self.sent()) == 1))
        self.assertEqual(self.sent()[0][5], 1)
        self.assertIsNone(self.frame.reply_to)

    def test_copied_files_and_pictures_are_sent_on_paste_but_text_is_left_alone(self):
        with mock.patch.object(self.frame, "send_paths") as send_paths:
            with mock.patch.object(wx, "TheClipboard", ClipboardWith(files=["C:\\docs\\report.pdf"])):
                self.assertTrue(self.frame.paste_files())
            send_paths.assert_called_once_with(["C:\\docs\\report.pdf"])

            with mock.patch.object(wx, "TheClipboard", ClipboardWith(bitmap=wx.Bitmap(4, 4))):
                self.assertTrue(self.frame.paste_files())
            picture = send_paths.call_args.args[0][0]
            self.assertTrue(os.path.exists(picture))
            self.assertTrue(picture.endswith(c.PASTED_IMAGE_NAME))

            send_paths.reset_mock()
            with mock.patch.object(wx, "TheClipboard", ClipboardWith(bitmap=wx.Bitmap(4, 4), text=True)):
                self.assertFalse(self.frame.paste_files())
            with mock.patch.object(wx, "TheClipboard", ClipboardWith(text=True)):
                self.assertFalse(self.frame.paste_files())
            send_paths.assert_not_called()

    def test_sticker_is_picked_by_set_and_emoji(self):
        FakeTelegramClient.sticker_sets = [("Cats", ["😺", "😹"])]
        FakeTelegramClient.recent_stickers = ["👍"]
        FakeChooser.selection = 1
        self.frame.on_send_sticker_menu(None)
        self.assertTrue(pump(lambda: len(self.sent()) == 1))
        self.assertEqual(self.sent()[0][2].attributes[0].alt, "😹")
        self.assertEqual(FakeChooser.last_choices, ["1. 😺", "2. 😹"])

    def test_recent_stickers_come_first_and_an_empty_set_says_so(self):
        FakeChooser.selection = 0
        self.frame.on_send_sticker_menu(None)
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.text(c.MSG_NO_STICKERS_KEY)]))
        self.assertEqual(FakeChooser.last_choices, [self.text(c.STICKERS_RECENT_KEY)])
        self.assertEqual(self.sent(), [])

    def test_contact_card_carries_name_and_number(self):
        FakeTelegramClient.contacts = [ZAKI]
        FakeTelegramClient.public["zaki"] = ZAKI
        self.frame.on_send_contact_menu(None)
        self.assertTrue(pump(lambda: len(self.sent()) == 1))
        card = self.sent()[0][2]
        self.assertEqual((card.phone_number, card.first_name, card.last_name), ("201000000009", "Zaki", "Omar"))

    def test_contact_with_a_hidden_number_cannot_be_shared(self):
        FakeTelegramClient.contacts = [SHY]
        FakeTelegramClient.public["shy"] = SHY
        self.frame.on_send_contact_menu(None)
        self.assertTrue(pump(lambda: self.boxes == [self.text(c.ERR_NO_PHONE_KEY)]))
        self.assertEqual(self.sent(), [])

    def test_place_is_sent_from_typed_coordinates(self):
        FakeChooser.values = ["30.0444، 31.2357"]
        self.frame.on_send_location_menu(None)
        self.assertTrue(pump(lambda: len(self.sent()) == 1))
        point = self.sent()[0][2].geo_point
        self.assertEqual((point.lat, point.long), (30.0444, 31.2357))

        for wrong in ("somewhere nice", "95, 10", "30.0"):
            FakeChooser.values = [wrong]
            self.frame.on_send_location_menu(None)
        self.assertEqual(self.boxes, [self.text(c.ERR_BAD_LOCATION_KEY)] * 3)
        self.assertEqual(len(self.sent()), 1)

    def test_mention_uses_the_username_or_else_a_link_to_the_person(self):
        self.frame.on_mention_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_MENTION_GROUPS_ONLY_KEY))

        FakeTelegramClient.members = [ME, MONA, SAMI]
        self.open_chat(1)
        FakeChooser.selection = 0
        self.frame.on_mention_menu(None)
        self.assertTrue(pump(lambda: self.frame.message_input.GetValue() == "@mona_s "))
        # This account itself is not offered.
        self.assertEqual(FakeChooser.last_choices, ["Mona", "Sami"])
        FakeChooser.selection = 1
        self.frame.on_mention_menu(None)
        self.assertTrue(pump(lambda: self.frame.message_input.GetValue() == "@mona_s [Sami](tg://user?id=6) "))

    def test_attachments_without_text_still_say_what_they_are(self):
        rows = [self.frame.messages_list.GetString(index) for index in range(4)]
        self.assertIn("😺", rows[1])
        self.assertIn("Zaki Omar +2010", rows[2])
        self.assertIn("30.5, 31.25", rows[3])
        # A place can be opened on a map through the message's links.
        self.assertEqual(self.frame.messages[3]["links"], ["https://www.google.com/maps?q=30.5,31.25"])
        # None of that is text of the message: it cannot be copied or edited as such.
        self.assertEqual(self.frame.messages[1]["text"], "")
