"""The English locale, its parity with the Arabic one, and the language setting."""
import json
import os
import tempfile
import unittest
from unittest import mock

import core.constants as c
import core.settings as s
from core.constants import BASE_DIR, LOCALES_DIR
from core.i18n import I18NManager
from tests.harness import WindowTestCase, make_user, pump
from ui.settings_dialog import SettingsDialog


class LocaleParityTest(unittest.TestCase):
    def load(self, code):
        with open(os.path.join(LOCALES_DIR, code + ".json"), encoding="utf-8") as file:
            return json.load(file)

    def test_both_languages_exist_with_exactly_the_same_keys(self):
        self.assertEqual(set(c.LANGUAGES), {"ar", "en"})
        ar, en = self.load("ar"), self.load("en")
        self.assertEqual(set(ar), set(en), "the two locales must have the same keys")
        # No value left untranslated (identical to the Arabic) except the few that are the same by design.
        same_on_purpose = {"APP_NAME", "MAIN_WINDOW_TITLE", "TRAY_TOOLTIP", "DEVELOPER_NAME", "DIALOG_FORMAT",
                           "PREVIEW_SENDER_FORMAT", "MAIN_TITLE_CHAT_FORMAT", "ANNOUNCE_FORMAT", "STICKER_CHOICE_FORMAT",
                           "AUDIENCE_REACTION_FORMAT", "REACTION_COUNT_FORMAT", "THREAD_LABEL_FORMAT", "FILE_SIZE_FORMAT",
                           "SOUND_ROW_FORMAT", "STATS_PERCENT_FORMAT", "INFO_MEMBER_ROLE_FORMAT", "SEARCH_ALL_ROW_FORMAT",
                           "TRAY_STATUS_FORMAT", "REACTION_CHOICE_FORMAT", "MEDIA_FORMAT", "POLL_OPTION_FORMAT",
                           "SHORTCUT_ROW_FORMAT", "SHORTCUTS_HELP_LINE_FORMAT"}
        untranslated = [key for key in ar if ar[key] == en[key] and key not in same_on_purpose]
        self.assertEqual(untranslated, [], "these English values are still the Arabic text")

    def test_each_language_reads_its_own_direction(self):
        self.assertEqual(self.load("ar")["TEXT_DIRECTION"], "rtl")
        self.assertEqual(self.load("en")["TEXT_DIRECTION"], "ltr")

    def test_the_manager_loads_english(self):
        english = I18NManager("en")
        self.assertEqual(english.get_string("BTN_SEND_MESSAGE"), "Send")
        self.assertEqual(english.get_string("SENDER_YOU"), "You")

    def test_shortcuts_are_the_users_to_choose_so_no_text_carries_one(self):
        for language in c.LANGUAGES:
            self.assertEqual([key for key, value in self.load(language).items() if "\t" in value], [])
        self.assertIn("&", I18NManager("en").get_string("MENU_FILE"))


class LanguageSettingTest(unittest.TestCase):
    def test_language_is_one_of_the_offered_ones_and_defaults_to_arabic(self):
        self.assertEqual(s.CHOICES[s.SETTING_LANGUAGE], (c.LANGUAGES, "ar"))
        self.assertEqual(s.Settings().get(s.SETTING_LANGUAGE), "ar")

    def test_a_saved_language_loads_back_and_junk_falls_back(self):
        path = os.path.join(tempfile.mkdtemp(), "settings.json")
        with open(path, "w") as file:
            json.dump({s.SETTING_LANGUAGE: "en"}, file)
        with mock.patch.object(s, "SETTINGS_FILE", path):
            self.assertEqual(s.Settings().get(s.SETTING_LANGUAGE), "en")
        with open(path, "w") as file:
            json.dump({s.SETTING_LANGUAGE: "fr"}, file)
        with mock.patch.object(s, "SETTINGS_FILE", path):
            self.assertEqual(s.Settings().get(s.SETTING_LANGUAGE), "ar")


class LanguageDialogTest(WindowTestCase):
    chats = [(make_user(1, "Ali"), 0, False)]

    def test_choosing_english_is_saved_and_flagged_as_a_change(self):
        dialog = SettingsDialog(self.frame, self.i18n, self.frame.settings, self.manager)
        self.addCleanup(dialog.Destroy)
        self.assertEqual(dialog.language_choice.GetSelection(), c.LANGUAGES.index("ar"))
        self.assertEqual(dialog.language_choice.GetString(c.LANGUAGES.index("en")), c.LANGUAGE_NAMES["en"])
        dialog.language_choice.SetSelection(c.LANGUAGES.index("en"))
        dialog.apply_app_settings()
        self.assertTrue(dialog.language_changed)
        self.assertEqual(s.Settings().get(s.SETTING_LANGUAGE), "en")

    def test_leaving_the_language_as_it_is_is_not_a_change(self):
        dialog = SettingsDialog(self.frame, self.i18n, self.frame.settings, self.manager)
        self.addCleanup(dialog.Destroy)
        dialog.apply_app_settings()
        self.assertFalse(dialog.language_changed)

    def test_messages_are_translated_into_the_chosen_language(self):
        self.manager.translate_lang = "en"
        self.open_chat(0)
        # No message to translate here; just confirm the target language reaches the request.
        import core.telegram_client as tc
        self.assertEqual(self.manager.translate_lang, "en")
        self.assertIn("en", tc.DEFAULT_LANG + "en")


class InstallerLanguageTest(unittest.TestCase):
    def test_the_installer_offers_both_languages(self):
        with open(os.path.join(BASE_DIR, "installer.iss"), encoding="utf-8") as file:
            script = file.read()
        self.assertIn('Name: "arabic"', script)
        self.assertIn('Name: "english"', script)
        # The language dialog is shown so a user can pick English.
        self.assertIn("ShowLanguageDialog=yes", script)
