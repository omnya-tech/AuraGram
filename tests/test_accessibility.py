"""The accessibility settings, the wider menu bar, and the plainer window."""
import asyncio
import json
import os
import tempfile
import unittest
from unittest import mock

import wx

import core.constants as c
import core.settings as s
import core.telegram_client as telegram_client
import ui.live_updates
from tests.harness import FakeChooser, Record, WindowTestCase, make_message, make_user, pump
from ui.background import connection_news_key
from ui.settings_dialog import SettingsDialog

ALI = make_user(1, "Ali")
MONA = make_user(2, "Mona")
OMAR = make_user(3, "Omar")


class AccessibilityTest(WindowTestCase):
    chats = [(ALI, 0, False), (MONA, 2, False), (OMAR, 0, False)]
    history = {1: [make_message(1, "first", sender=ALI)]}

    def incoming(self, entity, message_id):
        async def value(result):
            return result
        event = Record(
            chat_id=telegram_client.get_peer_id(entity),
            get_sender=lambda: value(entity), get_chat=lambda: value(entity), get_input_chat=lambda: value(None),
            message=make_message(message_id, "live")
        )
        asyncio.run_coroutine_threadsafe(self.manager.client.handlers["NewMessage"](event), self.manager.loop)
        self.assertTrue(pump(lambda: self.frame.find_known_dialog(event.chat_id)["last_message"]["id"] == message_id))

    def in_front(self, active):
        return mock.patch.multiple(
            type(self.frame), IsShown=mock.Mock(return_value=active), IsActive=mock.Mock(return_value=active)
        )

    def test_messages_are_spoken_only_where_the_setting_says(self):
        message_id = 100
        for when, active, expected in (
            (c.ANNOUNCE_WHEN_ALWAYS, True, 1), (c.ANNOUNCE_WHEN_ALWAYS, False, 1),
            (c.ANNOUNCE_WHEN_FOREGROUND, True, 1), (c.ANNOUNCE_WHEN_FOREGROUND, False, 0),
            (c.ANNOUNCE_WHEN_BACKGROUND, True, 0), (c.ANNOUNCE_WHEN_BACKGROUND, False, 1),
        ):
            self.frame.settings.set(s.SETTING_ANNOUNCE_WHEN, when)
            del self.spoken[:]
            message_id += 1
            with self.in_front(active):
                self.incoming(OMAR, message_id)
            self.assertEqual(len(self.spoken), expected, (when, active))

    def test_sender_only_leaves_the_text_out(self):
        self.incoming(OMAR, 70)
        self.assertIn("live", self.spoken[-1])
        self.frame.settings.set(s.SETTING_ANNOUNCE_WHAT, c.ANNOUNCE_WHAT_SENDER)
        self.incoming(OMAR, 71)
        self.assertIn("Omar", self.spoken[-1])
        self.assertNotIn("live", self.spoken[-1])

    def test_interrupting_and_braille_follow_their_settings(self):
        speak = mock.Mock()
        with mock.patch.object(ui.live_updates, "speak", speak), \
                mock.patch.object(ui.live_updates.speech, "braille") as braille:
            self.incoming(OMAR, 80)
            speak.assert_called_once_with(mock.ANY)
            braille.assert_not_called()
            self.frame.settings.set(s.SETTING_ANNOUNCE_INTERRUPT, True)
            self.frame.settings.set(s.SETTING_BRAILLE_MESSAGES, True)
            # Braille is its own channel: it shows the message even with speech turned off.
            self.frame.settings.set(s.SETTING_ANNOUNCE_MESSAGES, False)
            self.incoming(OMAR, 81)
            self.assertEqual(speak.call_count, 1)
            braille.assert_called_once()
            self.frame.settings.set(s.SETTING_ANNOUNCE_MESSAGES, True)
            self.incoming(OMAR, 82)
            speak.assert_called_with(mock.ANY, interrupt=True)

    def test_passing_remarks_can_be_kept_to_the_status_bar(self):
        self.frame.notify(c.MSG_NO_UNREAD_KEY)
        self.assertEqual(self.spoken, [self.text(c.MSG_NO_UNREAD_KEY)])
        self.frame.settings.set(s.SETTING_SPEAK_FEEDBACK, False)
        self.frame.notify(c.MSG_NO_CHAT_SELECTED_KEY)
        self.assertEqual(len(self.spoken), 1)
        self.assertEqual(self.frame.GetStatusBar().GetStatusText(), self.text(c.MSG_NO_CHAT_SELECTED_KEY))

    def test_tab_skips_the_view_box_and_the_send_button(self):
        optional = (self.frame.view_choice, self.frame.send_btn)
        self.assertEqual([control.AcceptsFocusFromKeyboard() for control in optional], [False] * 2)
        # Attaching and recording have no other place in the window, so Tab still reaches them.
        for control in (self.frame.dialogs_list, self.frame.attach_btn, self.frame.record_btn):
            self.assertTrue(control.AcceptsFocusFromKeyboard())
        self.frame.settings.set(s.SETTING_SIMPLE_TAB, False)
        self.frame.apply_simplicity()
        self.assertTrue(self.frame.view_choice.AcceptsFocusFromKeyboard())

    def test_preview_box_can_be_taken_away(self):
        self.open_chat(0)
        self.assertTrue(self.frame.preview_text.IsShown())
        self.frame.settings.set(s.SETTING_SHOW_PREVIEW, False)
        self.frame.apply_simplicity()
        self.assertFalse(self.frame.preview_text.IsShown())
        self.assertFalse(self.frame.preview_label.IsShown())

    def test_settings_tab_keeps_what_is_chosen(self):
        dialog = SettingsDialog(self.frame, self.i18n, self.frame.settings, self.manager)
        self.addCleanup(dialog.Destroy)
        dialog.choices[s.SETTING_ANNOUNCE_WHEN].SetSelection(c.ANNOUNCE_WHEN_OPTIONS.index(c.ANNOUNCE_WHEN_BACKGROUND))
        dialog.choices[s.SETTING_ANNOUNCE_WHAT].SetSelection(c.ANNOUNCE_WHAT_OPTIONS.index(c.ANNOUNCE_WHAT_SENDER))
        dialog.checkboxes[s.SETTING_BRAILLE_MESSAGES].SetValue(True)
        dialog.apply_app_settings()
        saved = s.Settings()
        self.assertEqual(saved.get(s.SETTING_ANNOUNCE_WHEN), c.ANNOUNCE_WHEN_BACKGROUND)
        self.assertEqual(saved.get(s.SETTING_ANNOUNCE_WHAT), c.ANNOUNCE_WHAT_SENDER)
        self.assertTrue(saved.get(s.SETTING_BRAILLE_MESSAGES))
        # Every on/off setting has a box somewhere in the dialog. Every list setting has a drop-down,
        # the language one shown by its own name rather than through the shared choices dict.
        self.assertEqual(set(dialog.checkboxes), set(s.DEFAULTS))
        self.assertEqual(set(dialog.choices), set(s.CHOICES) - {s.SETTING_LANGUAGE})
        self.assertEqual(dialog.language_choice.GetCount(), len(c.LANGUAGES))

    def test_next_unread_opens_it_and_says_when_there_is_none(self):
        self.frame.dialogs_list.SetSelection(0)
        self.frame.on_next_unread_menu(None)
        self.assertTrue(pump(lambda: self.frame.current_dialog_id == 2))
        self.frame.find_known_dialog(2)["unread"] = 0
        self.frame.on_next_unread_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NO_UNREAD_KEY))

    def test_views_can_be_walked_from_the_keyboard(self):
        self.frame.cycle_view(1)
        self.assertEqual(self.frame.views[self.frame.view_index].label, self.text("VIEW_UNREAD"))
        self.assertEqual(len(self.frame.dialogs), 1)
        self.frame.cycle_view(-1)
        self.frame.cycle_view(-1)
        self.assertEqual(self.frame.view_index, len(self.frame.views) - 1)

    def test_chat_entries_of_the_menu_bar_act_on_the_selected_chat(self):
        self.frame.dialogs_list.SetSelection(1)
        self.frame.on_chat_menu(self.frame.toggle_dialog_read)
        self.assertEqual(self.frame.find_known_dialog(2)["unread"], 0)
        FakeChooser.selection = 1
        self.frame.on_chat_menu(self.frame.toggle_dialog_muted)
        self.assertTrue(pump(lambda: self.frame.find_known_dialog(2)["muted"]))
        self.assertEqual(FakeChooser.last_choices, [self.text(key) for _, key in c.MUTE_DURATIONS])

        self.frame.dialogs_list.SetSelection(wx.NOT_FOUND)
        self.frame.on_chat_menu(self.frame.toggle_dialog_read)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NO_CHAT_SELECTED_KEY))

    def test_every_menu_shortcut_is_used_once(self):
        shortcuts = [
            item.GetItemLabel().partition("\t")[2]
            for menu, _ in self.frame.GetMenuBar().GetMenus() for item in menu.GetMenuItems()
        ]
        shortcuts = [shortcut for shortcut in shortcuts if shortcut]
        self.assertEqual(sorted(shortcuts), sorted(set(shortcuts)))

    def test_connection_state_is_told_on_request(self):
        self.assertTrue(pump(lambda: self.manager.connection_state == c.CONNECTION_ONLINE))
        self.frame.on_connection_menu(None)
        self.assertIn(self.text(c.CONNECTION_STATE_KEYS[c.CONNECTION_ONLINE]), self.spoken[-1])


class ConnectionNewsTest(unittest.TestCase):
    def test_only_losing_the_line_and_getting_it_back_are_news(self):
        self.assertIsNone(connection_news_key(None, c.CONNECTION_ONLINE))
        self.assertEqual(connection_news_key(None, c.CONNECTION_OFFLINE), c.MSG_CONNECTION_LOST_KEY)
        self.assertEqual(connection_news_key(c.CONNECTION_ONLINE, c.CONNECTION_OFFLINE), c.MSG_CONNECTION_LOST_KEY)
        self.assertEqual(connection_news_key(c.CONNECTION_OFFLINE, c.CONNECTION_ONLINE), c.MSG_CONNECTION_BACK_KEY)


class ChoiceSettingsTest(unittest.TestCase):
    def test_unknown_stored_choice_falls_back_to_the_default(self):
        path = os.path.join(tempfile.mkdtemp(), "settings.json")
        with open(path, "w") as file:
            json.dump({s.SETTING_ANNOUNCE_WHEN: "sometimes", s.SETTING_ANNOUNCE_WHAT: c.ANNOUNCE_WHAT_SENDER}, file)
        with mock.patch.object(s, "SETTINGS_FILE", path):
            settings = s.Settings()
        self.assertEqual(settings.get(s.SETTING_ANNOUNCE_WHEN), c.ANNOUNCE_WHEN_ALWAYS)
        self.assertEqual(settings.get(s.SETTING_ANNOUNCE_WHAT), c.ANNOUNCE_WHAT_SENDER)

    def test_every_choice_and_tone_has_its_text(self):
        from core.i18n import I18NManager
        strings = I18NManager("ar").strings
        for setting, (options, default) in s.CHOICES.items():
            self.assertIn(default, options)
            if setting == s.SETTING_LANGUAGE:
                continue  # the language codes are shown by autonym, not by a locale string
            for option in options:
                self.assertIn(option, strings)
        for name in c.SOUND_NAMES:
            self.assertIn(c.SOUND_LABEL_KEY_PREFIX + name, strings)
            self.assertTrue(os.path.exists(os.path.join(c.SOUNDS_DIR, name + ".wav")), name)
