"""Space plays a voice message straight from Telegram and keeps nothing; Enter saves it.
And in any list, typing the start of a name goes to it."""
import os
import tempfile
import unittest
from unittest import mock

import wx

import core.constants as c
import core.settings as s
from tests.harness import Record, WindowTestCase, get_app, make_channel, make_message, make_user, pump
from ui.type_ahead import TypeAhead, fold

ALI = make_user(1, "Ali")
AHMED = make_user(2, "أحمد")
TEAM = make_channel(41, "Team", group=True)


class Typed:
    """A key typed, as the list sees it."""

    def __init__(self, char, control=False):
        self.char = char
        self.control = control
        self.skipped = False

    def GetUnicodeKey(self):
        return ord(self.char)

    def ControlDown(self):
        return self.control

    def AltDown(self):
        return False

    def Skip(self):
        self.skipped = True


class ListenTest(WindowTestCase):
    chats = [(ALI, 0, False)]
    history = {1: [
        make_message(1, sender=ALI, voice=True, file=Record(name=None, size=30000, duration=4)),
        make_message(2, "words only", sender=ALI),
    ]}

    def setUp(self):
        super().setUp()
        self.heard = []
        for patch in (
            mock.patch.object(self.frame, "play_voice", self.heard.append),
            mock.patch("core.audio.AVAILABLE", True),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.open_chat(0)

    def space(self):
        event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        event.SetKeyCode(wx.WXK_SPACE)
        with mock.patch.object(wx.Window, "FindFocus", return_value=self.frame.messages_list):
            self.frame.on_char_hook(event)
        return event.GetSkipped()

    def test_space_plays_from_memory_and_writes_nothing(self):
        self.frame.messages_list.SetSelection(0)
        self.assertFalse(self.space())
        self.assertTrue(pump(lambda: self.heard))
        self.assertEqual(self.heard, [b"sound"])
        # Asked for in memory, not into any folder.
        self.assertEqual([call[2] for call in self.calls("download")], [bytes])

    def test_heard_once_it_plays_again_without_a_second_fetch(self):
        self.frame.messages_list.SetSelection(0)
        self.space()
        self.assertTrue(pump(lambda: self.heard))
        self.space()
        self.assertEqual(len(self.heard), 2)
        self.assertEqual(len(self.calls("download")), 1)

    def test_space_while_it_plays_stops_it(self):
        self.frame.messages_list.SetSelection(0)
        with mock.patch.object(self.frame.player, "is_playing", lambda: True), \
                mock.patch.object(self.frame.player, "stop") as stop:
            self.space()
        stop.assert_called_once()
        self.assertEqual(self.calls("download"), [])

    def test_space_on_a_message_without_sound_is_left_alone(self):
        self.frame.messages_list.SetSelection(1)
        self.assertTrue(self.space())
        self.assertEqual(self.calls("download"), [])

    def test_enter_saves_it_to_the_downloads_and_plays_nothing(self):
        folder = tempfile.mkdtemp()
        self.frame.settings.set(s.SETTING_DOWNLOAD_FOLDER, folder)
        self.frame.messages_list.SetSelection(0)
        self.frame.on_activate_message(None)
        self.assertTrue(pump(lambda: not self.frame.is_busy and self.calls("download")))
        self.assertEqual(self.calls("download")[0][2], folder + os.sep)
        self.assertEqual(self.heard, [])
        self.assertIn(folder, self.spoken[-1])


class ChatListTypingTest(WindowTestCase):
    chats = [(ALI, 0, False), (AHMED, 0, False), (TEAM, 0, False)]

    def type(self, text):
        for char in text:
            self.frame.dialogs_type_ahead.on_char(Typed(char))

    def selected_title(self):
        return self.frame.dialogs[self.frame.dialogs_list.GetSelection()]["title"]

    def test_a_name_is_found_by_its_first_letters(self):
        self.frame.dialogs_list.SetSelection(0)
        self.type("te")
        self.assertEqual(self.selected_title(), "Team")

    def test_arabic_is_found_without_its_hamza(self):
        self.frame.dialogs_list.SetSelection(0)
        self.type("احم")
        self.assertEqual(self.selected_title(), "أحمد")

    def test_a_row_with_no_chat_behind_it_is_typed_through(self):
        # E.g. the row that says more chats are being fetched, after the last chat.
        self.frame.dialogs_list.Append("loading")
        self.frame.dialogs_list.SetSelection(2)
        self.type("l")
        self.assertEqual(self.frame.dialogs_list.GetSelection(), 3)
        self.type_ahead_reset()
        self.type("a")
        self.assertEqual(self.selected_title(), "Ali")

    def type_ahead_reset(self):
        self.frame.dialogs_type_ahead.typed = ""

    def test_typing_with_control_is_left_to_the_shortcuts(self):
        event = Typed("t", control=True)
        self.frame.dialogs_type_ahead.on_char(event)
        self.assertTrue(event.skipped)


class TypeAheadTest(unittest.TestCase):
    def setUp(self):
        get_app()
        self.frame = wx.Frame(None)
        self.addCleanup(self.frame.Destroy)
        self.list_box = wx.ListBox(self.frame, choices=["Apple", "Avocado", "Banana", "apricot"])
        self.type_ahead = TypeAhead(self.list_box)
        self.list_box.SetSelection(0)

    def press(self, char):
        event = Typed(char)
        self.type_ahead.on_char(event)
        return event

    def test_one_letter_again_and_again_goes_round_the_items_with_it(self):
        self.press("a")
        self.assertEqual(self.list_box.GetSelection(), 1)
        self.type_ahead.typed = ""
        self.press("a")
        self.assertEqual(self.list_box.GetSelection(), 3)
        self.type_ahead.typed = ""
        self.press("a")
        self.assertEqual(self.list_box.GetSelection(), 0)

    def test_a_space_on_its_own_is_the_lists_own(self):
        self.assertTrue(self.press(" ").skipped)

    def test_after_a_pause_the_typing_starts_over(self):
        self.press("b")
        self.assertEqual(self.list_box.GetSelection(), 2)
        self.type_ahead.last_typed -= c.TYPE_AHEAD_PAUSE_SECONDS + 1
        self.press("a")
        self.assertEqual(self.list_box.GetSelection(), 3)

    def test_arabic_letters_people_type_one_for_another_match(self):
        self.assertEqual(fold("إسلام"), fold("اسلام"))
        self.assertEqual(fold("مدرسة"), fold("مدرسه"))
        self.assertEqual(fold("مُصْطَفى"), fold("مصطفي"))
