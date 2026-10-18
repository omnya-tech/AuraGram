"""The rows of buttons for the mouse: in sight for the eyes, out of the way of the keyboard."""
import wx

import core.constants as c
import core.settings as s
from tests.harness import WindowTestCase, make_message, make_user, pump

ALI = make_user(1, "Ali")


class MouseBarsTest(WindowTestCase):
    chats = [(ALI, 0, False)]
    history = {1: [make_message(1, "hello", sender=ALI, chat_id=1)]}

    def button(self, label_key):
        label = self.text(label_key)
        return next(button for button in self.frame.mouse_buttons if button.GetLabel() == label)

    def click(self, button):
        event = wx.CommandEvent(wx.wxEVT_BUTTON, button.GetId())
        event.SetEventObject(button)
        button.ProcessEvent(event)

    def test_tab_passes_them_by_unless_the_short_way_round_is_turned_off(self):
        self.assertTrue(self.frame.mouse_buttons)
        self.assertFalse(any(button.AcceptsFocusFromKeyboard() for button in self.frame.mouse_buttons))
        self.frame.settings.set(s.SETTING_SIMPLE_TAB, False)
        self.frame.apply_simplicity()
        self.open_chat(0)
        shown = [button for button in self.frame.mouse_buttons if button.IsShown()]
        self.assertTrue(shown)
        self.assertTrue(all(button.AcceptsFocusFromKeyboard() for button in shown))

    def test_each_button_tells_its_shortcut(self):
        reply = self.button(c.CONTEXT_REPLY_KEY)
        self.assertEqual(reply.GetToolTipText(), self.text(c.TOOLTIP_COMMAND_FORMAT_KEY).format(
            command=self.text(c.MENU_REPLY_KEY), shortcut="Ctrl+R"
        ))

    def test_a_button_does_what_its_menu_command_does(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(0)
        self.click(self.button(c.CONTEXT_REPLY_KEY))
        self.assertEqual(self.frame.reply_to["id"], 1)

    def test_play_on_a_message_without_sound_says_so(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(0)
        self.click(self.button(c.BTN_PLAY_KEY))
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NOTHING_TO_PLAY_KEY))

    def test_more_opens_the_whole_menu_of_the_message(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(0)
        # Both rows have one; the chat's is the last made.
        more = [button for button in self.frame.mouse_buttons if button.GetLabel() == self.text(c.BTN_MORE_ACTIONS_KEY)]
        self.click(more[-1])
        self.assertIn(self.text(c.CONTEXT_REPLY_KEY), self.menu_labels)

    def test_the_rows_belong_to_their_screens(self):
        new_chat = self.button(c.BTN_NEW_CHAT_KEY)
        reply = self.button(c.CONTEXT_REPLY_KEY)
        self.assertTrue(new_chat.IsShown())
        self.assertFalse(reply.IsShown())
        self.open_chat(0)
        self.assertFalse(new_chat.IsShown())
        self.assertTrue(reply.IsShown())
