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


class StartWithWindowsTest(unittest.TestCase):
    """Started with Windows the program stays out of sight and silent, but for a tone of its own once ready."""

    def app(self, start_hidden, **settings):
        values = {main.SETTING_START_SOUND: True, main.SETTING_WINDOWS_START_SOUND: True,
                  main.SETTING_ANNOUNCE_CONNECTION: True, **settings}
        app = mock.MagicMock()
        app.start_hidden = start_hidden
        app.quiet_until_online = start_hidden
        app.account_generation, app.account_after, app.connection_state = 1, None, None
        app.settings.get = values.get
        return app

    def signed_in(self, app):
        played = []
        # The checks that follow an opened window are queued for later; only what is decided now counts here.
        with mock.patch.object(main, "load_main_frame", lambda: mock.MagicMock()), \
                mock.patch.object(main.sounds, "play", played.append), mock.patch.object(main.wx, "CallAfter"):
            main.MainApplication._process_telegram_response(app, c.STEP_DONE, None, 1)
        return played

    def test_its_own_tone_once_ready_and_no_window(self):
        app = self.app(start_hidden=True)
        self.assertEqual(self.signed_in(app), [c.SOUND_START_WINDOWS])
        app.main_frame.Show.assert_not_called()

    def test_opened_by_hand_the_usual_tone_and_the_window(self):
        app = self.app(start_hidden=False)
        self.assertEqual(self.signed_in(app), [c.SOUND_START])
        app.main_frame.Show.assert_called_once()

    def test_the_tone_can_be_turned_off(self):
        self.assertEqual(self.signed_in(self.app(start_hidden=True, **{main.SETTING_WINDOWS_START_SOUND: False})), [])

    def test_nothing_is_said_of_the_connection_before_it_is_first_made(self):
        app = self.app(start_hidden=True)
        spoken = []
        with mock.patch.object(main, "speak", spoken.append):
            for state in (c.CONNECTION_OFFLINE, c.CONNECTION_ONLINE, c.CONNECTION_OFFLINE):
                main.MainApplication._show_connection_state(app, state)
        # Lost and back while starting: silent. Lost after that: said, as at any other time.
        self.assertEqual(len(spoken), 1)

    def test_the_window_asked_for_while_waiting_opens_once_signed_in(self):
        app = self.app(start_hidden=True)
        app.main_frame = None
        main.MainApplication.show_window(app)
        self.assertEqual(self.signed_in(app), [c.SOUND_START])
        app.main_frame.Show.assert_called_once()
