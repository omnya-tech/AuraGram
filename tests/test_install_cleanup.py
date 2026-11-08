"""What an older install leaves behind cannot break a newer one: the installer clears the libraries
first, and a cryptg that cannot encrypt is set aside before Telethon takes it."""
import os
import re
import sys
import types
import unittest
from unittest import mock

import core
import core.constants as c


class LeftoverCryptgTest(unittest.TestCase):
    def setUp(self):
        saved = sys.modules.get("cryptg", "absent"), core.CRYPTG_SET_ASIDE

        def restore():
            if saved[0] == "absent":
                sys.modules.pop("cryptg", None)
            else:
                sys.modules["cryptg"] = saved[0]
            core.CRYPTG_SET_ASIDE = saved[1]
        self.addCleanup(restore)

    def test_a_cryptg_folder_without_its_compiled_part_is_set_aside(self):
        # What Python makes of 1.0.0's cryptg folder, whose .pyd was built for Python 3.11.
        sys.modules["cryptg"] = types.ModuleType("cryptg")
        core.CRYPTG_SET_ASIDE = False
        core._set_aside_broken_cryptg()
        self.assertTrue(core.CRYPTG_SET_ASIDE)
        with self.assertRaises(ImportError):
            import cryptg  # noqa: F401

    def test_a_working_cryptg_is_kept(self):
        working = types.ModuleType("cryptg")
        working.encrypt_ige = working.decrypt_ige = lambda *args: b""
        sys.modules["cryptg"] = working
        core.CRYPTG_SET_ASIDE = False
        core._set_aside_broken_cryptg()
        self.assertFalse(core.CRYPTG_SET_ASIDE)
        self.assertIs(sys.modules["cryptg"], working)

    def test_telethon_encrypts_with_cryptg_here(self):
        # The build's self-check stops a release without it; this says so before a build is even tried.
        from telethon.crypto import aes
        self.assertIsNotNone(aes.cryptg)


class InstallerCleanupTest(unittest.TestCase):
    def test_the_whole_installer_clears_the_old_libraries_and_the_small_one_does_not(self):
        with open(os.path.join(c.BASE_DIR, "installer.iss"), encoding="utf-8") as script_file:
            script = script_file.read()
        full_only = re.search(r"#ifndef UpdateOnly\s*\[InstallDelete\](.*?)\[", script, re.S)
        self.assertIsNotNone(full_only)
        self.assertIn('Name: "{app}\\_internal"', full_only.group(1))
        # Only once: the small update carries the program alone and needs the libraries kept.
        self.assertEqual(script.count("[InstallDelete]"), 1)


class SendToMenuTest(unittest.TestCase):
    def test_send_to_has_the_one_auragram_entry_and_it_sends_each_file_as_it_is(self):
        with open(os.path.join(c.BASE_DIR, "installer.iss"), encoding="utf-8") as script_file:
            script = script_file.read()
        entries = re.findall(r'Name: "\{usersendto\}([^"]*)".*?Parameters: "--send-as=(\w+)"', script)
        self.assertEqual(entries, [("\\{#AppName}", c.SEND_AS_AUTO)])
        # Each as it is: a sound as a sound, anything else as the file it is.
        self.assertEqual(c.SEND_AS_CHOICES[c.SEND_AS_AUTO], (True, False))
        # What builds in between put there is taken away by the whole installer.
        self.assertIn('Type: files; Name: "{usersendto}\\{#AppName} - *.lnk"', script)
        self.assertIn('Type: filesandordirs; Name: "{usersendto}\\{#AppName}"', script)
        self.assertNotIn("{cm:SendTo", script.replace("{cm:SendToMenu}", ""))


class SelfCheckTest(unittest.TestCase):
    def test_pure_python_encryption_stops_the_build(self):
        import build
        self.assertTrue(build.SELF_CHECK_FATAL & 32)
        self.assertIn(32, [bit for bit, text in build.SELF_CHECK_PROBLEMS])
        self.assertIn("cryptg", build.COLLECTED_PACKAGES)
        with mock.patch.object(build.subprocess, "run", return_value=mock.Mock(returncode=32)), \
                mock.patch("builtins.print"), self.assertRaises(SystemExit):
            build.check_program()


if __name__ == "__main__":
    unittest.main()
