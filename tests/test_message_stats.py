"""A post's numbers said with one shortcut, wherever the settings put them on its row."""
from unittest import mock

import wx

import core.constants as c
from tests.harness import Record, WindowTestCase, make_channel, make_message

NEWS = make_channel(41, "News")


class MessageStatsTest(WindowTestCase):
    chats = [(NEWS, 0, False)]
    history = {-1000000000041: [
        make_message(1, "launch day", sender=NEWS, post=True, views=950, forwards=12,
                     replies=Record(comments=True, replies=3)),
        make_message(2, "no numbers", sender=NEWS),
    ]}

    def test_views_comments_and_forwards_are_said_at_once(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(0)
        self.frame.on_message_stats_menu(None)
        said = self.spoken[-1]
        self.assertIn(self.text(c.VIEWS_FORMAT_KEY).format(count=950), said)
        self.assertIn(self.text(c.COMMENTS_FORMAT_KEY).format(count=3), said)
        self.assertIn(self.text(c.AUDIENCE_FORWARDS_FORMAT_KEY).format(count=12), said)

    def test_a_message_without_numbers_says_so(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(1)
        self.frame.on_message_stats_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NO_MESSAGE_STATS_KEY))

    def test_the_context_menu_offers_the_numbers_and_the_comments(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(0)
        self.frame.on_message_context_menu(self.context_event(self.frame.messages_list))
        self.assertIn(self.text(c.CONTEXT_MESSAGE_STATS_KEY), self.menu_labels)
        self.assertIn(self.text(c.CONTEXT_COMMENTS_KEY), self.menu_labels)

    def test_new_numbers_show_on_their_row_without_opening_the_chat_again(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(1)
        self.frame.on_message_numbers(self.frame.current_dialog_id, {1: {"views": 1234, "forwards": 15}})
        self.assertIn(self.text(c.VIEWS_FORMAT_KEY).format(count=1234), self.frame.messages_list.GetString(0))
        # A message without numbers is left as it was.
        self.assertNotIn("1234", self.frame.messages_list.GetString(1))
        # Another chat's numbers are no business of this one.
        self.frame.on_message_numbers(-1000000000099, {1: {"views": 5}})
        self.assertIn("1234", self.frame.messages_list.GetString(0))

    def numbers_arrive(self, views, screen_reader, active=True):
        messages = self.frame.messages_list
        with mock.patch.object(wx.Window, "FindFocus", return_value=messages),                 mock.patch("core.speech.screen_reader_running", return_value=screen_reader),                 mock.patch.object(self.frame, "IsActive", return_value=active):
            self.frame.on_message_numbers(self.frame.current_dialog_id, {1: {"views": views}})

    def test_for_the_eyes_the_row_one_is_on_changes_with_each_new_view(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(0)
        self.numbers_arrive(2000, screen_reader=False)
        self.assertIn(self.text(c.VIEWS_FORMAT_KEY).format(count=2000), self.frame.messages_list.GetString(0))
        self.numbers_arrive(2001, screen_reader=False)
        self.assertIn(self.text(c.VIEWS_FORMAT_KEY).format(count=2001), self.frame.messages_list.GetString(0))

    def test_with_a_screen_reader_the_new_number_is_said_and_not_the_whole_post_again(self):
        self.open_chat(0)
        messages = self.frame.messages_list
        messages.SetSelection(0)
        before = messages.GetString(0)
        spoken = len(self.spoken)
        self.numbers_arrive(2000, screen_reader=True)
        # Said, the number alone: a row whose words change is read out again, post and all.
        self.assertEqual(self.spoken[spoken:], [self.text(c.VIEWS_FORMAT_KEY).format(count=2000)])
        self.assertEqual(messages.GetString(0), before)
        # Nothing new, nothing said; and a channel left open in another window says nothing at all.
        self.numbers_arrive(2000, screen_reader=True)
        self.numbers_arrive(2001, screen_reader=True, active=False)
        self.assertEqual(len(self.spoken), spoken + 1)
        # Its numbers are current where they are asked for, and its row once the selection moves.
        self.frame.on_message_stats_menu(None)
        self.assertIn(self.text(c.VIEWS_FORMAT_KEY).format(count=2001), self.spoken[-1])
        messages.SetSelection(1)
        self.frame.update_preview()
        self.assertIn("2001", messages.GetString(0))

    def test_told_it_is_asked_too_often_it_rests_a_while(self):
        self.open_chat(0)
        self.frame.on_numbers_answer(self.frame.current_dialog_id, None, c.ERR_FLOOD_KEY)
        with mock.patch.object(self.frame, "IsShown", return_value=True):
            self.frame.ask_live_numbers()
        self.assertEqual(self.calls("GetMessagesViewsRequest"), [])

    def test_the_open_channel_is_asked_for_its_numbers_without_counting_a_view(self):
        from tests.harness import FakeTelegramClient, pump
        self.open_chat(0)
        FakeTelegramClient.live_views = {1: 1500}
        with mock.patch.object(self.frame, "IsShown", return_value=True):
            self.frame.ask_live_numbers()
        self.assertTrue(pump(lambda: "1500" in self.frame.messages_list.GetString(0)))
        request = self.calls("GetMessagesViewsRequest")[-1][1]
        # Only posts are asked about, and asking is not reading: no view is added by it.
        self.assertEqual(request.id, [1])
        self.assertFalse(request.increment)

    def test_nothing_is_asked_while_the_window_is_hidden(self):
        self.open_chat(0)
        with mock.patch.object(self.frame, "IsShown", return_value=False):
            self.frame.ask_live_numbers()
        self.assertEqual(self.calls("GetMessagesViewsRequest"), [])

    def press_on_messages(self, code):
        event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        event.SetKeyCode(code)
        with mock.patch.object(wx.Window, "FindFocus", return_value=self.frame.messages_list):
            self.frame.on_char_hook(event)

    def test_right_says_the_numbers_and_left_goes_into_the_comments(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(0)
        # Arabic reads right to left: right is back, left is forward, into the post.
        self.press_on_messages(wx.WXK_RIGHT)
        self.assertIn(self.text(c.VIEWS_FORMAT_KEY).format(count=950), self.spoken[-1])
        with mock.patch.object(self.frame, "open_thread") as open_thread:
            self.press_on_messages(wx.WXK_LEFT)
        self.assertEqual(open_thread.call_args[0][0]["id"], 1)


class NumbersSentByTelegramTest(MessageStatsTest.__base__):
    """What Telegram sends of its own accord when a post's numbers change reaches the window as they do."""
    chats = []

    def test_views_and_forwards_updates_become_one_event(self):
        import asyncio
        from telethon.tl import types
        import core.telegram_client as telegram_client
        told = []
        stub = mock.Mock(message_listener=lambda *details: told.append(details))
        asyncio.run(telegram_client.TelegramManager._on_numbers(
            stub, types.UpdateChannelMessageViews(channel_id=41, id=1, views=77)
        ))
        asyncio.run(telegram_client.TelegramManager._on_numbers(
            stub, types.UpdateChannelMessageForwards(channel_id=41, id=1, forwards=4)
        ))
        self.assertEqual(told, [
            (c.EVENT_MESSAGE_NUMBERS, -1000000000041, {1: {"views": 77}}),
            (c.EVENT_MESSAGE_NUMBERS, -1000000000041, {1: {"forwards": 4}}),
        ])
