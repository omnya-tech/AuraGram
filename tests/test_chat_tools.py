"""Around the message field: the attach button, the progress bar of a transfer, and Escape leaving the chat."""
import asyncio
from unittest import mock

import wx

import core.constants as c
from tests.harness import FakeChooser, FakeTelegramClient, WindowTestCase, make_message, make_user, pump

ALI = make_user(1, "Ali")
MONA = make_user(2, "Mona")


class ChatToolsTest(WindowTestCase):
    chats = [(ALI, 0, False), (MONA, 0, False)]
    history = {1: [make_message(1, "hello", sender=ALI), make_message(2, sender=ALI, photo=True)]}

    def status(self):
        return self.frame.GetStatusBar().GetStatusText()

    def test_attach_button_offers_everything_that_can_go_with_a_message(self):
        self.assertFalse(self.frame.attach_btn.IsEnabled())
        self.open_chat(0)
        self.assertTrue(self.frame.attach_btn.IsEnabled())
        self.frame.on_attach(None)
        self.assertEqual(self.menu_labels, [
            self.frame.i18n.get_string(key).partition("\t")[0] for key in (
                c.MENU_SEND_FILE_KEY, c.MENU_SEND_STICKER_KEY, c.MENU_SEND_CONTACT_KEY,
                c.MENU_SEND_LOCATION_KEY, c.MENU_NEW_POLL_KEY,
            )
        ])

    def test_progress_bar_follows_an_upload_and_goes_away_after_it(self):
        self.open_chat(0)
        gate = FakeTelegramClient.transfer_gate = asyncio.Event()
        self.assertFalse(self.frame.progress_gauge.IsShown())
        FakeChooser.values = [""]
        self.frame.send_paths(["report.pdf"])
        # Held half way: the bar is up and the status bar says how far.
        half = self.text(c.MSG_UPLOAD_PROGRESS_FORMAT_KEY).format(percent=50)
        self.assertTrue(pump(lambda: self.status() == half))
        self.assertTrue(self.frame.progress_gauge.IsShown())
        self.assertEqual(self.frame.progress_gauge.GetValue(), 50)

        self.manager.loop.call_soon_threadsafe(gate.set)
        self.assertTrue(pump(lambda: self.calls("send_file") and not self.frame.is_busy))
        self.assertFalse(self.frame.progress_gauge.IsShown())
        self.assertEqual(self.frame.progress_gauge.GetValue(), 0)

    def test_late_report_does_not_bring_the_bar_back(self):
        self.open_chat(0)
        self.frame.show_progress(c.MSG_UPLOAD_PROGRESS_FORMAT_KEY, 80)
        self.assertFalse(self.frame.progress_gauge.IsShown())

    def test_download_shows_progress_too(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(1)
        seen = []
        show = self.frame.show_progress
        self.frame.show_progress = lambda key, percent: (seen.append(percent), show(key, percent))
        with mock.patch.object(wx, "LaunchDefaultApplication"):
            self.frame.on_activate_message(None)
            self.assertTrue(pump(lambda: self.calls("download") and not self.frame.is_busy))
        pump(timeout=0.1)
        # Each whole percent once, though the transfer reported 50% twice.
        self.assertEqual(seen, [50, 100])
        self.assertFalse(self.frame.progress_gauge.IsShown())

    def test_failed_upload_takes_the_bar_down(self):
        self.open_chat(0)
        self.frame.is_busy = True
        self.frame.show_progress(c.MSG_UPLOAD_PROGRESS_FORMAT_KEY, 30)
        self.assertTrue(self.frame.progress_gauge.IsShown())
        self.frame.show_error(c.ERR_CONNECTION_KEY)
        self.assertFalse(self.frame.progress_gauge.IsShown())

    def test_escape_leaves_the_chat_and_keeps_what_was_being_written(self):
        self.open_chat(0)
        self.frame.message_input.SetValue("not sent yet")
        self.assertTrue(self.frame.on_escape())
        self.assertIsNone(self.frame.current_dialog_id)
        self.assertEqual(self.frame.messages_list.GetCount(), 0)
        self.assertEqual(self.frame.message_input.GetValue(), "")
        self.assertFalse(self.frame.message_input.IsEnabled())
        self.assertEqual(self.frame.GetTitle(), self.text(c.MAIN_TITLE_KEY))
        self.assertEqual(self.spoken[-1], self.text(c.MSG_CHAT_CLOSED_KEY))
        # With nothing open, Escape has nothing left to do.
        self.assertFalse(self.frame.on_escape())

        self.open_chat(0)
        self.assertEqual(self.frame.message_input.GetValue(), "not sent yet")

    def on_screen(self):
        """Which of the two screens is showing: the names of its lists that are visible."""
        return {
            name for name in ("dialogs_list", "list_search_btn", "messages_list", "message_input", "search_btn")
            if getattr(self.frame, name).IsShown()
        }

    def test_window_shows_the_list_of_chats_or_the_entered_chat_never_both(self):
        chats, chat = {"dialogs_list", "list_search_btn"}, {"messages_list", "message_input", "search_btn"}
        self.assertEqual(self.on_screen(), chats)
        self.open_chat(0)
        self.assertEqual(self.on_screen(), chat)
        self.assertTrue(self.frame.preview_text.IsShown())
        self.assertFalse(self.frame.cancel_record_btn.IsShown())
        self.frame.on_escape()
        self.assertEqual(self.on_screen(), chats)
        self.assertFalse(self.frame.preview_text.IsShown())

    def test_moving_through_the_list_enters_nothing(self):
        self.frame.dialogs_list.SetSelection(1)
        event = wx.CommandEvent(wx.wxEVT_LISTBOX, self.frame.dialogs_list.GetId())
        self.frame.dialogs_list.ProcessEvent(event)
        pump(timeout=0.6)
        self.assertIsNone(self.frame.current_dialog_id)
        self.assertEqual(self.calls("read"), [])

    def test_search_button_of_each_screen_searches_what_that_screen_shows(self):
        self.frame.on_search_chats(None)
        self.assertEqual(self.menu_labels, [
            self.frame.i18n.get_string(key).partition("	")[0]
            for key in (c.MENU_FIND_KEY, c.MENU_SEARCH_ALL_KEY, c.MENU_GLOBAL_SEARCH_KEY, c.MENU_FIND_CHAT_KEY)
        ])
        self.open_chat(0)
        FakeChooser.values = ["hello"]
        self.frame.on_search_messages_menu(None)
        self.assertTrue(pump(lambda: self.frame.message_view == c.MESSAGE_VIEW_SEARCH))
        self.assertEqual(self.frame.search_btn.GetLabel(), self.text(c.BTN_SEARCH_KEY))

    def test_looking_for_another_chat_goes_back_to_the_list_first(self):
        self.open_chat(0)
        FakeChooser.values = ["Mona"]
        self.frame.on_find_menu(None)
        self.assertIsNone(self.frame.current_dialog_id)
        self.assertEqual(self.on_screen(), {"dialogs_list", "list_search_btn"})
        self.assertEqual(self.frame.dialogs_list.GetSelection(), 1)

        self.open_chat(1)
        self.frame.cycle_view(1)
        self.assertIsNone(self.frame.current_dialog_id)
        self.assertTrue(self.frame.dialogs_list.IsShown())

    def test_chat_that_is_left_for_good_gives_the_list_back(self):
        self.open_chat(0)
        self.frame.on_chat_left(None, self.frame.dialogs[0])
        self.assertEqual(self.on_screen(), {"dialogs_list", "list_search_btn"})
        self.assertEqual(self.frame.dialogs_list.GetCount(), 1)

    def test_transfer_under_way_stays_visible_on_either_screen(self):
        self.open_chat(0)
        self.frame.is_busy = True
        self.frame.show_progress(c.MSG_UPLOAD_PROGRESS_FORMAT_KEY, 30)
        self.frame.close_chat()
        self.assertTrue(self.frame.progress_gauge.IsShown())
        self.open_chat(1)
        self.assertTrue(self.frame.progress_gauge.IsShown())
        self.frame.is_busy = False
        self.frame.hide_progress()

    def test_back_button_is_for_the_mouse_and_tab_passes_it(self):
        self.assertFalse(self.frame.back_btn.AcceptsFocusFromKeyboard())
        self.assertTrue(self.frame.search_btn.AcceptsFocusFromKeyboard())
        self.assertTrue(self.frame.list_search_btn.AcceptsFocusFromKeyboard())

    def test_escape_first_backs_out_of_what_is_in_progress(self):
        self.open_chat(0)
        self.frame.set_compose(reply_to=self.frame.messages[0])
        self.assertTrue(self.frame.on_escape())
        self.assertEqual(self.frame.current_dialog_id, 1)
        self.assertIsNone(self.frame.reply_to)
        self.assertTrue(self.frame.on_escape())
        self.assertIsNone(self.frame.current_dialog_id)
