"""The chat views as a row of tabs: all in sight for the eyes, one stop and the arrows for the keyboard."""
from unittest import mock

import wx
from telethon.tl import types

import core.constants as c
import core.settings as s
from tests.harness import FakeTelegramClient, WindowTestCase, make_channel, make_user, pump

ALI = make_user(1, "Ali")
OLD = make_channel(40, "Old")
NEWS = make_channel(41, "Team news")
FRIENDS = make_channel(42, "Friends", group=True)


class ViewTabsTest(WindowTestCase):
    chats = [(ALI, 1, False), (OLD, 0, True), (NEWS, 0, False), (FRIENDS, 0, False)]

    def tabs(self):
        return self.frame.view_tabs

    def labels(self):
        return [button.GetLabel() for button in self.tabs().buttons]

    def pressed(self):
        return [button.GetValue() for button in self.tabs().buttons]

    def click(self, index):
        button = self.tabs().buttons[index]
        # What wx does on a click, before telling the program.
        button.SetValue(not button.GetValue())
        event = wx.CommandEvent(wx.wxEVT_TOGGLEBUTTON, button.GetId())
        event.SetEventObject(button)
        button.ProcessEvent(event)

    def press(self, key, focused=None, **modifiers):
        event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        event.SetKeyCode(key)
        event.SetControlDown(modifiers.get("control", False))
        focused = self.tabs().buttons[self.tabs().GetSelection()] if focused is None else focused
        with mock.patch.object(wx.Window, "FindFocus", return_value=focused), \
                mock.patch.object(wx.ToggleButton, "SetFocus"):
            return self.frame.ProcessEvent(event)

    def test_every_view_is_a_tab_in_sight_with_the_current_one_pressed(self):
        self.assertEqual(self.labels(), [self.text(key) for key in (
            c.VIEW_ALL_KEY, c.VIEW_UNREAD_KEY, c.VIEW_ARCHIVE_KEY, c.VIEW_CHANNELS_KEY, c.VIEW_GROUPS_KEY,
            c.VIEW_CONTACTS_KEY
        )])
        self.assertEqual(self.pressed(), [True, False, False, False, False, False])
        self.assertTrue(self.tabs().IsShown())
        weights = [button.GetFont().GetWeight() for button in self.tabs().buttons]
        self.assertEqual(weights, [wx.FONTWEIGHT_BOLD] + [wx.FONTWEIGHT_NORMAL] * 5)

    def test_one_click_goes_to_a_view_and_says_what_is_in_it(self):
        self.click(2)
        self.assertEqual(self.frame.view_index, 2)
        self.assertEqual(self.pressed(), [False, False, True, False, False, False])
        self.assertEqual([dialog["title"] for dialog in self.frame.dialogs], ["Old"])
        self.assertIn(self.text(c.VIEW_ARCHIVE_KEY), self.spoken[-1])

    def test_clicking_the_current_tab_leaves_it_pressed_and_reloads_nothing(self):
        self.spoken.clear()
        self.click(0)
        self.assertEqual(self.pressed(), [True, False, False, False, False, False])
        self.assertEqual(self.spoken, [])

    def test_keyboard_shortcut_moves_the_pressed_tab_too(self):
        self.frame.cycle_view(1)
        self.assertEqual(self.pressed(), [False, True, False, False, False, False])
        self.frame.cycle_view(-1)
        self.frame.cycle_view(-1)
        self.assertEqual(self.pressed(), [False, False, False, False, False, True])

    def test_arrows_on_a_tab_go_to_its_neighbours_the_way_they_look(self):
        # Arabic reads right to left: the next tab is to the left.
        self.assertTrue(self.press(wx.WXK_LEFT))
        self.assertEqual(self.frame.view_index, 1)
        self.press(wx.WXK_RIGHT)
        self.assertEqual(self.frame.view_index, 0)
        self.press(wx.WXK_DOWN)
        self.assertEqual(self.frame.view_index, 1)
        self.press(wx.WXK_UP)
        self.press(wx.WXK_UP)
        self.assertEqual(self.frame.view_index, len(self.frame.views) - 1)

    def test_channels_and_groups_each_have_a_tab_of_their_own(self):
        self.click(3)
        self.assertEqual([dialog["title"] for dialog in self.frame.dialogs], ["Team news"])
        self.click(4)
        self.assertEqual([dialog["title"] for dialog in self.frame.dialogs], ["Friends"])

    def test_left_and_right_in_the_chat_list_go_to_the_tab_beside(self):
        # Arabic reads right to left: the next tab is to the left.
        self.assertTrue(self.press(wx.WXK_LEFT, focused=self.frame.dialogs_list))
        self.assertEqual(self.frame.view_index, 1)
        self.press(wx.WXK_RIGHT, focused=self.frame.dialogs_list)
        self.press(wx.WXK_RIGHT, focused=self.frame.dialogs_list)
        self.assertEqual(self.frame.view_index, len(self.frame.views) - 1)
        self.assertIn(self.text(c.VIEW_CONTACTS_KEY), self.frame.views[self.frame.view_index].label)

    def test_arrows_elsewhere_and_shortcuts_with_modifiers_are_not_the_tabs_business(self):
        self.assertFalse(self.tabs().handle_key(self.key(wx.WXK_LEFT), self.frame.dialogs_list))
        self.assertFalse(self.tabs().handle_key(self.key(wx.WXK_LEFT, control=True), self.tabs().buttons[0]))
        self.assertFalse(self.tabs().handle_key(self.key(ord("A")), self.tabs().buttons[0]))
        self.assertEqual(self.frame.view_index, 0)

    def key(self, code, control=False):
        event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        event.SetKeyCode(code)
        event.SetControlDown(control)
        return event

    def test_strip_is_one_stop_for_tab_or_none_with_the_short_way_round(self):
        # The short way round (the default) passes the tabs by: Ctrl+PgDn is one key away.
        self.assertFalse(self.tabs().AcceptsFocusFromKeyboard())
        self.frame.settings.set(s.SETTING_SIMPLE_TAB, False)
        self.frame.apply_simplicity()
        stops = [button.AcceptsFocusFromKeyboard() for button in self.tabs().buttons]
        self.assertEqual(stops, [True, False, False, False, False, False])
        self.frame.cycle_view(1)
        stops = [button.AcceptsFocusFromKeyboard() for button in self.tabs().buttons]
        self.assertEqual(stops, [False, True, False, False, False, False])

    def test_folders_get_tabs_of_their_own_and_keep_the_choice_made(self):
        self.frame.cycle_view(1)
        FakeTelegramClient.folders = [types.DialogFilter(
            id=5, title=types.TextWithEntities("Work", []), contacts=True,
            pinned_peers=[], include_peers=[], exclude_peers=[]
        )]
        self.manager.load_folders(self.frame.on_ui_thread(self.frame.show_folders))
        self.assertTrue(pump(lambda: len(self.tabs().buttons) == 7))
        self.assertIn("Work", self.labels()[6])
        self.assertEqual(self.pressed(), [False, True, False, False, False, False, False])
        # Made after the settings were applied, the new tabs follow them all the same.
        self.assertFalse(self.tabs().buttons[6].AcceptsFocusFromKeyboard())

    def test_tabs_leave_the_screen_with_the_list_of_chats(self):
        self.frame.dialogs_list.SetSelection(0)
        self.frame.on_open_dialog(None)
        self.assertTrue(pump(lambda: self.frame.current_dialog_id == 1))
        self.assertFalse(self.tabs().IsShown())
        self.frame.close_chat()
        self.assertTrue(self.tabs().IsShown())

    def test_current_tab_stands_out_in_every_theme(self):
        from ui.themes import contrast_ratio
        for theme in (c.THEME_DARK, c.THEME_SEPIA, c.THEME_HIGH_CONTRAST):
            self.frame.settings.set(s.SETTING_THEME, theme)
            self.frame.apply_colours()
            self.frame.cycle_view(1)
            current = self.tabs().buttons[self.tabs().GetSelection()]
            other = self.tabs().buttons[self.tabs().GetSelection() - 1]
            # Unlike its neighbours, and still readable itself.
            self.assertNotEqual(current.GetBackgroundColour(), other.GetBackgroundColour(), theme)
            self.assertGreaterEqual(contrast_ratio(current.GetBackgroundColour(), other.GetBackgroundColour()), 3, theme)
            self.assertGreaterEqual(contrast_ratio(current.GetBackgroundColour(), current.GetForegroundColour()), 4.5, theme)
            self.assertGreaterEqual(contrast_ratio(other.GetBackgroundColour(), other.GetForegroundColour()), 4.5, theme)
        # Back under Windows' own colours nothing is forced: its pressed look does the telling.
        self.frame.settings.set(s.SETTING_THEME, c.THEME_SYSTEM)
        self.frame.apply_colours()
        self.assertEqual(
            self.tabs().buttons[self.tabs().GetSelection()].GetBackgroundColour(),
            self.tabs().buttons[self.tabs().GetSelection() - 1].GetBackgroundColour()
        )


class WindowsForTheEyesTest(WindowTestCase):
    """What a ruler and a pair of eyes found on a tour of the windows."""

    chats = [(make_channel(31, "Team", group=True, creator=True), 0, False)]

    def test_chat_control_shows_every_button_whole_in_both_languages(self):
        from core.i18n import I18NManager
        from ui.chat_control_dialog import ChatControlDialog
        for language in c.LANGUAGES:
            dialog = ChatControlDialog(self.frame, I18NManager(language), self.manager, self.frame.dialogs[0])
            self.addCleanup(dialog.Destroy)
            dialog.Layout()
            dialog.SendSizeEvent()
            pump(timeout=0.1)
            area = dialog.GetClientSize()
            buttons = [child for child in dialog.GetChildren() if isinstance(child, wx.Button)]
            self.assertEqual(len(buttons), 7)
            for button in buttons:
                rect = button.GetRect()
                self.assertGreaterEqual(rect.width, button.GetBestSize().width, (language, button.GetLabel()))
                self.assertLessEqual(rect.GetRight(), area.width, (language, button.GetLabel()))
                self.assertLessEqual(rect.GetBottom(), area.height, (language, button.GetLabel()))

    def test_wx_words_its_own_buttons_in_the_interface_language(self):
        from ui.layout import use_interface_language
        self.addCleanup(wx.Translations.Set, wx.Translations())
        use_interface_language("en")
        self.assertEqual(wx.GetStockLabel(wx.ID_CANCEL), "Cancel")
        use_interface_language("ar")
        self.assertNotEqual(wx.GetStockLabel(wx.ID_CANCEL), "Cancel")
        self.assertNotIn("OK", wx.GetStockLabel(wx.ID_OK))
