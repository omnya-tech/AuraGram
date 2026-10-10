"""Logic that needs neither a window nor Telegram."""
import datetime
import json
import os
import unittest

from core.chat_views import build_views, matches_folder
from core.constants import BASE_DIR, LOCALES_DIR
from core.i18n import I18NManager
from core.schedule import parse_send_time


def chat(chat_id, category="contacts", unread=0, muted=False, archived=False):
    return {"id": chat_id, "category": category, "unread": unread, "muted": muted, "archived": archived}


def folder(**overrides):
    rules = {
        "include_ids": set(), "exclude_ids": set(), "categories": set(),
        "exclude_muted": False, "exclude_read": False, "exclude_archived": False,
    }
    rules.update(overrides)
    return rules


class ParseSendTimeTest(unittest.TestCase):
    now = datetime.datetime(2026, 10, 10, 20, 0)

    def test_time_later_today_stays_today(self):
        self.assertEqual(parse_send_time("21:30", self.now), datetime.datetime(2026, 10, 10, 21, 30))

    def test_time_already_passed_moves_to_tomorrow(self):
        self.assertEqual(parse_send_time("7:05", self.now), datetime.datetime(2026, 10, 11, 7, 5))

    def test_current_minute_is_never_scheduled_in_the_past(self):
        self.assertEqual(parse_send_time("20:00", self.now), datetime.datetime(2026, 10, 11, 20, 0))

    def test_arabic_digits_and_other_separators(self):
        expected = datetime.datetime(2026, 10, 10, 21, 30)
        self.assertEqual(parse_send_time("٢١:٣٠", self.now), expected)
        self.assertEqual(parse_send_time(" 21.30 ", self.now), expected)

    def test_text_that_is_not_a_time(self):
        for text in ("", "25:00", "12:60", "soon", "2130", "12:"):
            self.assertIsNone(parse_send_time(text, self.now), text)


class FolderRulesTest(unittest.TestCase):
    def test_category_decides_when_nothing_is_listed_by_hand(self):
        rules = folder(categories={"contacts"})
        self.assertTrue(matches_folder(chat(1, "contacts"), rules))
        self.assertFalse(matches_folder(chat(2, "bots"), rules))

    def test_hand_picked_chat_is_in_regardless_of_category_and_flags(self):
        rules = folder(include_ids={5}, exclude_muted=True)
        self.assertTrue(matches_folder(chat(5, "broadcasts", muted=True), rules))

    def test_exclusion_beats_everything(self):
        rules = folder(include_ids={5}, exclude_ids={5}, categories={"contacts"})
        self.assertFalse(matches_folder(chat(5, "contacts"), rules))

    def test_exclude_flags(self):
        self.assertFalse(matches_folder(chat(1, muted=True), folder(categories={"contacts"}, exclude_muted=True)))
        self.assertFalse(matches_folder(chat(1, unread=0), folder(categories={"contacts"}, exclude_read=True)))
        self.assertFalse(matches_folder(chat(1, archived=True), folder(categories={"contacts"}, exclude_archived=True)))

    def test_built_in_views(self):
        everything, unread, archive = build_views(I18NManager("ar"), [])[:3]
        archived = chat(1, archived=True, unread=3)
        fresh = chat(2, unread=1)
        read = chat(3)
        self.assertEqual([everything.matches(c) for c in (archived, fresh, read)], [False, True, True])
        self.assertEqual([unread.matches(c) for c in (archived, fresh, read)], [False, True, False])
        self.assertEqual([archive.matches(c) for c in (archived, fresh, read)], [True, False, False])

    def test_each_folder_becomes_a_view_named_after_it(self):
        views = build_views(I18NManager("ar"), [dict(folder(categories={"bots"}), id=2, title="Robots")])
        self.assertEqual(len(views), 4)
        self.assertIn("Robots", views[3].label)
        self.assertTrue(views[3].matches(chat(1, "bots")))


class VersionTest(unittest.TestCase):
    def test_version_is_three_numbers(self):
        import re
        from core.constants import APP_VERSION
        self.assertRegex(APP_VERSION, re.compile(r"^\d+\.\d+\.\d+$"))

    def test_current_version_is_recorded_in_the_changelog(self):
        from core.constants import APP_VERSION
        with open(os.path.join(BASE_DIR, "CHANGELOG.md"), encoding="utf-8") as file:
            self.assertIn("## " + APP_VERSION, file.read())

    def test_about_text_shows_name_and_version(self):
        from core.constants import ABOUT_FORMAT_KEY, APP_NAME, APP_VERSION, DEVELOPER_NAME_KEY
        i18n = I18NManager("ar")
        developer = i18n.get_string(DEVELOPER_NAME_KEY)
        text = i18n.get_string(ABOUT_FORMAT_KEY).format(name=APP_NAME, version=APP_VERSION, developer=developer)
        self.assertIn(APP_NAME, text)
        self.assertIn(APP_VERSION, text)
        self.assertIn(developer, text)

    def test_publisher_is_named_in_the_copyright_line(self):
        from core.constants import APP_COPYRIGHT, APP_PUBLISHER
        self.assertTrue(APP_PUBLISHER.strip())
        self.assertIn(APP_PUBLISHER, APP_COPYRIGHT)


class ThemeTest(unittest.TestCase):
    def setUp(self):
        from tests.harness import get_app
        get_app()

    def test_every_theme_has_colours_and_a_name_to_show(self):
        import core.constants as constants
        from ui.themes import THEME_COLOURS
        strings = I18NManager("ar").strings
        self.assertEqual(set(THEME_COLOURS), set(constants.THEMES))
        for theme in constants.THEMES:
            self.assertIn(theme, strings)

    def test_text_is_easy_to_read_in_every_theme(self):
        # 7:1 is the stricter of the two WCAG levels for body text.
        from ui.themes import THEME_COLOURS, contrast_ratio
        for theme, colours in THEME_COLOURS.items():
            if colours is None:
                continue
            for background, text in (("window", "text"), ("field", "field_text"), ("button", "text")):
                ratio = contrast_ratio(colours[background], colours[text])
                self.assertGreaterEqual(ratio, 7, "%s: %s on %s is %.1f" % (theme, text, background, ratio))

    def test_contrast_formula_matches_the_known_extremes(self):
        from ui.themes import contrast_ratio
        self.assertAlmostEqual(contrast_ratio("#000000", "#FFFFFF"), 21, places=1)
        self.assertAlmostEqual(contrast_ratio("#777777", "#777777"), 1, places=2)

    def test_unknown_theme_falls_back_to_the_system_one(self):
        import core.constants as constants
        from ui import themes
        self.addCleanup(themes.set_theme, constants.THEME_SYSTEM)
        themes.set_theme("no such theme")
        self.assertEqual(themes.current_theme(), constants.THEME_SYSTEM)

    def test_theme_in_a_damaged_settings_file_is_ignored(self):
        import tempfile
        from unittest import mock
        import core.constants as constants
        from core.settings import SETTING_THEME, Settings
        path = os.path.join(tempfile.mkdtemp(), "settings.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump({SETTING_THEME: "neon"}, file)
        with mock.patch("core.settings.SETTINGS_FILE", path):
            self.assertEqual(Settings().get(SETTING_THEME), constants.THEME_SYSTEM)


class WindowPlacementSettingTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        from unittest import mock
        self.path = os.path.join(tempfile.mkdtemp(), "settings.json")
        patch = mock.patch("core.settings.SETTINGS_FILE", self.path)
        patch.start()
        self.addCleanup(patch.stop)

    def test_nothing_saved_yet(self):
        from core.settings import Settings
        self.assertIsNone(Settings().get_window_placement())

    def test_placement_survives_a_restart(self):
        from core.settings import Settings
        settings = Settings()
        settings.set_window_placement(10, 20, 900, 600, True)
        settings.save()
        self.assertEqual(Settings().get_window_placement(), [10, 20, 900, 600, 1])

    def test_a_damaged_placement_is_ignored_without_losing_other_settings(self):
        from core.settings import SETTING_PLAY_SOUND, WINDOW_PLACEMENT, Settings
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump({WINDOW_PLACEMENT: ["wide", 1], SETTING_PLAY_SOUND: False}, file)
        settings = Settings()
        self.assertIsNone(settings.get_window_placement())
        self.assertFalse(settings.get(SETTING_PLAY_SOUND))


class QuitRequestTest(unittest.TestCase):
    """--quit, which the installer uses to close the copy running in the background."""

    class FakeUser32:
        """Windows with one hidden AuraGram window that goes away some time after being told to close."""

        def __init__(self, running, lookups_until_gone=None):
            self.running = running
            self.lookups_until_gone = lookups_until_gone
            self.posted = []

        def FindWindowW(self, class_name, title):
            from core.constants import BACKGROUND_WINDOW_TITLE
            assert title == BACKGROUND_WINDOW_TITLE
            if self.running and self.posted and self.lookups_until_gone is not None:
                self.lookups_until_gone -= 1
                if self.lookups_until_gone <= 0:
                    self.running = False
            return 1234 if self.running else 0

        def PostMessageW(self, window, message, wparam, lparam):
            self.posted.append((window, message))

    def ask(self, user32, wait_seconds=1):
        from unittest import mock
        import ui.background as background
        with mock.patch.object(background.ctypes, "windll", mock.Mock(user32=user32)), \
                mock.patch.object(background.time, "sleep", lambda seconds: None):
            return background.ask_running_copy_to_quit(wait_seconds)

    def test_nothing_running_is_already_done(self):
        user32 = self.FakeUser32(running=False)
        self.assertTrue(self.ask(user32))
        self.assertEqual(user32.posted, [])

    def test_running_copy_is_asked_to_close_and_waited_for(self):
        user32 = self.FakeUser32(running=True, lookups_until_gone=3)
        self.assertTrue(self.ask(user32))
        self.assertEqual(user32.posted, [(1234, 0x0010)])

    def test_copy_that_will_not_close_is_reported(self):
        user32 = self.FakeUser32(running=True)
        self.assertFalse(self.ask(user32, wait_seconds=0.05))
        self.assertEqual(len(user32.posted), 1)


class InstallerScriptTest(unittest.TestCase):
    """The installer cannot be run in tests; these catch the script drifting from the app."""

    def setUp(self):
        with open(os.path.join(BASE_DIR, "installer.iss"), encoding="utf-8") as file:
            self.script = file.read()

    def test_installs_for_all_users_under_program_files(self):
        self.assertIn("PrivilegesRequired=admin", self.script)
        self.assertIn("DefaultDirName={autopf}\\", self.script)

    def test_uses_the_flags_the_program_understands(self):
        from core.constants import BACKGROUND_FLAG, QUIT_FLAG
        self.assertIn(BACKGROUND_FLAG, self.script)
        self.assertIn("'%s'" % QUIT_FLAG, self.script)

    def test_user_data_is_looked_for_where_the_program_keeps_it(self):
        from core.constants import APP_NAME
        self.assertIn('#define AppName "%s"' % APP_NAME, self.script)
        self.assertIn("{userappdata}\\{#AppName}", self.script)

    def test_compiled_on_its_own_it_still_carries_the_real_version_and_publisher(self):
        # Opened directly in Inno Setup, nothing passes these in; the defaults must be right.
        import re
        from core.constants import APP_COPYRIGHT, APP_PUBLISHER, APP_VERSION
        defaults = dict(re.findall(r'#ifndef (\w+)\s+#define \1 "([^"]*)"', self.script))
        self.assertEqual(defaults["AppVersion"], APP_VERSION)
        self.assertEqual(defaults["AppPublisher"], APP_PUBLISHER)
        self.assertEqual(defaults["AppCopyright"], APP_COPYRIGHT)

    def test_every_custom_message_exists_in_both_languages(self):
        import re
        used = set(re.findall(r"\{cm:(\w+)", self.script)) | set(re.findall(r"CustomMessage\('(\w+)'\)", self.script))
        self.assertTrue(used)
        for name in used:
            for language in ("arabic", "english"):
                self.assertIn("%s.%s=" % (language, name), self.script)


class CredentialsTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        from unittest import mock
        folder = tempfile.mkdtemp()
        self.path = os.path.join(folder, "config.json")
        self.bundled = os.path.join(folder, "bundled_config.json")
        for name, path in (("CONFIG_FILE", self.path), ("BUNDLED_CONFIG_FILE", self.bundled)):
            patch = mock.patch("core.config." + name, path)
            patch.start()
            self.addCleanup(patch.stop)

    HASH = "0123456789abcdef0123456789abcdef"
    OTHER_HASH = "ffffffffffffffffffffffffffffffff"

    def write(self, path, api_id, api_hash):
        with open(path, "w", encoding="utf-8") as file:
            json.dump({"API_ID": api_id, "API_HASH": api_hash}, file)

    def test_missing_file_means_not_set_up(self):
        from core.config import load_credentials
        self.assertEqual(load_credentials(), (0, ""))

    def test_saved_credentials_load_back(self):
        from core.config import load_credentials, save_credentials
        save_credentials(12345, self.HASH)
        self.assertEqual(load_credentials(), (12345, self.HASH))

    def test_damaged_file_is_treated_as_missing(self):
        from core.config import load_credentials
        with open(self.path, "w", encoding="utf-8") as file:
            file.write("{not json")
        self.assertEqual(load_credentials(), (0, ""))

    def test_values_packed_into_the_program_mean_it_never_asks(self):
        from core.config import load_credentials
        self.write(self.bundled, 777, self.HASH)
        self.assertEqual(load_credentials(), (777, self.HASH))

    def test_packed_values_win_over_whatever_a_user_typed_earlier(self):
        # An installed copy must not stay broken because of an old file with a mistyped key.
        from core.config import load_credentials
        self.write(self.bundled, 777, self.HASH)
        self.write(self.path, 111, self.OTHER_HASH)
        self.assertEqual(load_credentials(), (777, self.HASH))

    def test_hash_saved_with_a_stray_quote_still_loads_clean(self):
        from core.config import load_credentials
        self.write(self.path, 12345, self.HASH + '"')
        self.assertEqual(load_credentials(), (12345, self.HASH))

    def test_values_that_cannot_be_right_never_reach_telegram(self):
        from core.config import load_credentials
        for api_id, api_hash in ((12345, "short"), (12345, self.HASH + "0"), (0, self.HASH),
                                 ("12345", self.HASH), (-5, self.HASH)):
            self.write(self.path, api_id, api_hash)
            self.assertEqual(load_credentials(), (0, ""), (api_id, api_hash))

    def test_cleaning_drops_only_what_is_never_part_of_a_hash(self):
        from core.config import clean_api_hash
        self.assertEqual(clean_api_hash('  "%s",\n' % self.HASH.upper()), self.HASH)
        self.assertEqual(clean_api_hash(self.HASH + "‏"), self.HASH)
        self.assertEqual(clean_api_hash(self.HASH[:-1] + "z"), "")
        self.assertEqual(clean_api_hash(self.HASH[:-1]), "")
        self.assertEqual(clean_api_hash(""), "")


class ApiSetupDialogTest(unittest.TestCase):
    def setUp(self):
        from unittest import mock
        from tests.harness import get_app
        from ui.api_setup_dialog import ApiSetupDialog
        get_app()
        self.errors = []
        patch = mock.patch("wx.MessageBox", lambda message, *args, **kwargs: self.errors.append(message))
        patch.start()
        self.addCleanup(patch.stop)
        self.dialog = ApiSetupDialog(I18NManager("ar"))
        self.addCleanup(self.dialog.Destroy)
        self.ended = []
        self.dialog.EndModal = self.ended.append

    def fill(self, api_id, api_hash):
        self.dialog.id_input.SetValue(api_id)
        self.dialog.hash_input.SetValue(api_hash)
        self.dialog.on_ok(None)

    HASH = "0123456789abcdef0123456789abcdef"

    def test_rejects_a_non_numeric_id_or_a_hash_of_the_wrong_shape(self):
        self.fill("abc", self.HASH)
        self.fill("123", "  ")
        self.fill("123", "too short")
        self.fill("123", self.HASH + "0")
        self.fill("123", self.HASH[:-1] + "g")
        self.assertEqual(len(self.errors), 5)
        self.assertEqual(self.ended, [])
        self.assertIsNone(self.dialog.credentials)

    def test_accepts_valid_values_trimmed(self):
        self.fill(" 123 ", " %s " % self.HASH)
        self.assertEqual(self.dialog.credentials, (123, self.HASH))
        self.assertEqual(len(self.ended), 1)

    def test_a_quote_pasted_along_with_the_hash_is_dropped(self):
        # Copying the value out of config.json easily takes its closing quote too.
        self.fill("123", self.HASH + '"')
        self.assertEqual(self.dialog.credentials, (123, self.HASH))


class LocaleTest(unittest.TestCase):
    """Every text key the code names must exist, or the UI shows the raw key."""

    def test_every_key_constant_has_a_string(self):
        import core.constants as constants
        with open(os.path.join(LOCALES_DIR, "ar.json"), encoding="utf-8") as file:
            strings = json.load(file)
        missing = [
            value for name, value in vars(constants).items()
            if name.endswith("_KEY") and isinstance(value, str) and value not in strings
        ]
        self.assertEqual(missing, [])

    def test_keys_built_from_a_prefix_have_strings(self):
        import core.constants as constants
        with open(os.path.join(LOCALES_DIR, "ar.json"), encoding="utf-8") as file:
            strings = json.load(file)
        expected = [constants.ADMIN_RIGHT_KEY_PREFIX + name for name in constants.ADMIN_RIGHTS]
        expected += [constants.REACTION_NAME_KEY_PREFIX + str(i) for i in range(len(constants.REACTION_EMOJIS))]
        expected += [key for _, key in constants.MEDIA_KINDS]
        expected += list(constants.MESSAGE_VIEWS) + list(constants.PRIVACY_LEVELS)
        expected += [key for _, key in constants.MEMBER_LISTS]
        expected += [key for keys in constants.MEMBER_ACTION_TEXTS.values() for key in keys]
        expected += list(constants.CODE_DELIVERY_KEYS.values()) + list(constants.NEXT_CODE_DELIVERY_KEYS.values())
        expected += [constants.MEMBER_PERMISSION_KEY_PREFIX + name for name in constants.MEMBER_PERMISSIONS]
        self.assertEqual([key for key in expected if key not in strings], [])

    def test_secrets_are_ignored_by_git(self):
        with open(os.path.join(BASE_DIR, ".gitignore"), encoding="utf-8") as file:
            ignored = file.read()
        for pattern in ("config.json", "*.session", "settings.json", "downloads/"):
            self.assertIn(pattern, ignored)


if __name__ == "__main__":
    unittest.main()
