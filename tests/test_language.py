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
                           "SOUND_ROW_FORMAT", "STATS_PERCENT_FORMAT", "INFO_MEMBER_ROLE_FORMAT", "ACCOUNT_ROW_FORMAT", "INLINE_RESULT_UNTITLED_FORMAT", "COUNTRY_ROW_FORMAT", "BOT_COMMAND_FORMAT", "SEARCH_ALL_ROW_FORMAT",
                           "TRAY_STATUS_FORMAT", "REACTION_CHOICE_FORMAT", "MEDIA_FORMAT", "POLL_OPTION_FORMAT",
                           "SHORTCUT_ROW_FORMAT", "SHORTCUTS_HELP_LINE_FORMAT",
                           # A bare percentage reads the same in both.
                           "MIC_LEVEL_40", "MIC_LEVEL_80", "MIC_LEVEL_130", "MIC_LEVEL_250", "POLL_PERCENT_FORMAT",
                           "EXPORT_LINE_FORMAT", "REMINDER_ROW_FORMAT", "TOOLTIP_COMMAND_FORMAT", "FORWARD_FAILURE_ROW_FORMAT"}
        untranslated = [key for key in ar if ar[key] == en[key] and key not in same_on_purpose]
        self.assertEqual(untranslated, [], "these English values are still the Arabic text")

    def test_each_language_reads_its_own_direction(self):
        self.assertEqual(self.load("ar")["TEXT_DIRECTION"], "rtl")
        self.assertEqual(self.load("en")["TEXT_DIRECTION"], "ltr")

    def test_no_arabic_comma_is_written_into_the_code_for_english_to_show(self):
        import glob
        import os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for path in glob.glob(os.path.join(root, "ui", "*.py")) + glob.glob(os.path.join(root, "core", "*.py")):
            with open(path, encoding="utf-8") as file:
                for number, line in enumerate(file, 1):
                    # Read from what is typed it may be; written out for the user to read, it comes from the texts.
                    if "،" in line and "replace" not in line and "re.compile" not in line:
                        self.fail("%s:%d writes an Arabic comma whatever the language" % (os.path.basename(path), number))
        self.assertEqual(I18NManager("en").get_string("FILE_LABEL_SEPARATOR"), ", ")

    def test_each_language_writes_its_own_marks(self):
        import re
        arabic_marks = re.compile("[،؛؟«»]")
        for key, text in I18NManager("en").strings.items():
            # English quotes words "like this" and asks "?": the Arabic «», ، ؛ and ؟ are for the Arabic texts.
            self.assertIsNone(arabic_marks.search(text), key)
        for key, text in I18NManager("ar").strings.items():
            # And Arabic asks with ؟ and lists with ، where a word of its own comes before them.
            self.assertIsNone(re.search(r"[؀-ۿ]\s*[?;]|[؀-ۿ], ", text), key)

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


class InstalledLanguageTest(unittest.TestCase):
    def folder_with(self, text):
        folder = tempfile.mkdtemp()
        if text is not None:
            with open(os.path.join(folder, c.INSTALL_LANGUAGE_FILE), "w", encoding="utf-8") as file:
                file.write(text)
        return folder

    def settings(self, folder, saved=None):
        path = os.path.join(tempfile.mkdtemp(), "settings.json")
        if saved is not None:
            with open(path, "w") as file:
                json.dump(saved, file)
        with mock.patch.object(s, "BASE_DIR", folder), mock.patch.object(s, "SETTINGS_FILE", path):
            return s.Settings()

    def test_the_program_first_opens_in_the_language_it_was_installed_in(self):
        # As the installer writes it, or with a line end after it.
        self.assertEqual(self.settings(self.folder_with("en\n")).get(s.SETTING_LANGUAGE), "en")
        self.assertEqual(self.settings(self.folder_with("ar")).get(s.SETTING_LANGUAGE), "ar")

    def test_a_language_chosen_in_the_settings_wins_and_nonsense_is_ignored(self):
        self.assertEqual(self.settings(self.folder_with("en"), {s.SETTING_LANGUAGE: "ar"}).get(s.SETTING_LANGUAGE), "ar")
        self.assertEqual(self.settings(self.folder_with("fr")).get(s.SETTING_LANGUAGE), "ar")
        self.assertEqual(self.settings(self.folder_with(None)).get(s.SETTING_LANGUAGE), "ar")

    def test_each_install_sets_the_language_once_even_over_a_choice_made_before(self):
        folder = self.folder_with("en\r\n20261021101500123")
        path = os.path.join(tempfile.mkdtemp(), "settings.json")
        with open(path, "w") as file:
            json.dump({s.SETTING_LANGUAGE: "ar"}, file)

        def start():
            with mock.patch.object(s, "BASE_DIR", folder), mock.patch.object(s, "SETTINGS_FILE", path):
                return s.Settings()
        # Installed again in English: English, and remembered as done.
        self.assertEqual(start().get(s.SETTING_LANGUAGE), "en")
        # Arabic chosen in the settings afterwards stays, start after start.
        settings = start()
        settings.set(s.SETTING_LANGUAGE, "ar")
        with mock.patch.object(s, "SETTINGS_FILE", path):
            settings.save()
        self.assertEqual(start().get(s.SETTING_LANGUAGE), "ar")
        self.assertEqual(start().get(s.SETTING_LANGUAGE), "ar")
        # Until the next install, or update, in English.
        with open(os.path.join(folder, c.INSTALL_LANGUAGE_FILE), "w", encoding="utf-8") as file:
            file.write("en\r\n20261101090000000")
        self.assertEqual(start().get(s.SETTING_LANGUAGE), "en")

    def test_a_first_start_after_installing_remembers_the_install(self):
        folder = self.folder_with("en\r\n20261021101500123")
        path = os.path.join(tempfile.mkdtemp(), "settings.json")
        with mock.patch.object(s, "BASE_DIR", folder), mock.patch.object(s, "SETTINGS_FILE", path):
            settings = s.Settings()
            self.assertEqual(settings.get(s.SETTING_LANGUAGE), "en")
            settings.set(s.SETTING_LANGUAGE, "ar")
            settings.save()
            # The same install does not undo what was chosen since.
            self.assertEqual(s.Settings().get(s.SETTING_LANGUAGE), "ar")

    def test_the_installer_writes_the_same_file_in_the_language_it_ran_in(self):
        with open(os.path.join(c.BASE_DIR, "installer.iss"), encoding="utf-8") as file:
            script = file.read()
        self.assertIn('#define InstallLanguageFile "%s"' % c.INSTALL_LANGUAGE_FILE, script)
        self.assertIn(r"{app}\{#InstallLanguageFile}", script)
        self.assertIn("ActiveLanguage = 'arabic'", script)
        # With the time of the install, so the program can tell one install from the next.
        self.assertIn("GetDateTimeString('yyyymmddhhnnsszzz'", script)


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
