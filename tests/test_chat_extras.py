"""A chat's own tone, typing on the chat list, a chat saved as text, stopping an upload, and reminders."""
import asyncio
import datetime
import os
import shutil
import tempfile
from unittest import mock

import wx

import core.constants as c
import core.settings as s
import core.reminders
import core.sounds
import ui.chat_extras
from tests.harness import FakeChooser, FakeTelegramClient, WindowTestCase, make_message, make_user, pump
from ui.chat_extras import chat_tone

ALI = make_user(1, "Ali")
MONA = make_user(2, "Mona")


class ChatExtrasTest(WindowTestCase):
    chats = [(ALI, 0, False), (MONA, 0, False)]
    history = {1: [
        make_message(1, "first", sender=ALI, chat_id=1),
        make_message(2, "second\nline", outgoing=True, chat_id=1),
    ]}

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, True)
        for patch in (
            mock.patch.object(core.sounds, "USER_SOUNDS_DIR", os.path.join(self.folder, "sounds")),
            mock.patch.object(core.reminders, "REMINDERS_FILE", os.path.join(self.folder, "reminders.json")),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def chat(self, index):
        return self.frame.all_dialogs[index]

    # A chat's own tone

    def test_a_chat_with_its_own_tone_plays_it_and_the_others_keep_the_usual(self):
        self.assertEqual(self.frame.message_tone(1), c.SOUND_MESSAGE)
        core.sounds.set_custom(chat_tone(1), os.path.join(c.SOUNDS_DIR, "sent.wav"))
        self.assertEqual(self.frame.message_tone(1), chat_tone(1))
        self.assertEqual(self.frame.message_tone(2), c.SOUND_MESSAGE)
        self.frame.on_new_message(self.chat(0), make_message_dict(9, "new"))
        self.assertEqual(self.played[-1], chat_tone(1))

    def test_going_back_to_the_usual_tone(self):
        core.sounds.set_custom(chat_tone(1), os.path.join(c.SOUNDS_DIR, "sent.wav"))
        FakeChooser.selection = 2
        self.frame.on_chat_tone(self.chat(0))
        self.assertEqual(self.frame.message_tone(1), c.SOUND_MESSAGE)

    # Typing on the chat list

    def test_typing_shows_on_the_row_of_its_chat_until_it_stops(self):
        self.frame.on_typing(2, c.TYPING_ACTION_VOICE)
        said = self.text("MSG_RECORDING_VOICE_FORMAT").format(chat="Mona")
        index = self.frame.find_dialog_index(2)
        self.assertIn(said, self.frame.dialogs_list.GetString(index))
        self.frame.on_typing(2, c.TYPING_ACTION_CANCEL)
        self.assertNotIn(said, self.frame.dialogs_list.GetString(index))

    def test_the_message_arriving_takes_the_typing_off_the_row(self):
        self.frame.on_typing(2, c.TYPING_ACTION_TYPING)
        self.frame.on_new_message(self.chat(1), make_message_dict(5, "hi", chat_id=2))
        index = self.frame.find_dialog_index(2)
        self.assertNotIn(self.text(c.MSG_TYPING_FORMAT_KEY).format(chat="Mona"), self.frame.dialogs_list.GetString(index))

    # A chat saved as text

    def test_a_chat_is_saved_oldest_first_with_its_line_breaks(self):
        self.frame.settings.set(s.SETTING_DOWNLOAD_FOLDER, os.path.join(self.folder, "downloads"))
        self.frame.on_export_chat(self.chat(0))
        path = os.path.join(self.folder, "downloads", "Ali.txt")
        self.assertTrue(pump(lambda: os.path.exists(path)))
        with open(path, encoding="utf-8-sig") as saved:
            text = saved.read()
        self.assertLess(text.index("first"), text.index("second\nline"))
        self.assertIn(self.text(c.SENDER_YOU_KEY) + ": second", text)
        self.assertIn(path, self.spoken[-1])

    # Stopping an upload

    def test_an_upload_can_be_stopped_and_nothing_is_sent(self):
        self.open_chat(0)
        gate = FakeTelegramClient.transfer_gate = asyncio.Event()
        self.addCleanup(setattr, FakeTelegramClient, "transfer_gate", None)
        FakeChooser.values = [""]
        self.frame.send_paths(["report.pdf"])
        self.assertTrue(pump(lambda: self.frame.progress_gauge.IsShown()))
        self.frame.cancel_upload()
        self.assertFalse(self.frame.is_busy)
        self.assertIsNone(self.frame.upload)
        self.assertEqual(self.frame.messages_list.GetCount(), len(self.frame.messages))
        self.manager.loop.call_soon_threadsafe(gate.set)
        pump(timeout=0.3)
        self.assertEqual(self.calls("send_file"), [])
        self.assertEqual(self.spoken[-1], self.text(c.MSG_UPLOAD_CANCELLED_KEY))

    def test_cancelling_with_nothing_going_up_says_so(self):
        self.frame.on_cancel_upload_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NO_UPLOAD_KEY))

    # Reminders

    def test_a_reminder_is_kept_and_given_when_its_time_comes(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(0)
        FakeChooser.selection = 0
        self.frame.on_remind_menu(None)
        self.assertEqual(len(core.reminders.load()), 1)
        self.assertEqual(core.reminders.load()[0]["message_id"], 1)

        # Its time has come: it is said, and taken off the list.
        self.frame.reminders[0]["due"] = (datetime.datetime.now().astimezone() - datetime.timedelta(minutes=1)).isoformat()
        self.box_answer = wx.NO
        self.frame.check_reminders()
        said = self.text(c.MSG_REMINDER_DUE_FORMAT_KEY).format(chat="Ali", text="first")
        self.assertIn(said, self.spoken)
        self.assertEqual(core.reminders.load(), [])

    def test_a_reminder_can_be_deleted_from_the_list(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(0)
        FakeChooser.selection = 1
        self.frame.on_remind_menu(None)
        FakeChooser.selection = 0
        self.frame.on_reminders_menu(None)
        self.assertEqual(self.frame.reminders, [])
        self.assertEqual(core.reminders.load(), [])

    def test_tomorrow_morning_is_nine_oclock_the_next_day(self):
        now = datetime.datetime(2026, 10, 17, 22, 30)
        self.assertEqual(core.reminders.when(None, now), datetime.datetime(2026, 10, 18, 9, 0))
        self.assertEqual(core.reminders.when(15, now), datetime.datetime(2026, 10, 17, 22, 45))


def make_message_dict(message_id, text, chat_id=1):
    """A message as the live updates hand it to the window."""
    return {
        "id": message_id, "sender": "Someone", "sender_id": chat_id, "text": text, "detail": "", "file": None,
        "media": None, "date": datetime.datetime.now().astimezone(), "outgoing": False, "reply_to": None,
        "forwarded_from": None, "edited": False, "buttons": [], "poll": None, "views": None, "forwards": None,
        "comments": None, "reactions": [], "pinned": False, "read": None, "links": [], "thread_id": None,
    }
