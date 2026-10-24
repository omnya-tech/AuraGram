"""JAWS is reached directly when accessible_output2 finds no screen reader though JAWS runs."""
import sys
import types
import unittest
from unittest import mock

from core import speech


class FakeJawsApi:
    def __init__(self):
        self.said = []
        self.functions = []

    def SayString(self, text, interrupt):
        self.said.append((text, interrupt))

    def RunFunction(self, call):
        self.functions.append(call)


class JawsFallbackTest(unittest.TestCase):
    def setUp(self):
        self.api = FakeJawsApi()
        self.window = 0
        self.dispatched = []
        win32gui = types.SimpleNamespace(FindWindow=lambda cls, title: self.window if cls == speech.JAWS_WINDOW_CLASS else 0)
        client = types.SimpleNamespace(Dispatch=lambda name: self.dispatched.append(name) or self.api)
        win32com = types.ModuleType("win32com")
        win32com.client = client
        for patch in (
            mock.patch.dict(sys.modules, {"win32gui": win32gui, "win32com": win32com, "win32com.client": client}),
            mock.patch.object(speech, "_jaws", speech.JawsFallback()),
            # accessible_output2 finding nothing, as when JAWS was started after the app.
            mock.patch.object(speech, "_auto", None),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def test_nothing_is_said_without_a_screen_reader(self):
        speech.speak("hello")
        self.assertEqual((self.api.said, self.dispatched), ([], []))

    def test_jaws_running_is_spoken_to_directly_and_reached_once(self):
        self.window = 4242
        speech.speak("hello", interrupt=True)
        speech.speak("again")
        self.assertEqual(self.api.said, [("hello", True), ("again", False)])
        self.assertEqual(self.dispatched, [speech.JAWS_COM_NAME])

    def test_braille_keeps_the_jaws_call_whole(self):
        self.window = 4242
        speech.braille('He said "hi"')
        self.assertEqual(self.api.functions, ["BrailleString(\"He said 'hi'\")"])

    def test_a_jaws_that_fails_is_logged_once_and_tried_again_later(self):
        self.window = 4242
        failing = mock.Mock(side_effect=RuntimeError("restarting"))
        self.api.SayString = failing
        with self.assertLogs("core.speech", "WARNING") as logged:
            speech.speak("one")
            speech.speak("two")
        self.assertEqual(len(logged.records), 1)
        self.assertEqual(len(self.dispatched), 2)

    def test_the_screen_reader_accessible_output2_finds_comes_first(self):
        self.window = 4242
        nvda = mock.Mock()
        nvda.is_system_output.return_value = False
        auto = mock.Mock()
        auto.get_first_available_output.return_value = nvda
        with mock.patch.object(speech, "_auto", auto):
            speech.speak("hello")
        nvda.speak.assert_called_once_with("hello", interrupt=False)
        self.assertEqual(self.api.said, [])
