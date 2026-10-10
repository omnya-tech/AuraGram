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


class CredentialsTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        from unittest import mock
        self.path = os.path.join(tempfile.mkdtemp(), "config.json")
        patch = mock.patch("core.config.CONFIG_FILE", self.path)
        patch.start()
        self.addCleanup(patch.stop)

    def test_missing_file_means_not_set_up(self):
        from core.config import load_credentials
        self.assertEqual(load_credentials(), (0, ""))

    def test_saved_credentials_load_back(self):
        from core.config import load_credentials, save_credentials
        save_credentials(12345, "abcdef")
        self.assertEqual(load_credentials(), (12345, "abcdef"))

    def test_damaged_file_is_treated_as_missing(self):
        from core.config import load_credentials
        with open(self.path, "w", encoding="utf-8") as file:
            file.write("{not json")
        self.assertEqual(load_credentials(), (0, ""))


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

    def test_rejects_a_non_numeric_id_or_empty_hash(self):
        self.fill("abc", "hash")
        self.fill("123", "  ")
        self.assertEqual(len(self.errors), 2)
        self.assertEqual(self.ended, [])
        self.assertIsNone(self.dialog.credentials)

    def test_accepts_valid_values_trimmed(self):
        self.fill(" 123 ", " hash ")
        self.assertEqual(self.dialog.credentials, (123, "hash"))
        self.assertEqual(len(self.ended), 1)


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
