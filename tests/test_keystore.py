"""Secrets in the settings file locked to the Windows account (core/keystore.py)."""
import json
import os
import tempfile
import unittest
from unittest import mock

import core.keystore as keystore
import core.settings as s

ON_WINDOWS = unittest.skipUnless(keystore.AVAILABLE, "Windows data protection is only on Windows")


class KeystoreTest(unittest.TestCase):
    @ON_WINDOWS
    def test_a_sealed_text_opens_again_and_does_not_show_itself(self):
        sealed = keystore.seal("my-gemini-key ✓")
        self.assertTrue(keystore.is_sealed(sealed))
        self.assertNotIn("my-gemini-key", sealed)
        self.assertEqual(keystore.unseal(sealed), "my-gemini-key ✓")
        # A fresh lock each time: the same key never looks the same twice.
        self.assertNotEqual(keystore.seal("my-gemini-key ✓"), sealed)

    def test_nothing_stays_nothing(self):
        self.assertEqual(keystore.seal(""), "")
        self.assertEqual(keystore.unseal(""), "")

    def test_a_value_saved_unlocked_is_read_as_it_is(self):
        self.assertEqual(keystore.unseal("plain-key"), "plain-key")

    @ON_WINDOWS
    def test_a_value_that_cannot_be_opened_here_comes_back_empty(self):
        self.assertEqual(keystore.unseal(keystore.SEALED_PREFIX + "bm90IGEgbG9jaw=="), "")
        self.assertEqual(keystore.unseal(keystore.SEALED_PREFIX + "%%% not base64"), "")
        with self.assertLogs("core.keystore", "WARNING"):
            keystore.unseal(keystore.SEALED_PREFIX + "AAAA")

    def test_without_windows_values_are_kept_as_they_are(self):
        with mock.patch.object(keystore, "AVAILABLE", False):
            self.assertEqual(keystore.seal("plain-key"), "plain-key")
            self.assertEqual(keystore.unseal(keystore.SEALED_PREFIX + "AAAA"), "")


class SettingsSecretsTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "settings.json")
        patch = mock.patch.object(s, "SETTINGS_FILE", self.path)
        patch.start()
        self.addCleanup(patch.stop)

    def stored(self):
        with open(self.path, encoding="utf-8") as file:
            return json.load(file)

    @ON_WINDOWS
    def test_secrets_are_locked_in_the_file_and_plain_in_the_program(self):
        settings = s.Settings()
        settings.set(s.SETTING_GEMINI_KEY, "gemini-secret")
        settings.set(s.SETTING_PROXY_PASSWORD, "proxy-secret")
        settings.set(s.SETTING_PROXY_HOST, "1.2.3.4")
        settings.save()
        with open(self.path, encoding="utf-8") as file:
            text = file.read()
        self.assertNotIn("gemini-secret", text)
        self.assertNotIn("proxy-secret", text)
        # What is no secret is written as it always was.
        self.assertEqual(self.stored()[s.SETTING_PROXY_HOST], "1.2.3.4")
        self.assertEqual(self.stored()[s.SETTING_PROXY_SECRET], "")
        self.assertEqual(settings.get(s.SETTING_GEMINI_KEY), "gemini-secret")
        reloaded = s.Settings()
        self.assertEqual(reloaded.get(s.SETTING_GEMINI_KEY), "gemini-secret")
        self.assertEqual(reloaded.get(s.SETTING_PROXY_PASSWORD), "proxy-secret")

    @ON_WINDOWS
    def test_settings_saved_before_are_read_and_locked_at_once(self):
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump({s.SETTING_GEMINI_KEY: "old-plain-key", s.SETTING_PLAY_SOUND: False}, file)
        settings = s.Settings()
        self.assertEqual(settings.get(s.SETTING_GEMINI_KEY), "old-plain-key")
        self.assertFalse(settings.get(s.SETTING_PLAY_SOUND))
        self.assertTrue(keystore.is_sealed(self.stored()[s.SETTING_GEMINI_KEY]))
        self.assertFalse(self.stored()[s.SETTING_PLAY_SOUND])

    @ON_WINDOWS
    def test_a_file_from_another_account_loses_only_its_secrets(self):
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump({s.SETTING_GEMINI_KEY: keystore.SEALED_PREFIX + "AAAA", s.SETTING_PLAY_SOUND: False}, file)
        with self.assertLogs("core.keystore", "WARNING"):
            settings = s.Settings()
        self.assertEqual(settings.get(s.SETTING_GEMINI_KEY), "")
        self.assertFalse(settings.get(s.SETTING_PLAY_SOUND))

    def test_a_copy_with_secrets_carries_them_plain_for_another_computer(self):
        settings = s.Settings()
        settings.set(s.SETTING_GEMINI_KEY, "gemini-secret")
        settings.save()
        path = os.path.join(tempfile.mkdtemp(), "copy.json")
        settings.export_to(path, with_secrets=True)
        with open(path, encoding="utf-8") as file:
            self.assertEqual(json.load(file)["settings"][s.SETTING_GEMINI_KEY], "gemini-secret")
        other = s.Settings()
        other.set(s.SETTING_GEMINI_KEY, "")
        self.assertTrue(other.import_from(path))
        self.assertEqual(other.get(s.SETTING_GEMINI_KEY), "gemini-secret")


if __name__ == "__main__":
    unittest.main()
