"""The first-run question of how much to say, and a copy of the settings kept in a file."""
import json
import os
import tempfile
from unittest import mock

import wx

import core.constants as c
import core.settings as s
from tests.harness import FakeChooser, WindowTestCase


class LevelQuestionTest(WindowTestCase):
    def test_asked_once_and_the_answer_ticks_its_share(self):
        FakeChooser.selection = 1
        self.frame.ask_speech_level_once()
        self.assertEqual(FakeChooser.last_choices, [self.text(level) for level in c.SPEECH_LEVELS[:3]])
        settings = s.Settings()
        self.assertEqual(settings.get(s.SETTING_SPEECH_LEVEL), c.SPEECH_LEVEL_INTERMEDIATE)
        self.assertFalse(settings.get(s.FEEDBACK_SETTINGS[c.FEEDBACK_COUNT]))
        self.assertTrue(settings.get(s.SPEECH_LEVEL_ASKED))
        # Never again, whatever is answered.
        FakeChooser.last_choices = None
        self.frame.ask_speech_level_once()
        self.assertIsNone(FakeChooser.last_choices)

    def test_not_answering_keeps_the_beginner_level_and_does_not_ask_again(self):
        FakeChooser.confirmed = False
        self.frame.ask_speech_level_once()
        self.assertEqual(s.Settings().get(s.SETTING_SPEECH_LEVEL), c.SPEECH_LEVEL_BEGINNER)
        self.assertTrue(s.Settings().get(s.SPEECH_LEVEL_ASKED))


class BackupTest(WindowTestCase):
    def path(self):
        return os.path.join(tempfile.mkdtemp(), "copy.json")

    def test_a_copy_leaves_secrets_out_unless_asked_and_brings_the_rest_back(self):
        settings = self.frame.settings
        settings.set(s.SETTING_FAVORITES, [5, 9])
        settings.set(s.SETTING_SHORTCUTS, {c.MENU_REPLY_KEY: "Ctrl+Alt+F7"})
        settings.set(s.SETTING_GEMINI_KEY, "secret-key")
        settings.apply_level(c.SPEECH_LEVEL_ADVANCED)
        path = self.path()
        settings.export_to(path, with_secrets=False)
        with open(path, encoding="utf-8") as file:
            stored = json.load(file)["settings"]
        self.assertEqual(stored[s.SETTING_GEMINI_KEY], "")
        self.assertNotIn(s.WINDOW_PLACEMENT, stored)

        # On another computer: everything comes back, and the key already there is kept.
        other = s.Settings()
        other.set(s.SETTING_FAVORITES, [])
        other.set(s.SETTING_GEMINI_KEY, "this-computer-key")
        self.assertTrue(other.import_from(path))
        self.assertEqual(other.get(s.SETTING_FAVORITES), [5, 9])
        self.assertEqual(other.get(s.SETTING_SHORTCUTS), {c.MENU_REPLY_KEY: "Ctrl+Alt+F7"})
        self.assertEqual(other.get(s.SETTING_SPEECH_LEVEL), c.SPEECH_LEVEL_ADVANCED)
        self.assertEqual(other.get(s.SETTING_GEMINI_KEY), "this-computer-key")

        settings.export_to(path, with_secrets=True)
        self.assertTrue(other.import_from(path))
        self.assertEqual(other.get(s.SETTING_GEMINI_KEY), "secret-key")

    def test_a_file_that_is_no_copy_changes_nothing(self):
        path = self.path()
        with open(path, "w", encoding="utf-8") as file:
            json.dump({"favorites": [1]}, file)
        settings = s.Settings()
        self.assertFalse(settings.import_from(path))
        self.assertEqual(settings.get(s.SETTING_FAVORITES), [])

    def test_bringing_a_copy_back_from_the_menu_shows_it_at_once(self):
        source = s.Settings()
        source.set(s.SETTING_FAVORITES, [self.frame.all_dialogs[0]["id"]] if self.frame.all_dialogs else [77])
        path = self.path()
        source.export_to(path, with_secrets=False)

        class FakeFileDialog:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def ShowModal(self):
                return wx.ID_OK

            def GetPath(self):
                return path
        with mock.patch.object(wx, "FileDialog", FakeFileDialog):
            self.frame.on_import_settings_menu(None)
        self.assertEqual(self.frame.favorites, set(source.get(s.SETTING_FAVORITES)))
        self.assertEqual(self.spoken[-1], self.text(c.MSG_SETTINGS_IMPORTED_KEY))


class LanguageRestartTest(WindowTestCase):
    def test_a_new_language_offers_a_restart_and_yes_restarts(self):
        import core.restart as restart
        started, quit = [], []
        self.frame.on_quit = lambda: quit.append(True)
        with mock.patch.object(restart.subprocess, "Popen", lambda command, **kwargs: started.append(command)):
            self.box_answer = wx.NO
            self.frame.offer_restart()
            self.assertEqual((started, quit), ([], []))
            self.box_answer = wx.YES
            self.frame.offer_restart()
        self.assertIn(self.text(c.MSG_LANGUAGE_RESTART_KEY), self.boxes[-1])
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0][-1], c.RESTART_FLAG)
        self.assertEqual(quit, [True])

    def test_the_new_copy_is_started_the_way_this_one_runs(self):
        import sys
        import core.restart as restart
        self.assertEqual(restart.command()[0], sys.executable)
        self.assertTrue(restart.command()[1].endswith("main.py"))
        with mock.patch.object(restart, "IS_FROZEN", True):
            self.assertEqual(restart.command(), [sys.executable, c.RESTART_FLAG])
