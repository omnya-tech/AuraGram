"""Getting around: only up and down move in the lists, a chat opens where reading stopped,
and a message can be reached by its reply, by a date, or by a search through every chat."""
import datetime
from unittest import mock

import wx

import core.constants as c
import core.telegram_client as telegram_client
from tests.harness import FakeChooser, WindowTestCase, make_channel, make_message, make_user, pump

ALI = make_user(1, "Ali")
MONA = make_user(2, "Mona")
NEWS = make_channel(3, "News")
NEWS_ID = telegram_client.get_peer_id(NEWS)
DAY = datetime.datetime(2026, 1, 1, 12, tzinfo=datetime.timezone.utc)


def long_history():
    """Eighty messages, a day apart; the last one answers one far too old to be on the first page."""
    messages = [
        make_message(number, "note %d" % number, sender=MONA, date=DAY + datetime.timedelta(days=number))
        for number in range(1, 80)
    ]
    messages.append(make_message(80, "about note 5", sender=MONA, reply_to_msg_id=5,
                                 date=DAY + datetime.timedelta(days=80)))
    return messages


class NavigationTest(WindowTestCase):
    chats = [(ALI, 2, False), (MONA, 0, False), (NEWS, 0, False)]
    history = {
        1: [
            make_message(1, "old news", sender=ALI),
            make_message(2, "seen that", outgoing=True, reply_to_msg_id=1),
            make_message(3, "fresh one", sender=ALI),
            make_message(4, "fresh two with pineapple", sender=ALI, reply_to_msg_id=1),
        ],
        2: long_history(),
        NEWS_ID: [make_message(1, "headline", post=True)],
    }

    def key(self, code, focused):
        event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        event.SetKeyCode(code)
        with mock.patch.object(wx.Window, "FindFocus", return_value=focused):
            self.frame.on_char_hook(event)
        return event.GetSkipped()

    def rows(self):
        return [self.frame.messages_list.GetString(i) for i in range(self.frame.messages_list.GetCount())]

    def shown_ids(self):
        return [message["id"] for message in self.frame.messages]

    def selected_id(self):
        return self.frame.selected_message()["id"]

    def test_left_and_right_move_nothing_in_the_lists_but_still_work_in_the_message_field(self):
        for sideways in (wx.WXK_LEFT, wx.WXK_RIGHT):
            self.assertFalse(self.key(sideways, self.frame.dialogs_list))
            self.assertFalse(self.key(sideways, self.frame.messages_list))
            self.assertTrue(self.key(sideways, self.frame.message_input))
        for vertical in (wx.WXK_UP, wx.WXK_DOWN):
            self.assertTrue(self.key(vertical, self.frame.dialogs_list))

    def test_chat_with_unread_messages_opens_on_the_first_of_them(self):
        self.open_chat(0)
        self.assertEqual(self.selected_id(), 3)
        self.assertTrue(self.rows()[2].startswith(self.text(c.NEW_FROM_HERE_FORMAT_KEY).format(text="")))
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NEW_MESSAGES_FORMAT_KEY).format(count=2))

        # Read by now: coming back lands on the last message, with nothing marked as new.
        self.frame.on_escape()
        self.open_chat(0)
        self.assertEqual(self.selected_id(), 4)
        self.assertFalse(any(self.text(c.NEW_FROM_HERE_FORMAT_KEY).format(text="") in row for row in self.rows()))

    def test_chat_with_nothing_unread_opens_on_its_last_message(self):
        self.open_chat(1)
        self.assertEqual(self.selected_id(), 80)

    def test_replied_message_on_screen_is_simply_selected(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(3)
        self.frame.on_go_to_reply_menu(None)
        self.assertEqual(self.selected_id(), 1)
        self.assertIsNone(self.frame.message_view)

        self.frame.messages_list.SetSelection(2)
        self.frame.on_go_to_reply_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NOT_A_REPLY_KEY))

    def test_replied_message_far_back_brings_its_part_of_the_conversation(self):
        self.open_chat(1)
        self.assertNotIn(5, self.shown_ids())
        self.frame.on_go_to_reply_menu(None)
        self.assertTrue(pump(lambda: self.frame.message_view == c.MESSAGE_VIEW_AROUND))
        self.assertEqual(self.selected_id(), 5)
        self.assertIn(4, self.shown_ids())
        self.assertIn(6, self.shown_ids())
        self.assertEqual(self.spoken[-1], self.text(c.MSG_JUMPED_KEY))
        # Escape goes back to where the conversation is now.
        self.frame.on_escape()
        self.assertTrue(pump(lambda: self.frame.message_view is None and 80 in self.shown_ids()))
        self.assertEqual(self.frame.current_dialog_id, 2)

    def test_day_typed_in_either_order_opens_the_conversation_from_that_day(self):
        self.open_chat(1)
        for typed in ("2026-01-11", "11/01/2026"):
            FakeChooser.values = [typed]
            self.frame.on_go_to_date_menu(None)
            self.assertTrue(pump(lambda: self.frame.message_view == c.MESSAGE_VIEW_AROUND and not self.frame.is_busy))
            self.assertEqual(self.selected_id(), 10)
            self.assertEqual(self.shown_ids()[0], 10)
            self.frame.on_escape()
            self.assertTrue(pump(lambda: self.frame.message_view is None and not self.frame.is_busy))

    def test_bad_or_too_late_a_date_says_so(self):
        self.open_chat(1)
        FakeChooser.values = ["last tuesday"]
        self.frame.on_go_to_date_menu(None)
        self.assertEqual(self.boxes[-1], self.text(c.ERR_BAD_DATE_KEY))
        FakeChooser.values = ["2030-01-01"]
        self.frame.on_go_to_date_menu(None)
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.text(c.MSG_NOTHING_ON_DATE_KEY)]))
        self.assertIsNone(self.frame.message_view)

    def test_search_through_every_chat_enters_the_chat_of_the_chosen_message(self):
        self.open_chat(1)
        FakeChooser.values = ["pineapple"]
        FakeChooser.selection = 0
        self.frame.on_search_all_menu(None)
        self.assertTrue(pump(lambda: self.frame.current_dialog_id == 1 and len(self.frame.messages) == 4))
        self.assertTrue(pump(lambda: self.selected_id() == 4))
        self.assertIn("Ali", FakeChooser.last_choices[0])
        self.assertIn("pineapple", FakeChooser.last_choices[0])

        FakeChooser.values = ["no such words"]
        self.frame.on_search_all_menu(None)
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.text(c.MSG_SEARCH_NO_RESULTS_KEY)]))

    def test_mentions_are_one_of_the_views_and_opening_it_marks_them_seen(self):
        self.assertIn(c.MESSAGE_VIEW_MENTIONS, c.MESSAGE_VIEWS)
        self.open_chat(1)
        self.frame.open_message_view(c.MESSAGE_VIEW_MENTIONS)
        self.assertTrue(pump(lambda: self.frame.message_view == c.MESSAGE_VIEW_MENTIONS))
        self.assertEqual(len(self.calls("ReadMentionsRequest")), 1)

    def test_message_can_be_sent_without_the_sound(self):
        self.open_chat(1)
        self.frame.message_input.SetValue("quietly")
        self.frame.on_send_message(None, silent=True)
        self.assertTrue(pump(lambda: self.calls("silent") == [("silent", 2, "quietly")]))
        self.assertTrue(pump(lambda: not self.frame.is_busy and self.frame.message_input.IsEnabled()))
        self.frame.message_input.SetValue("normally")
        self.frame.on_send_message(None)
        self.assertTrue(pump(lambda: len(self.calls("send")) == 2))
        self.assertEqual(len(self.calls("silent")), 1)

    def test_own_message_is_deleted_for_all_or_only_on_this_side(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(1)
        FakeChooser.selection = 1
        self.frame.on_delete_menu(None)
        self.assertTrue(pump(lambda: self.calls("delete") == [("delete", 1, [2])]))
        self.assertEqual(self.calls("delete_for_me"), [("delete_for_me", 1, [2])])
        self.assertEqual(FakeChooser.last_choices, [self.text(c.DELETE_FOR_ALL_KEY), self.text(c.DELETE_FOR_ME_KEY)])

    def test_backing_out_of_where_to_delete_deletes_nothing(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(1)
        with mock.patch.object(FakeChooser, "ShowModal", lambda dialog: wx.ID_CANCEL):
            self.frame.on_delete_menu(None)
            pump(timeout=0.2)
        self.assertEqual(self.calls("delete"), [])
        self.assertFalse(self.frame.is_busy)
