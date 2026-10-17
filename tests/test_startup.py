"""A second start of the program, as from the desktop icon, hands over to the running copy before loading anything heavy."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import core.constants as c
import main


class HandOverTest(unittest.TestCase):
    def setUp(self):
        self.asked = []
        self.left = []
        for patch in (
            mock.patch.object(main, "ask_running_copy_to_show", lambda: self.asked.append("show") or True),
            mock.patch.object(main, "ask_running_copy_to_take_files", lambda: self.asked.append("files") or True),
            mock.patch.object(main.share, "leave", self.left.extend),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def hand_over(self, arguments, running=True):
        with mock.patch.object(main, "running_copy_window", lambda: 7 if running else 0):
            return main.hand_over_to_running_copy(arguments)

    def test_with_no_copy_running_the_program_starts_as_usual(self):
        self.assertFalse(self.hand_over([], running=False))
        self.assertEqual(self.asked, [])

    def test_a_running_copy_is_brought_forward(self):
        self.assertTrue(self.hand_over([c.BACKGROUND_FLAG]))
        self.assertEqual(self.asked, ["show"])

    def test_files_are_left_for_the_running_copy(self):
        path = os.path.join(tempfile.mkdtemp(), "notes.txt")
        open(path, "w").close()
        self.assertTrue(self.hand_over([path]))
        self.assertEqual((self.asked, self.left), (["files"], [path]))

    def test_the_build_checks_and_the_installer_quit_are_never_handed_over(self):
        for flag in (c.CHECK_FLAG, c.QUIT_FLAG):
            self.assertFalse(self.hand_over([flag]))
        self.assertEqual(self.asked, [])

    def test_handing_over_loads_neither_telegram_nor_audio(self):
        code = (
            "import sys; sys.argv = ['main.py']; import ui.background as b; b.running_copy_window = lambda: 0; "
            "ns = {}; "
            "src = open('main.py', encoding='utf-8').read(); head = src[:src.index('import logging')]; "
            "exec(compile(head.replace(\"__name__ == '__main__'\", 'False'), 'main.py', 'exec'), ns); "
            "print(any(name in sys.modules for name in ('telethon', 'numpy', 'sounddevice', 'av')))"
        )
        result = subprocess.run([sys.executable, "-c", code], cwd=c.BASE_DIR, capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), "False", result.stderr)
