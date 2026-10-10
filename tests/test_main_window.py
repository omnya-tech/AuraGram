"""The main window driven end to end against the fake Telegram."""
import asyncio
import unittest
from unittest import mock

import wx

import core.constants as c
import core.telegram_client as telegram_client
from tests.harness import (
    FakeChooser, FakeTelegramClient, Record, WindowTestCase, make_channel, make_message, make_user, pump
)

ALI = make_user(1, "Ali")
NEWS = make_channel(3, "News")
MY_GROUP = make_channel(4, "MyGroup", group=True, creator=True)
OLD = make_user(6, "Old")
NEWS_ID = telegram_client.get_peer_id(NEWS)
GROUP_ID = telegram_client.get_peer_id(MY_GROUP)


def conversation():
    return [
        make_message(1, "first", sender=ALI),
        make_message(2, "mine", outgoing=True, reply_to_msg_id=1),
        make_message(3, "pinned note", sender=ALI, pinned=True),
    ]


class ChatListTest(WindowTestCase):
    chats = [(ALI, 2, False), (NEWS, 5, False), (MY_GROUP, 0, False), (OLD, 0, True)]
    history = {1: conversation()}

    def titles(self):
        return [dialog["title"] for dialog in self.frame.dialogs]

    def show_view(self, index):
        self.frame.view_choice.SetSelection(index)
        self.frame.on_view_changed(None)

    def test_default_view_hides_archived_and_shows_unread_counts(self):
        self.assertEqual(self.titles(), ["Ali", "News", "MyGroup"])
        self.assertIn("2", self.frame.dialogs_list.GetString(0))
        self.assertEqual(self.frame.dialogs_list.GetString(2), "MyGroup")

    def test_views_filter_the_list_and_announce_the_count(self):
        self.show_view(1)
        self.assertEqual(self.titles(), ["Ali", "News"])
        self.assertIn("2", self.spoken[-1])
        self.show_view(2)
        self.assertEqual(self.titles(), ["Old"])

    def test_opening_a_chat_loads_messages_and_marks_it_read(self):
        self.open_chat(0)
        self.assertEqual(self.frame.messages_list.GetCount(), 3)
        self.assertEqual(self.calls("read"), [("read", 1)])
        self.assertEqual(self.frame.dialogs_list.GetString(0), "Ali")

    def test_enter_on_the_chat_list_opens_the_selected_chat(self):
        self.frame.dialogs_list.SetSelection(0)
        self.frame.dialogs_list.SetFocus()
        with mock.patch.object(wx.Window, "FindFocus", return_value=self.frame.dialogs_list):
            self.assertTrue(self.press(wx.WXK_RETURN))
        self.assertTrue(pump(lambda: self.frame.current_dialog_id == 1))

    def test_context_menu_matches_the_chat(self):
        self.frame.dialogs_list.SetSelection(1)
        self.frame.on_dialog_context_menu(self.context_event(self.frame.dialogs_list))
        self.assertIn(self.text(c.CONTEXT_MARK_READ_KEY), self.menu_labels)
        self.assertEqual(self.menu_labels[-1], self.text(c.CONTEXT_LEAVE_KEY))
        self.frame.dialogs_list.SetSelection(2)
        self.frame.on_dialog_context_menu(self.context_event(self.frame.dialogs_list))
        self.assertNotIn(self.text(c.CONTEXT_MARK_READ_KEY), self.menu_labels)
        self.frame.dialogs_list.SetSelection(0)
        self.frame.on_dialog_context_menu(self.context_event(self.frame.dialogs_list))
        self.assertEqual(self.menu_labels[-1], self.text(c.CONTEXT_DELETE_CHAT_KEY))

    def test_leaving_needs_confirmation_and_removes_the_chat(self):
        news = self.frame.dialogs[1]
        self.box_answer = wx.NO
        self.frame.leave_chat(news, False)
        self.assertEqual(self.calls("leave"), [])
        self.box_answer = wx.YES
        self.frame.leave_chat(news, False)
        self.assertTrue(pump(lambda: news not in self.frame.all_dialogs))
        self.assertEqual(self.calls("leave"), [("leave", NEWS_ID)])
        self.assertEqual(self.titles(), ["Ali", "MyGroup"])

    def test_find_jumps_to_a_matching_chat_and_wraps(self):
        self.frame.find_text = "my"
        self.frame.find_dialog(0)
        self.assertEqual(self.frame.dialogs_list.GetSelection(), 2)
        self.frame.find_dialog(3)
        self.assertEqual(self.frame.dialogs_list.GetSelection(), 2)
        self.frame.find_text = "zzz"
        self.frame.find_dialog(0)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NOT_FOUND_KEY))

    def incoming(self, entity, message_id, text="live"):
        async def value(result):
            return result
        event = Record(
            chat_id=telegram_client.get_peer_id(entity),
            get_sender=lambda: value(None), get_chat=lambda: value(entity), get_input_chat=lambda: value(None),
            message=make_message(message_id, text)
        )
        asyncio.run_coroutine_threadsafe(self.manager.client.handlers["NewMessage"](event), self.manager.loop)

    def test_new_message_elsewhere_raises_unread_and_moves_the_chat_up(self):
        self.incoming(MY_GROUP, 50)
        self.assertTrue(pump(lambda: self.titles()[0] == "MyGroup"))
        self.assertIn("1", self.frame.dialogs_list.GetString(0))
        self.assertIn("MyGroup", self.spoken[-1])

    def test_new_message_in_the_open_chat_is_appended_and_read(self):
        self.open_chat(0)
        self.incoming(ALI, 60, "hello again")
        self.assertTrue(pump(lambda: self.frame.messages_list.GetCount() == 4))
        self.assertIn("hello again", self.frame.messages_list.GetString(3))
        self.assertEqual(self.frame.find_known_dialog(1)["unread"], 0)

    def test_message_to_a_chat_hidden_by_the_view_stays_out_of_the_list(self):
        self.show_view(2)
        self.incoming(NEWS, 70)
        self.assertTrue(pump(lambda: self.frame.find_known_dialog(NEWS_ID)["unread"] == 6))
        self.assertEqual(self.titles(), ["Old"])


class MessagesTest(WindowTestCase):
    chats = [(ALI, 0, False), (MY_GROUP, 0, False)]
    history = {1: conversation(), GROUP_ID: [make_message(1, "theirs", sender=ALI)]}

    def setUp(self):
        super().setUp()
        self.open_chat(0)
        self.messages = self.frame.messages_list

    def test_messages_read_with_sender_reply_quote_and_pin_mark(self):
        self.assertTrue(self.messages.GetString(0).startswith("Ali: first"))
        self.assertIn("رداً على Ali «first»", self.messages.GetString(1))
        self.assertIn("مثبتة", self.messages.GetString(2))

    def test_send_appears_in_the_list_and_clears_the_field(self):
        self.frame.message_input.SetValue("  new one  ")
        self.frame.on_send_message(None)
        self.assertTrue(pump(lambda: self.messages.GetCount() == 4 and self.frame.send_btn.IsEnabled()))
        self.assertEqual(self.calls("send")[-1][2:4], ("new one", None))
        self.assertEqual(self.frame.message_input.GetValue(), "")

    def test_reply_is_sent_as_a_reply_and_escape_cancels_it(self):
        self.messages.SetSelection(0)
        self.frame.on_reply_menu(None)
        self.assertEqual(self.frame.reply_to["id"], 1)
        self.assertTrue(self.press(wx.WXK_ESCAPE))
        self.assertIsNone(self.frame.reply_to)
        self.frame.on_reply_menu(None)
        self.frame.message_input.SetValue("answer")
        self.frame.on_send_message(None)
        self.assertTrue(pump(lambda: self.calls("send") and self.frame.reply_to is None))
        self.assertEqual(self.calls("send")[-1][2:4], ("answer", 1))

    def test_only_own_text_can_be_edited(self):
        self.messages.SetSelection(0)
        self.frame.on_edit_menu(None)
        self.assertIsNone(self.frame.editing)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_CANNOT_EDIT_KEY))
        self.messages.SetSelection(1)
        self.frame.on_edit_menu(None)
        self.assertEqual(self.frame.message_input.GetValue(), "mine")
        self.frame.message_input.SetValue("mine, fixed")
        self.frame.on_send_message(None)
        self.assertTrue(pump(lambda: "mine, fixed" in self.messages.GetString(1)))
        self.assertEqual(self.calls("edit"), [("edit", 2, "mine, fixed")])
        self.assertEqual(self.calls("send"), [])

    def test_delete_asks_first_and_refuses_other_peoples_messages(self):
        self.messages.SetSelection(0)
        self.frame.on_delete_menu(None)
        self.assertEqual(self.boxes, [])
        self.assertEqual(self.spoken[-1], self.text(c.MSG_CANNOT_DELETE_KEY))
        self.messages.SetSelection(1)
        self.box_answer = wx.NO
        self.frame.on_delete_menu(None)
        self.assertEqual(self.calls("delete"), [])
        self.box_answer = wx.YES
        self.frame.on_delete_menu(None)
        self.assertTrue(pump(lambda: self.messages.GetCount() == 2))
        self.assertEqual(self.calls("delete"), [("delete", 1, [2])])

    def test_owner_may_delete_members_messages_and_is_told_whose(self):
        self.open_chat(1)
        self.frame.messages_list.SetSelection(0)
        self.frame.on_delete_menu(None)
        self.assertIn("Ali", self.boxes[-1])
        self.assertTrue(pump(lambda: self.frame.messages_list.GetCount() == 0))

    def test_context_menu_offers_only_what_works(self):
        self.messages.SetSelection(0)
        self.frame.on_message_context_menu(self.context_event(self.messages))
        self.assertNotIn(self.text(c.CONTEXT_EDIT_KEY), self.menu_labels)
        self.assertNotIn(self.text(c.CONTEXT_DELETE_KEY), self.menu_labels)
        self.assertIn(self.text(c.CONTEXT_COPY_KEY), self.menu_labels)
        self.messages.SetSelection(1)
        self.frame.on_message_context_menu(self.context_event(self.messages))
        for key in (c.CONTEXT_REPLY_KEY, c.CONTEXT_EDIT_KEY, c.CONTEXT_DELETE_KEY, c.CONTEXT_FORWARD_KEY):
            self.assertIn(self.text(key), self.menu_labels)

    def test_pin_toggles(self):
        self.messages.SetSelection(2)
        self.frame.on_pin_menu(None)
        self.assertTrue(pump(lambda: self.calls("unpin") == [("unpin", 3)]))
        self.assertTrue(pump(lambda: "مثبتة" not in self.messages.GetString(2)))

    def test_forward_goes_to_the_chosen_chat(self):
        self.messages.SetSelection(0)
        FakeChooser.selection = 1
        self.frame.on_forward_menu(None)
        self.assertTrue(pump(lambda: self.calls("forward") == [("forward", GROUP_ID, 1, 1)]))
        self.assertEqual(FakeChooser.last_choices, ["Ali", "MyGroup"])

    def test_search_shows_results_and_escape_returns(self):
        FakeChooser.values = ["pinned"]
        self.frame.on_search_messages_menu(None)
        self.assertTrue(pump(lambda: self.frame.message_view == c.MESSAGE_VIEW_SEARCH and self.messages.GetCount() == 1))
        self.assertTrue(self.press(wx.WXK_ESCAPE))
        self.assertTrue(pump(lambda: self.frame.message_view is None and self.messages.GetCount() == 3))

    def test_pinned_view(self):
        self.frame.open_message_view(c.MESSAGE_VIEW_PINNED)
        self.assertTrue(pump(lambda: self.frame.message_view == c.MESSAGE_VIEW_PINNED))
        self.assertEqual(self.messages.GetCount(), 1)

    def test_empty_view_keeps_the_conversation(self):
        self.frame.open_message_view(c.MESSAGE_VIEW_SCHEDULED)
        self.assertTrue(pump(lambda: not self.frame.is_busy))
        self.assertIsNone(self.frame.message_view)
        self.assertEqual(self.messages.GetCount(), 3)

    def test_scheduled_messages_can_only_be_cancelled(self):
        FakeTelegramClient.scheduled = {1: [make_message(900, "later", outgoing=True)]}
        self.frame.open_message_view(c.MESSAGE_VIEW_SCHEDULED)
        self.assertTrue(pump(lambda: self.frame.message_view == c.MESSAGE_VIEW_SCHEDULED))
        self.messages.SetSelection(0)
        for handler in (self.frame.on_reply_menu, self.frame.on_edit_menu, self.frame.on_pin_menu,
                        self.frame.on_forward_menu, self.frame.on_react_menu):
            handler(None)
        self.assertIsNone(self.frame.reply_to)
        self.assertEqual(self.calls("pin") + self.calls("forward"), [])
        self.frame.on_delete_menu(None)
        self.assertTrue(pump(lambda: self.messages.GetCount() == 0))
        self.assertEqual(self.calls("delete"), [])
        self.assertEqual(self.calls("DeleteScheduledMessagesRequest")[0][1].id, [900])

    def test_scheduling_needs_text_and_a_valid_time(self):
        self.frame.on_schedule_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NOTHING_TO_SCHEDULE_KEY))
        self.frame.message_input.SetValue("later")
        FakeChooser.values = ["nonsense"]
        self.frame.on_schedule_menu(None)
        self.assertEqual(self.boxes, [self.text(c.ERR_BAD_TIME_KEY)])
        self.assertEqual(self.frame.message_input.GetValue(), "later")
        FakeChooser.values = ["23:59"]
        self.frame.on_schedule_menu(None)
        self.assertTrue(pump(lambda: self.calls("send")))
        scheduled_for = self.calls("send")[-1][4]
        self.assertEqual((scheduled_for.hour, scheduled_for.minute), (23, 59))
        self.assertIsNotNone(scheduled_for.tzinfo)
        self.assertEqual(self.messages.GetCount(), 3)

    def test_live_edit_and_delete_update_the_open_chat(self):
        self.frame.on_message_edited(1, dict(self.frame.messages[0], text="first, edited"))
        self.assertIn("first, edited", self.messages.GetString(0))
        self.assertIn("first, edited", self.messages.GetString(1))
        self.frame.on_messages_deleted(None, [1])
        self.assertEqual(self.messages.GetCount(), 2)
        self.assertNotIn("رداً على", self.messages.GetString(0))


class MarkingTest(WindowTestCase):
    chats = [(ALI, 0, False), (MY_GROUP, 0, False)]
    history = {1: [
        make_message(1, "theirs", sender=ALI),
        make_message(2, "mine one", outgoing=True),
        make_message(3, "mine two", outgoing=True),
    ]}

    def setUp(self):
        super().setUp()
        self.open_chat(0)
        self.messages = self.frame.messages_list

    def mark(self, *rows):
        for row in rows:
            self.messages.SetSelection(row)
            self.frame.on_mark_menu(None)

    def test_mark_is_read_first_and_toggles(self):
        self.mark(1)
        self.assertTrue(self.messages.GetString(1).startswith("محددة."))
        self.assertEqual(self.messages.GetSelection(), 1)
        self.assertIn("1", self.spoken[-1])
        self.mark(1)
        self.assertFalse(self.messages.GetString(1).startswith("محددة."))

    def test_escape_clears_marks_before_anything_else(self):
        self.mark(1, 2)
        self.assertTrue(self.press(wx.WXK_ESCAPE))
        self.assertEqual(self.frame.marked, set())
        self.assertEqual(self.spoken[-1], self.text(c.MSG_MARKS_CLEARED_KEY))

    def test_delete_takes_all_marked_in_one_request(self):
        self.mark(1, 2)
        self.frame.on_delete_menu(None)
        self.assertIn("2", self.boxes[-1])
        self.assertTrue(pump(lambda: self.messages.GetCount() == 1))
        self.assertEqual(self.calls("delete"), [("delete", 1, [2, 3])])
        self.assertEqual(self.frame.marked, set())

    def test_delete_refuses_if_any_marked_message_is_not_deletable(self):
        self.mark(0, 1)
        self.frame.on_delete_menu(None)
        self.assertEqual(self.boxes, [])
        self.assertEqual(self.calls("delete"), [])
        self.assertEqual(self.spoken[-1], self.text(c.MSG_CANNOT_DELETE_SOME_KEY))

    def test_forward_sends_marked_messages_in_chat_order(self):
        self.mark(2, 0)
        FakeChooser.selection = 1
        self.frame.on_forward_menu(None)
        self.assertTrue(pump(lambda: self.calls("forward") == [("forward", GROUP_ID, [1, 3], 1)]))
        self.assertTrue(pump(lambda: self.frame.marked == set()))

    def test_copy_joins_marked_texts(self):
        self.mark(0, 2)
        self.frame.on_copy_message(None)
        data = wx.TextDataObject()
        wx.TheClipboard.Open()
        wx.TheClipboard.GetData(data)
        wx.TheClipboard.Close()
        self.assertEqual(data.GetText().splitlines(), ["theirs", "mine two"])

    def test_marks_do_not_survive_switching_chats(self):
        self.mark(1)
        self.open_chat(1)
        self.assertEqual(self.frame.marked, set())


class DraftAndReadingTest(WindowTestCase):
    chats = [(ALI, 0, False), (MY_GROUP, 0, False)]
    history = {1: [make_message(1, "line one\nline two", sender=ALI), make_message(2, "mine", outgoing=True)]}

    def test_unsent_text_is_kept_per_chat(self):
        self.open_chat(0)
        self.frame.message_input.SetValue("half written")
        self.open_chat(1)
        self.assertEqual(self.frame.message_input.GetValue(), "")
        self.frame.message_input.SetValue("for the group")
        self.open_chat(0)
        self.assertEqual(self.frame.message_input.GetValue(), "half written")
        self.open_chat(1)
        self.assertEqual(self.frame.message_input.GetValue(), "for the group")

    def test_sending_clears_the_draft(self):
        self.open_chat(0)
        self.frame.message_input.SetValue("send me")
        self.frame.on_send_message(None)
        self.assertTrue(pump(lambda: self.calls("send") and self.frame.send_btn.IsEnabled()))
        self.open_chat(1)
        self.open_chat(0)
        self.assertEqual(self.frame.message_input.GetValue(), "")

    def test_text_of_a_message_being_edited_is_not_saved_as_a_draft(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(1)
        self.frame.on_edit_menu(None)
        self.assertEqual(self.frame.message_input.GetValue(), "mine")
        self.open_chat(1)
        self.open_chat(0)
        self.assertEqual(self.frame.message_input.GetValue(), "")

    def shown_text(self, action):
        shown = []

        class CapturingDialog:
            def __init__(self, parent, i18n, title, text):
                shown.append((title, text))

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def ShowModal(self):
                return wx.ID_CANCEL

        with mock.patch("ui.main_frame.TextDialog", CapturingDialog):
            action(None)
        return shown[0]

    def test_reading_a_message_in_full_keeps_its_line_breaks(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(0)
        title, text = self.shown_text(self.frame.on_read_message_menu)
        self.assertEqual(title, self.text(c.READ_MESSAGE_TITLE_KEY))
        self.assertIn("Ali", text.splitlines()[0])
        self.assertEqual(text.splitlines()[-2:], ["line one", "line two"])

    def test_shortcut_list_mentions_every_menu_shortcut(self):
        _, text = self.shown_text(self.frame.on_shortcuts_menu)
        menu_bar = self.frame.GetMenuBar()
        shortcuts = []
        for menu, _ in menu_bar.GetMenus():
            for item in menu.GetMenuItems():
                accelerator = item.GetItemLabel().partition("\t")[2]
                if accelerator and accelerator != "Alt+F4":
                    shortcuts.append(accelerator)
        self.assertGreater(len(shortcuts), 15)
        self.assertEqual([shortcut for shortcut in shortcuts if shortcut not in text], [])


class NewChatTest(WindowTestCase):
    chats = [(ALI, 0, False)]

    def test_creating_a_group_opens_it(self):
        FakeChooser.values = ["Book Club", "We read"]
        self.frame.create_chat(is_channel=False)
        self.assertTrue(pump(lambda: self.calls("CreateChannelRequest")))
        request = self.calls("CreateChannelRequest")[0][1]
        self.assertEqual((request.title, request.about, request.megagroup, request.broadcast),
                         ("Book Club", "We read", True, False))
        self.assertTrue(pump(lambda: self.frame.current_dialog_id is not None and self.frame.current_dialog_id != 1))
        self.assertEqual(self.frame.dialogs[self.frame.dialogs_list.GetSelection()]["title"], "Book Club")

    def test_a_channel_is_created_as_broadcast_and_description_may_be_empty(self):
        FakeChooser.values = ["Announcements", ""]
        self.frame.create_chat(is_channel=True)
        self.assertTrue(pump(lambda: self.calls("CreateChannelRequest")))
        request = self.calls("CreateChannelRequest")[0][1]
        self.assertEqual((request.about, request.megagroup, request.broadcast), ("", False, True))

    def test_empty_name_creates_nothing(self):
        FakeChooser.values = ["   "]
        self.frame.create_chat(is_channel=False)
        pump(timeout=0.2)
        self.assertEqual(self.calls("CreateChannelRequest"), [])


class LongHistoryTest(WindowTestCase):
    chats = [(ALI, 0, False)]
    history = {1: [make_message(i, "m%d" % i, outgoing=True) for i in range(1, 121)]}

    def test_older_messages_load_in_pages_until_the_start(self):
        self.open_chat(0)
        messages = self.frame.messages_list
        self.assertEqual(messages.GetCount(), 51)
        self.assertEqual(messages.GetString(0), self.text(c.MSG_LOAD_OLDER_KEY))
        messages.SetSelection(0)
        self.frame.on_activate_message(None)
        self.assertTrue(pump(lambda: messages.GetCount() == 101))
        self.assertIn("m70،", messages.GetString(messages.GetSelection()))
        messages.SetSelection(0)
        self.frame.on_activate_message(None)
        self.assertTrue(pump(lambda: messages.GetCount() == 120))
        self.assertIn("m1،", messages.GetString(0))
        self.assertEqual(len(self.calls("read")), 1)


if __name__ == "__main__":
    unittest.main()
