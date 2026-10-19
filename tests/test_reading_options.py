"""Choices about what is heard and how it is written: whole announcements, recording tones, Enter, the time on a row."""
import asyncio
import datetime
from unittest import mock

import wx

import core.constants as c
import core.settings as s
import core.telegram_client as telegram_client
import ui.voice
from tests.harness import Record, WindowTestCase, make_message, make_user, pump

ALI = make_user(1, "Ali")
LONG = "start " + "word " * 40 + "the very end"
# A fixed afternoon in another year, as the computer's own clock would show it.
THEN = datetime.datetime(2020, 3, 9, 14, 5).astimezone()


class FakeRecorder:
    device = level = reduction_db = None

    def __init__(self):
        self.recording = False

    def is_recording(self):
        return self.recording

    def start(self):
        self.recording = True

    def finish(self, path):
        self.recording = False
        return 3.0

    def cancel(self):
        self.recording = False


class ReadingOptionsTest(WindowTestCase):
    chats = [(ALI, 0, False)]
    history = {1: [make_message(1, "old one", sender=ALI, date=THEN), make_message(2, "today's", sender=ALI)]}

    def incoming(self, text):
        async def value(result):
            return result
        event = Record(
            chat_id=1, get_sender=lambda: value(ALI), get_chat=lambda: value(ALI), get_input_chat=lambda: value(None),
            message=make_message(50 + len(self.spoken), text, sender=ALI)
        )
        before = len(self.spoken)
        asyncio.run_coroutine_threadsafe(self.manager.client.handlers["NewMessage"](event), self.manager.loop)
        self.assertTrue(pump(lambda: len(self.spoken) > before))
        return self.spoken[-1]

    def test_new_message_is_spoken_to_its_end_only_when_asked(self):
        self.assertNotIn("the very end", self.incoming(LONG))
        self.frame.settings.set(s.SETTING_ANNOUNCE_WHAT, c.ANNOUNCE_WHAT_WHOLE)
        spoken = self.incoming(LONG + "\nsecond line")
        self.assertIn("the very end second line", spoken)
        self.assertTrue(spoken.startswith("Ali"))

    def record(self):
        self.frame.recorder = FakeRecorder()
        # The send that follows a recording is faked here and never reports back.
        self.frame.is_busy = False
        self.spoken.clear()
        self.played.clear()
        with mock.patch.object(ui.voice.audio, "AVAILABLE", True), \
                mock.patch.object(ui.voice.audio, "find_input", lambda name: None), \
                mock.patch.object(self.manager, "send_file"):
            self.frame.on_record_menu(None)
            started = (list(self.played), list(self.spoken))
            self.frame.on_record_menu(None)
        return started

    def test_recording_is_marked_by_tones_and_not_by_words_that_would_be_recorded(self):
        self.open_chat(0)
        played, spoken = self.record()
        self.assertEqual(played, [c.SOUND_RECORD_START])
        self.assertNotIn(self.text(c.MSG_RECORDING_KEY), spoken)
        # Still there to see.
        self.assertEqual(self.played[1], c.SOUND_RECORD_STOP)

        self.frame.settings.set(s.SETTING_RECORD_SOUND, False)
        played, spoken = self.record()
        self.assertEqual(played, [])
        self.assertEqual(spoken, [self.text(c.MSG_RECORDING_KEY)])
        self.assertNotIn(c.SOUND_RECORD_STOP, self.played)

    def press_enter(self, shift=False, control=False, alt=False):
        event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        event.SetKeyCode(wx.WXK_RETURN)
        event.SetShiftDown(shift)
        event.SetControlDown(control)
        event.SetAltDown(alt)
        with mock.patch.object(wx.Window, "FindFocus", return_value=self.frame.message_input):
            self.frame.ProcessEvent(event)

    def test_enter_sends_and_shift_enter_breaks_the_line_or_the_other_way_round(self):
        self.open_chat(0)
        sent = []
        self.frame.on_send_message = lambda event, silent=False: sent.append(self.frame.message_input.GetValue())
        field = self.frame.message_input
        field.SetValue("one")
        field.SetInsertionPointEnd()
        self.press_enter(shift=True)
        field.WriteText("two")
        self.assertEqual(field.GetValue(), "one\ntwo")
        self.assertEqual(sent, [])
        self.press_enter()
        self.assertEqual(sent, ["one\ntwo"])

        self.frame.settings.set(s.SETTING_ENTER_SENDS, False)
        self.press_enter()
        self.assertEqual(field.GetValue(), "one\ntwo\n")
        self.assertEqual(len(sent), 1)
        self.press_enter(control=True)
        self.assertEqual(len(sent), 2)

    def test_other_ways_of_sending_keep_their_own_shortcuts(self):
        self.open_chat(0)
        sent, scheduled = [], []
        self.frame.on_send_message = lambda event, silent=False: sent.append(silent)
        self.frame.on_schedule_menu = lambda event: scheduled.append(True)
        # The writing field's menu holds them, so its shortcuts are taken anew.
        self.frame.apply_shortcuts()
        self.frame.message_input.SetValue("text")
        # Alt+Enter sends silently and Ctrl+Shift+Enter schedules, not a plain send nor a new line.
        self.press_enter(alt=True)
        self.press_enter(control=True, shift=True)
        self.assertEqual((sent, scheduled, self.frame.message_input.GetValue()), ([True], [True], "text"))

    def test_a_message_with_line_breaks_is_sent_as_written(self):
        self.open_chat(0)
        self.frame.message_input.SetValue("first\nsecond")
        self.frame.on_send_message(None)
        self.assertTrue(pump(lambda: self.calls("send")))
        self.assertEqual(self.calls("send")[0][2], "first\nsecond")

    def rows(self):
        self.frame.render_messages(0)
        return [self.frame.messages_list.GetString(index) for index in range(2)]

    def test_time_on_a_row_is_written_the_way_that_was_chosen(self):
        self.open_chat(0)
        old, today = self.rows()
        self.assertTrue(old.endswith("2020-03-09 14:05"))
        self.assertRegex(today, r"\d\d:\d\d$")

        self.frame.settings.set(s.SETTING_TIME_STYLE, c.TIME_STYLE_WORDS_24)
        old, today = self.rows()
        # A past year is named; today needs no day at all.
        self.assertTrue(old.endswith("9 %s 2020، 14:05" % self.text("MONTH_3")))
        self.assertRegex(today, r"\d\d:\d\d$")

        self.frame.settings.set(s.SETTING_TIME_STYLE, c.TIME_STYLE_WORDS_12)
        old, today = self.rows()
        self.assertTrue(old.endswith("9 %s 2020، 2:05 %s" % (self.text("MONTH_3"), self.text(c.TIME_PM_KEY))))
        self.assertEqual(self.frame.time_text(THEN.replace(hour=0, minute=7), False), "12:07 " + self.text(c.TIME_AM_KEY))
        this_year = THEN.replace(year=datetime.date.today().year)
        self.assertNotIn(str(this_year.year), self.frame.time_text(this_year, True))

        self.frame.settings.set(s.SETTING_TIME_STYLE, c.TIME_STYLE_NONE)
        old, today = self.rows()
        self.assertEqual(old, "Ali: old one")
        self.assertEqual(today, "Ali: today's")
        # The box under the list still tells when.
        self.frame.messages_list.SetSelection(0)
        self.frame.update_preview()
        self.assertIn("2020-03-09 14:05", self.frame.preview_text.GetValue())
