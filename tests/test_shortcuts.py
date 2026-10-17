"""Keyboard shortcuts the user chooses: the table of them, the settings tab, and what else on the computer holds one."""
import os
import struct
import tempfile
import unittest
from unittest import mock

import wx

import core.constants as c
import core.key_conflicts as key_conflicts
import core.settings as s
import core.shortcuts as shortcuts
from tests.harness import WindowTestCase, get_app, make_user
from ui.settings_dialog import SettingsDialog
from ui.shortcut_dialog import ShortcutDialog

ALI = make_user(1, "Ali")


def key_event(key_code, control=False, alt=False, shift=False):
    event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
    event.SetKeyCode(key_code)
    event.SetControlDown(control)
    event.SetAltDown(alt)
    event.SetShiftDown(shift)
    return event


class ShortcutTextTest(unittest.TestCase):
    def setUp(self):
        get_app()

    def test_every_command_starts_with_a_shortcut_of_its_own_that_it_may_have(self):
        table = shortcuts.defaults()
        self.assertEqual(len(set(table.values())), len(table))
        for command, text in table.items():
            self.assertEqual(shortcuts.normalize(text), text)
            self.assertIsNone(shortcuts.refusal(text, command), text)

    def test_a_shortcut_is_written_one_way_however_it_came(self):
        self.assertEqual(shortcuts.normalize("shift+ctrl+s"), "Ctrl+Shift+S")
        self.assertEqual(shortcuts.normalize("alt + pgdn"), "Alt+PgDn")
        for not_one in ("", "Ctrl+", "Ctrl+Ctrl+A", "Hyper+A", "Ctrl+A+B"):
            self.assertEqual(shortcuts.normalize(not_one), "")

    def test_a_key_press_reads_as_its_shortcut(self):
        self.assertEqual(shortcuts.from_key_event(key_event(ord("K"), control=True, shift=True)), "Ctrl+Shift+K")
        self.assertEqual(shortcuts.from_key_event(key_event(wx.WXK_NUMPAD_ENTER, alt=True)), "Alt+Enter")
        self.assertEqual(shortcuts.from_key_event(key_event(wx.WXK_F6)), "F6")
        self.assertEqual(shortcuts.from_key_event(key_event(wx.WXK_CONTROL, control=True)), "")

    def test_what_may_not_be_a_shortcut_and_why(self):
        command = c.MENU_REPLY_KEY
        self.assertEqual(shortcuts.refusal("Ctrl+C", command), c.ERR_SHORTCUT_RESERVED_FORMAT_KEY)
        self.assertEqual(shortcuts.refusal("Alt+F4", command), c.ERR_SHORTCUT_RESERVED_FORMAT_KEY)
        self.assertEqual(shortcuts.refusal("A", command), c.ERR_SHORTCUT_MODIFIER_KEY)
        self.assertEqual(shortcuts.refusal("Shift+A", command), c.ERR_SHORTCUT_MODIFIER_KEY)
        self.assertEqual(shortcuts.refusal("Alt+F", command), c.ERR_SHORTCUT_MENU_FORMAT_KEY)
        self.assertIsNone(shortcuts.refusal("F6", command))
        self.assertIsNone(shortcuts.refusal("Alt+7", command))
        # Alone, an F key would be taken from every other program too.
        self.assertEqual(shortcuts.refusal("F6", c.SHORTCUT_SHOW_WINDOW), c.ERR_SHORTCUT_MODIFIER_KEY)

    def test_windows_and_wx_are_told_the_same_keys(self):
        self.assertEqual(shortcuts.windows_hotkey("Ctrl+Alt+Shift+A"), (0x7, ord("A")))
        self.assertEqual(shortcuts.wx_hotkey("Ctrl+Alt+Shift+A"), (wx.MOD_CONTROL | wx.MOD_ALT | wx.MOD_SHIFT, ord("A")))
        self.assertEqual(shortcuts.windows_hotkey("F2"), (0, 0x71))


class StoredShortcutsTest(unittest.TestCase):
    def setUp(self):
        get_app()
        patch = mock.patch.object(s, "SETTINGS_FILE", os.path.join(tempfile.mkdtemp(), "settings.json"))
        patch.start()
        self.addCleanup(patch.stop)

    def test_only_what_the_user_changed_is_saved(self):
        settings = s.Settings()
        table = shortcuts.current(settings)
        self.assertEqual(table, shortcuts.defaults())
        table[c.MENU_REPLY_KEY] = "Ctrl+Alt+F7"
        table[c.MENU_EDIT_KEY] = ""
        shortcuts.store(settings, table)
        settings.save()
        saved = s.Settings()
        self.assertEqual(saved.get(s.SETTING_SHORTCUTS), {c.MENU_REPLY_KEY: "Ctrl+Alt+F7", c.MENU_EDIT_KEY: ""})
        self.assertEqual(shortcuts.current(saved)[c.MENU_REPLY_KEY], "Ctrl+Alt+F7")
        self.assertEqual(shortcuts.current(saved)[c.MENU_EDIT_KEY], "")
        self.assertEqual(shortcuts.current(saved)[c.MENU_PIN_KEY], "Ctrl+T")

    def test_a_command_that_is_gone_or_a_damaged_entry_is_passed_over(self):
        settings = s.Settings()
        settings.set(s.SETTING_SHORTCUTS, {"MENU_OF_LONG_AGO": "Ctrl+Alt+F7", c.MENU_REPLY_KEY: "nonsense"})
        table = shortcuts.current(settings)
        self.assertNotIn("MENU_OF_LONG_AGO", table)
        self.assertEqual(table[c.MENU_REPLY_KEY], "")


class KeyConflictsTest(unittest.TestCase):
    def setUp(self):
        get_app()

    def link(self, folder, name, vk_code, flags):
        header = bytearray(key_conflicts.LINK_HEADER_SIZE)
        struct.pack_into("<I", header, 0, key_conflicts.LINK_HEADER_SIZE)
        struct.pack_into("<BB", header, key_conflicts.LINK_HOTKEY_OFFSET, vk_code, flags)
        with open(os.path.join(folder, name), "wb") as link_file:
            link_file.write(header)

    def test_shortcut_files_are_read_for_the_keys_that_start_them(self):
        folder = tempfile.mkdtemp()
        os.mkdir(os.path.join(folder, "Programs"))
        self.link(folder, "Reader.lnk", ord("N"), 0x02 | 0x04)
        self.link(os.path.join(folder, "Programs"), "Plain.lnk", 0, 0)
        self.link(os.path.join(folder, "Programs"), "Notes.LNK", 0x71, 0x01)
        with open(os.path.join(folder, "broken.lnk"), "wb") as link_file:
            link_file.write(b"not a shortcut file")
        self.assertEqual(key_conflicts.link_hotkeys([folder]), {"Ctrl+Alt+N": "Reader", "Shift+F2": "Notes"})

    def test_a_shortcut_file_is_named_and_a_running_program_is_not(self):
        with mock.patch.object(key_conflicts, "link_hotkeys", lambda: {"Ctrl+Alt+N": "Reader"}), \
                mock.patch.object(key_conflicts, "taken_by_a_program", lambda text: text == "Ctrl+Shift+S"), \
                mock.patch.object(key_conflicts, "own_hotkeys", {"Ctrl+Alt+Shift+A"}):
            found = key_conflicts.find(["Ctrl+Alt+N", "Ctrl+Shift+S", "Ctrl+R", "", "Ctrl+Alt+Shift+A"])
        self.assertEqual(found, {"Ctrl+Alt+N": "Reader", "Ctrl+Shift+S": ""})

    def test_windows_refuses_a_hot_key_that_is_held_and_gives_a_free_one(self):
        user32 = key_conflicts.ctypes.WinDLL("user32", use_last_error=True)
        modifiers, vk_code = shortcuts.windows_hotkey("Ctrl+Alt+Shift+F11")
        if not user32.RegisterHotKey(None, 1, modifiers, vk_code):
            self.skipTest("another program on this machine holds the combination the test uses")
        try:
            # Held by this very test, which Windows does not tell apart from another program.
            self.assertTrue(key_conflicts.taken_by_a_program("Ctrl+Alt+Shift+F11"))
            with mock.patch.object(key_conflicts, "own_hotkeys", {"Ctrl+Alt+Shift+F11"}):
                self.assertFalse(key_conflicts.taken_by_a_program("Ctrl+Alt+Shift+F11"))
        finally:
            user32.UnregisterHotKey(None, 1)
        self.assertFalse(key_conflicts.taken_by_a_program("Ctrl+Alt+Shift+F11"))


class ShortcutsWindowTest(WindowTestCase):
    chats = [(ALI, 0, False)]

    def settings_dialog(self):
        dialog = SettingsDialog(self.frame, self.i18n, self.frame.settings, self.manager)
        self.addCleanup(dialog.Destroy)
        return dialog

    def select(self, dialog, command):
        dialog.shortcuts_list.SetSelection(shortcuts.COMMANDS.index(command))

    def row(self, dialog, command):
        return dialog.shortcuts_list.GetString(shortcuts.COMMANDS.index(command))

    def menu_accelerators(self):
        return {
            command: item.GetItemLabel().partition("\t")[2] for command, item in self.frame.menu_items.items()
        }

    def test_every_menu_entry_has_a_shortcut_and_shows_it(self):
        entries = [item for menu, _ in self.frame.GetMenuBar().GetMenus() for item in menu.GetMenuItems()
                   if not item.IsSeparator()]
        self.assertEqual(len(entries), len(self.frame.menu_items))
        self.assertEqual(set(self.frame.menu_items) | {c.SHORTCUT_SHOW_WINDOW}, set(shortcuts.COMMANDS))
        table = shortcuts.defaults()
        for command, accelerator in self.menu_accelerators().items():
            self.assertEqual(accelerator, table[command])
            self.assertTrue(self.frame.menu_items[command].GetAccel().IsOk())

    def test_settings_list_every_command_with_its_shortcut(self):
        dialog = self.settings_dialog()
        self.assertEqual(dialog.shortcuts_list.GetCount(), len(shortcuts.COMMANDS))
        self.assertEqual(
            self.row(dialog, c.MENU_REPLY_KEY),
            self.text(c.SHORTCUT_ROW_FORMAT_KEY).format(
                command=self.text(c.MENU_REPLY_KEY), shortcut="Ctrl+R"
            )
        )
        self.assertIn(c.SHOW_HOTKEY_TEXT, self.row(dialog, c.SHORTCUT_SHOW_WINDOW))
        # No row carries the mark that opens a menu by its letter.
        self.assertEqual([row for row in dialog.shortcuts_list.GetStrings() if "&" in row], [])

    def test_a_changed_shortcut_reaches_the_menu_and_stays_after_a_restart(self):
        dialog = self.settings_dialog()
        self.select(dialog, c.MENU_REPLY_KEY)
        with mock.patch.object(dialog, "ask_shortcut", lambda command: "Ctrl+Alt+F7"):
            dialog.on_change_shortcut(None)
        self.assertIn("Ctrl+Alt+F7", self.row(dialog, c.MENU_REPLY_KEY))
        self.assertIn("Ctrl+Alt+F7", self.spoken[-1])
        # Nothing changes outside the dialog until it is accepted.
        self.assertEqual(self.menu_accelerators()[c.MENU_REPLY_KEY], "Ctrl+R")
        dialog.apply_app_settings()
        self.frame.apply_shortcuts()
        self.assertEqual(self.menu_accelerators()[c.MENU_REPLY_KEY], "Ctrl+Alt+F7")
        self.assertEqual(shortcuts.current(s.Settings())[c.MENU_REPLY_KEY], "Ctrl+Alt+F7")

    def test_a_shortcut_another_command_has_is_moved_only_if_the_user_agrees(self):
        dialog = self.settings_dialog()
        self.select(dialog, c.MENU_REPLY_KEY)
        self.box_answer = wx.NO
        with mock.patch.object(dialog, "ask_shortcut", lambda command: "Ctrl+E"):
            dialog.on_change_shortcut(None)
        self.assertIn(self.text(c.MENU_EDIT_KEY), self.boxes[-1])
        self.assertEqual(dialog.shortcut_table[c.MENU_REPLY_KEY], "Ctrl+R")
        self.assertEqual(dialog.shortcut_table[c.MENU_EDIT_KEY], "Ctrl+E")
        self.box_answer = wx.YES
        with mock.patch.object(dialog, "ask_shortcut", lambda command: "Ctrl+E"):
            dialog.on_change_shortcut(None)
        self.assertEqual(dialog.shortcut_table[c.MENU_REPLY_KEY], "Ctrl+E")
        self.assertEqual(dialog.shortcut_table[c.MENU_EDIT_KEY], "")
        self.assertIn(self.text(c.SHORTCUT_NONE_KEY), self.row(dialog, c.MENU_EDIT_KEY))

    def test_a_shortcut_another_program_holds_brings_a_message_to_change_it(self):
        dialog = self.settings_dialog()
        self.select(dialog, c.MENU_REPLY_KEY)
        pressed = ["Ctrl+Alt+F6", "Ctrl+Alt+F7"]
        held = {"Ctrl+Alt+F6": "Reader"}
        find = lambda texts: {text: held[text] for text in texts if text in held}
        # Yes to "choose another": the user is asked again, and the second one is free.
        with mock.patch.object(key_conflicts, "find", find), \
                mock.patch.object(dialog, "ask_shortcut", lambda command: pressed.pop(0)):
            dialog.on_change_shortcut(None)
        self.assertEqual(len(self.boxes), 1)
        self.assertIn("Ctrl+Alt+F6", self.boxes[0])
        self.assertIn("Reader", self.boxes[0])
        self.assertEqual(dialog.shortcut_table[c.MENU_REPLY_KEY], "Ctrl+Alt+F7")
        # No: it is kept all the same, and its row says who else has it.
        self.box_answer = wx.NO
        with mock.patch.object(key_conflicts, "find", find), \
                mock.patch.object(dialog, "ask_shortcut", lambda command: "Ctrl+Alt+F6"):
            dialog.on_change_shortcut(None)
        self.assertEqual(dialog.shortcut_table[c.MENU_REPLY_KEY], "Ctrl+Alt+F6")
        self.assertIn("Reader", self.row(dialog, c.MENU_REPLY_KEY))

    def test_shortcuts_already_there_are_looked_for_in_windows_too(self):
        held = {"Ctrl+Shift+S": "", "Ctrl+Alt+Shift+A": "Reader"}
        find = lambda texts: {text: held[text] for text in texts if text in held}
        with mock.patch.object(key_conflicts, "find", find):
            dialog = self.settings_dialog()
            self.assertIn(self.text(c.SHORTCUT_CONFLICT_PROGRAM_KEY), self.row(dialog, c.MENU_SETTINGS_KEY))
            self.assertIn("Reader", self.row(dialog, c.SHORTCUT_SHOW_WINDOW))
            self.assertNotIn(self.text(c.SHORTCUT_CONFLICT_PROGRAM_KEY), self.row(dialog, c.MENU_REPLY_KEY))
            dialog.on_check_shortcuts(None)
        self.assertIn("Ctrl+Shift+S", self.boxes[-1])
        self.assertIn(self.text(c.MENU_SETTINGS_KEY), self.boxes[-1])
        self.assertIn("Reader", self.boxes[-1])
        dialog.on_check_shortcuts(None)
        self.assertEqual(self.boxes[-1], self.text(c.MSG_SHORTCUTS_NO_CONFLICTS_KEY))

    def test_removing_and_restoring(self):
        dialog = self.settings_dialog()
        self.select(dialog, c.MENU_REPLY_KEY)
        dialog.on_remove_shortcut(None)
        self.assertEqual(dialog.shortcut_table[c.MENU_REPLY_KEY], "")
        dialog.on_default_shortcut(None)
        self.assertEqual(dialog.shortcut_table[c.MENU_REPLY_KEY], "Ctrl+R")
        dialog.on_remove_shortcut(None)
        self.select(dialog, c.MENU_EDIT_KEY)
        dialog.on_remove_shortcut(None)
        dialog.on_default_shortcuts(None)
        self.assertEqual(dialog.shortcut_table, shortcuts.defaults())
        self.assertEqual(self.spoken[-1], self.text(c.MSG_SHORTCUTS_DEFAULTS_KEY))
        self.assertEqual(dialog.shortcuts_list.GetSelection(), shortcuts.COMMANDS.index(c.MENU_EDIT_KEY))

    def test_a_command_left_without_a_shortcut_shows_none_in_the_menu_or_the_help(self):
        table = shortcuts.defaults()
        table[c.MENU_REPLY_KEY] = ""
        table[c.MENU_EDIT_KEY] = "Ctrl+Alt+F7"
        shortcuts.store(self.frame.settings, table)
        self.frame.apply_shortcuts()
        self.assertEqual(self.frame.menu_items[c.MENU_REPLY_KEY].GetItemLabel(), self.text(c.MENU_REPLY_KEY))
        self.assertIsNone(self.frame.menu_items[c.MENU_REPLY_KEY].GetAccel())
        text = self.frame.shortcuts_text()
        self.assertIn(self.text(c.SHORTCUTS_HELP_LINE_FORMAT_KEY).format(
            shortcut="Ctrl+Alt+F7", command=self.text(c.MENU_EDIT_KEY)
        ), text)
        self.assertNotIn(self.text(c.MENU_REPLY_KEY), text)
        self.assertIn(c.SHOW_HOTKEY_TEXT, text)

    def test_enter_with_other_keys_sends_unless_a_menu_entry_has_that_shortcut(self):
        self.open_chat(0)
        sent = []
        self.frame.on_send_message = lambda event, silent=False: sent.append(self.frame.message_input.GetValue())
        self.frame.message_input.SetValue("hello")

        def press_alt_enter():
            with mock.patch.object(wx.Window, "FindFocus", return_value=self.frame.message_input):
                self.frame.ProcessEvent(key_event(wx.WXK_RETURN, alt=True))

        # The menu's own way of sending without a sound: not for the field to act on.
        press_alt_enter()
        self.assertEqual(sent, [])
        table = shortcuts.defaults()
        table[c.MENU_SEND_SILENT_KEY] = ""
        shortcuts.store(self.frame.settings, table)
        self.frame.apply_shortcuts()
        press_alt_enter()
        self.assertEqual(sent, ["hello"])

    def test_the_way_back_from_any_program_follows_the_setting(self):
        asked = []
        self.frame.on_hotkey_changed = lambda hotkey: asked.append(hotkey) or hotkey != "Ctrl+Alt+F9"
        table = shortcuts.defaults()

        def choose(hotkey):
            table[c.SHORTCUT_SHOW_WINDOW] = hotkey

            class Chosen(SettingsDialog):
                def ShowModal(dialog):
                    dialog.shortcut_table = dict(table)
                    return wx.ID_OK
            with mock.patch("ui.main_frame.SettingsDialog", Chosen):
                self.frame.open_settings()

        choose("Ctrl+Alt+F8")
        self.assertEqual(asked, ["Ctrl+Alt+F8"])
        self.assertEqual([box for box in self.boxes if "Ctrl+Alt+F8" in box], [])
        self.frame.Close()
        self.assertIn("Ctrl+Alt+F8", self.spoken[-1])
        # Windows gave the next one to somebody else: the user is told so.
        choose("Ctrl+Alt+F9")
        self.assertEqual(self.boxes[-1], self.text(c.ERR_HOTKEY_TAKEN_FORMAT_KEY).format(hotkey="Ctrl+Alt+F9"))
        # Left without one, the tray icon is the way back.
        choose("")
        self.frame.Close()
        self.assertEqual(self.spoken[-1], self.text(c.MSG_IN_BACKGROUND_KEY))

    def test_conflicts_are_told_once_at_the_start_with_an_offer_to_change_them(self):
        opened = []
        self.frame.open_settings = lambda on_shortcuts=False: opened.append(on_shortcuts)
        held = {"Ctrl+Shift+S": ""}
        with mock.patch.object(key_conflicts, "find", lambda texts: dict(held)):
            self.frame.check_shortcuts_once()
            self.assertEqual(len(self.boxes), 1)
            self.assertIn("Ctrl+Shift+S", self.boxes[0])
            self.assertEqual(opened, [True])
            # Not again in this run, and not at the next start while nothing new turned up.
            self.frame.check_shortcuts_once()
            self.frame.shortcuts_checked = False
            self.frame.check_shortcuts_once()
            self.assertEqual(len(self.boxes), 1)
            held["Ctrl+R"] = "Reader"
            self.frame.shortcuts_checked = False
            self.frame.check_shortcuts_once()
            self.assertEqual(len(self.boxes), 2)

    def test_pressing_keys_in_the_capture_window(self):
        dialog = ShortcutDialog(self.frame, self.i18n, "Reply", c.MENU_REPLY_KEY)
        self.addCleanup(dialog.Destroy)
        dialog.on_char_hook(key_event(wx.WXK_CONTROL, control=True))
        self.assertEqual(self.spoken, [])
        dialog.on_char_hook(key_event(ord("P"), control=True, alt=True))
        self.assertEqual((dialog.shortcut, dialog.field.GetValue(), self.spoken[-1]), ("Ctrl+Alt+P",) * 3)
        dialog.on_char_hook(key_event(ord("C"), control=True))
        self.assertEqual(dialog.shortcut, "")
        self.assertEqual(self.spoken[-1], self.text(c.ERR_SHORTCUT_RESERVED_FORMAT_KEY).format(shortcut="Ctrl+C"))
        dialog.on_char_hook(key_event(ord("P")))
        self.assertEqual(self.spoken[-1], self.text(c.ERR_SHORTCUT_MODIFIER_KEY))
        dialog.on_char_hook(key_event(wx.WXK_NUMPAD5, control=True))
        self.assertEqual(self.spoken[-1], self.text(c.ERR_SHORTCUT_KEY_KEY))
        dialog.on_char_hook(key_event(wx.WXK_F6))
        self.assertEqual(dialog.shortcut, "F6")
