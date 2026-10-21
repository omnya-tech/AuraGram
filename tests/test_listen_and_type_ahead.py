"""Space plays a voice message from Telegram as it arrives and keeps nothing; Enter saves it.
And in any list, typing the start of a name goes to it."""
import os
import tempfile
import unittest
from unittest import mock

import wx

import core.constants as c
import core.settings as s
from tests.harness import Record, WindowTestCase, get_app, make_channel, make_message, make_user, pump
from ui.type_ahead import TypeAhead, fold

ALI = make_user(1, "Ali")
AHMED = make_user(2, "أحمد")
TEAM = make_channel(41, "Team", group=True)


class Typed:
    """A key typed, as the list sees it."""

    def __init__(self, char, control=False):
        self.char = char
        self.control = control
        self.skipped = False

    def GetUnicodeKey(self):
        return ord(self.char)

    def ControlDown(self):
        return self.control

    def AltDown(self):
        return False

    def Skip(self):
        self.skipped = True


class ListenTest(WindowTestCase):
    chats = [(ALI, 0, False)]
    history = {1: [
        make_message(1, sender=ALI, voice=True, file=Record(name=None, size=30000, duration=4)),
        make_message(2, "words only", sender=ALI),
    ]}

    def setUp(self):
        super().setUp()
        self.heard = []
        self.streams = []
        for patch in (
            mock.patch.object(self.frame, "play_voice", self.heard.append),
            mock.patch.object(self.frame.player, "play_stream", lambda buffer, on_finished, speed=1.0: self.streams.append(
                (buffer, on_finished)
            )),
            mock.patch("core.audio.AVAILABLE", True),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.open_chat(0)

    def space(self):
        event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        event.SetKeyCode(wx.WXK_SPACE)
        with mock.patch.object(wx.Window, "FindFocus", return_value=self.frame.messages_list):
            self.frame.on_char_hook(event)
        return event.GetSkipped()

    def arrived(self, buffer):
        pieces = []
        while True:
            piece = buffer.read()
            if not piece:
                return b"".join(pieces)
            pieces.append(piece)

    def test_space_plays_it_as_it_arrives_and_keeps_nothing(self):
        self.frame.messages_list.SetSelection(0)
        self.assertFalse(self.space())
        # The player is handed the sound at once, and reads it as Telegram sends it.
        self.assertEqual(len(self.streams), 1)
        buffer, on_finished = self.streams[0]
        self.assertEqual(self.arrived(buffer), b"sound")
        self.assertEqual(self.calls("stream"), [("stream", c.STREAM_REQUEST_BYTES)])
        # Nothing fetched whole, and nothing written anywhere.
        self.assertEqual(self.calls("download"), [])
        self.assertFalse(self.frame.is_busy)

    def test_heard_again_it_comes_from_telegram_again(self):
        self.frame.messages_list.SetSelection(0)
        self.space()
        self.streams[0][1](True, None, True)
        pump(timeout=0.1)
        self.space()
        self.assertEqual(len(self.streams), 2)
        self.assertTrue(pump(lambda: len(self.calls("stream")) == 2))

    def test_a_sound_that_cannot_play_as_it_arrives_is_fetched_whole_and_played(self):
        self.frame.messages_list.SetSelection(0)
        self.space()
        # Nothing of it could be heard: fetched whole into memory, as a last resort.
        self.streams[0][1](False, ValueError("not streamable"), False)
        self.assertTrue(pump(lambda: self.heard))
        self.assertEqual(self.heard, [b"sound"])
        self.assertEqual([call[2] for call in self.calls("download")], [bytes])

    def test_space_while_it_plays_stops_it(self):
        self.frame.messages_list.SetSelection(0)
        with mock.patch.object(self.frame.player, "is_playing", lambda: True), \
                mock.patch.object(self.frame.player, "stop") as stop:
            self.space()
        stop.assert_called_once()
        self.assertEqual(self.calls("download"), [])
        self.assertEqual(self.streams, [])

    def test_space_on_a_message_without_sound_is_left_alone(self):
        self.frame.messages_list.SetSelection(1)
        self.assertTrue(self.space())
        self.assertEqual((self.calls("download"), self.streams), ([], []))

    def test_enter_saves_it_to_the_downloads_and_plays_nothing(self):
        folder = tempfile.mkdtemp()
        self.frame.settings.set(s.SETTING_DOWNLOAD_FOLDER, folder)
        self.frame.messages_list.SetSelection(0)
        self.frame.on_activate_message(None)
        self.assertTrue(pump(lambda: self.calls("download") and not self.frame.transfers))
        self.assertEqual(self.calls("download")[0][2], folder + os.sep)
        self.assertEqual(self.heard, [])
        self.assertIn(folder, self.spoken[-1])


class ChatListTypingTest(WindowTestCase):
    chats = [(ALI, 0, False), (AHMED, 0, False), (TEAM, 0, False)]

    def type(self, text):
        for char in text:
            self.frame.dialogs_type_ahead.on_char(Typed(char))

    def selected_title(self):
        return self.frame.dialogs[self.frame.dialogs_list.GetSelection()]["title"]

    def test_a_name_is_found_by_its_first_letters(self):
        self.frame.dialogs_list.SetSelection(0)
        self.type("te")
        self.assertEqual(self.selected_title(), "Team")

    def test_arabic_is_found_without_its_hamza(self):
        self.frame.dialogs_list.SetSelection(0)
        self.type("احم")
        self.assertEqual(self.selected_title(), "أحمد")

    def test_a_row_with_no_chat_behind_it_is_typed_through(self):
        # E.g. the row that says more chats are being fetched, after the last chat.
        self.frame.dialogs_list.Append("loading")
        self.frame.dialogs_list.SetSelection(2)
        self.type("l")
        self.assertEqual(self.frame.dialogs_list.GetSelection(), 3)
        self.type_ahead_reset()
        self.type("a")
        self.assertEqual(self.selected_title(), "Ali")

    def type_ahead_reset(self):
        self.frame.dialogs_type_ahead.typed = ""

    def test_typing_with_control_is_left_to_the_shortcuts(self):
        event = Typed("t", control=True)
        self.frame.dialogs_type_ahead.on_char(event)
        self.assertTrue(event.skipped)


class TypeAheadTest(unittest.TestCase):
    def setUp(self):
        get_app()
        self.frame = wx.Frame(None)
        self.addCleanup(self.frame.Destroy)
        self.list_box = wx.ListBox(self.frame, choices=["Apple", "Avocado", "Banana", "apricot"])
        self.type_ahead = TypeAhead(self.list_box)
        self.list_box.SetSelection(0)

    def press(self, char):
        event = Typed(char)
        self.type_ahead.on_char(event)
        return event

    def test_one_letter_again_and_again_goes_round_the_items_with_it(self):
        self.press("a")
        self.assertEqual(self.list_box.GetSelection(), 1)
        self.type_ahead.typed = ""
        self.press("a")
        self.assertEqual(self.list_box.GetSelection(), 3)
        self.type_ahead.typed = ""
        self.press("a")
        self.assertEqual(self.list_box.GetSelection(), 0)

    def test_a_space_on_its_own_is_the_lists_own(self):
        self.assertTrue(self.press(" ").skipped)

    def test_after_a_pause_the_typing_starts_over(self):
        self.press("b")
        self.assertEqual(self.list_box.GetSelection(), 2)
        self.type_ahead.last_typed -= c.TYPE_AHEAD_PAUSE_SECONDS + 1
        self.press("a")
        self.assertEqual(self.list_box.GetSelection(), 3)

    def test_arabic_letters_people_type_one_for_another_match(self):
        self.assertEqual(fold("إسلام"), fold("اسلام"))
        self.assertEqual(fold("مدرسة"), fold("مدرسه"))
        self.assertEqual(fold("مُصْطَفى"), fold("مصطفي"))


class StreamingPlayerTest(unittest.TestCase):
    """The real decoder, reading a voice message as it arrives, with the sound card stood in for."""

    def setUp(self):
        from core import audio
        if not audio.AVAILABLE:
            self.skipTest("audio libraries not installed")
        self.audio = audio
        path = os.path.join(tempfile.mkdtemp(), "voice.ogg")
        audio.encode_voice(audio.numpy.zeros(audio.SAMPLE_RATE // 2, dtype=audio.SAMPLE_FORMAT), path)
        with open(path, "rb") as file:
            self.voice = file.read()

    def play(self, pieces_later):
        import threading
        written = []

        class Output:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def write(self, samples):
                written.append(len(samples))

            def abort(self):
                pass
        buffer = self.audio.StreamBuffer()
        done = threading.Event()
        result = []
        with mock.patch.object(self.audio.sounddevice, "OutputStream", Output):
            player = self.audio.Player()
            player.play_stream(buffer, lambda *finished: (result.append(finished), done.set()))
            pieces_later(buffer)
            self.assertTrue(done.wait(10))
        return result[0], written

    def test_it_plays_while_the_rest_is_still_coming(self):
        def send(buffer):
            # A few bytes at a time, as Telegram might send them, from another thread.
            import threading
            def feed():
                for start in range(0, len(self.voice), 300):
                    buffer.feed(self.voice[start:start + 300])
                buffer.finish()
            threading.Thread(target=feed).start()
        (completed, error, started), written = self.play(send)
        self.assertEqual((completed, error, started), (True, None, True))
        self.assertGreater(sum(written), self.audio.SAMPLE_RATE // 4)

    def test_what_is_not_a_sound_says_nothing_was_heard(self):
        def send(buffer):
            buffer.feed(b"not a sound at all" * 50)
            buffer.finish()
        (completed, error, started), written = self.play(send)
        self.assertFalse(completed or started)
        self.assertIsNotNone(error)
