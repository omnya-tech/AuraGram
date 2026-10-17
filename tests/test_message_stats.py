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
