"""Space plays a voice message from Telegram as it arrives and keeps nothing; Enter opens it in the
program Windows has for it, and Shift+Enter shows it in its folder.
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

    def test_enter_saves_it_to_the_downloads_and_opens_the_file_itself(self):
        folder = tempfile.mkdtemp()
        self.frame.settings.set(s.SETTING_DOWNLOAD_FOLDER, folder)
        self.frame.messages_list.SetSelection(0)
        with mock.patch.object(wx, "LaunchDefaultApplication", return_value=True) as launch:
            self.frame.on_activate_message(None)
            self.assertTrue(pump(lambda: self.calls("download") and not self.frame.transfers))
            self.assertTrue(pump(lambda: launch.called))
        self.assertEqual(self.calls("download")[0][2], folder + os.sep)
        # The file, in its own player: not its folder, and not played here.
        self.assertEqual(launch.call_args[0][0], folder + os.sep + "saved.bin")
        self.assertEqual(self.heard, [])

    def test_shift_enter_shows_the_file_selected_in_its_folder(self):
        folder = tempfile.mkdtemp()
        self.frame.settings.set(s.SETTING_DOWNLOAD_FOLDER, folder)
        self.frame.messages_list.SetSelection(0)
        self.frame.messages_list.SetFocus()
        event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        event.SetKeyCode(wx.WXK_RETURN)
        event.SetShiftDown(True)
        with mock.patch("ui.message_list.subprocess.Popen") as explorer, \
                mock.patch.object(wx, "LaunchDefaultApplication") as launch:
            self.frame.ProcessEvent(event)
            self.assertTrue(pump(lambda: explorer.called))
        self.assertEqual(explorer.call_args[0][0], ["explorer", "/select,", os.path.normpath(folder + os.sep + "saved.bin")])
        self.assertFalse(launch.called)
        # Downloaded once: asked again, it is shown from where it is.
        open(os.path.join(folder, "saved.bin"), "wb").close()
        with mock.patch("ui.message_list.subprocess.Popen") as explorer:
            self.frame.on_show_in_folder_menu(None)
        self.assertTrue(explorer.called)
        self.assertEqual(len(self.calls("download")), 1)

    def test_a_program_asks_before_it_runs_and_is_marked_as_from_the_internet(self):
        path = os.path.join(tempfile.mkdtemp(), "setup.exe")
        with open(path, "wb") as file:
            file.write(b"MZ")
        self.box_answer = wx.NO
        with mock.patch.object(wx, "LaunchDefaultApplication") as launch:
            self.frame.open_media(path, ("chat", 1), c.MEDIA_FILE)
        self.assertFalse(launch.called)
        self.assertIn("setup.exe", self.boxes[-1])
        # Windows checks it too, as it does a program from a browser.
        with open(path + ":Zone.Identifier") as mark:
            self.assertIn("ZoneId=3", mark.read())
        self.box_answer = wx.YES
        with mock.patch.object(wx, "LaunchDefaultApplication", return_value=True) as launch:
            self.frame.open_media(path, ("chat", 1), c.MEDIA_FILE)
        launch.assert_called_once_with(path)

    def test_a_file_nothing_opens_is_shown_in_its_folder(self):
        path = os.path.join(tempfile.mkdtemp(), "notes.xyz")
        with mock.patch.object(wx, "LaunchDefaultApplication", return_value=False), \
                mock.patch("ui.message_list.subprocess.Popen") as explorer:
            self.frame.open_media(path, ("chat", 1), c.MEDIA_FILE)
        self.assertEqual(explorer.call_args[0][0][2], os.path.normpath(path))
        self.assertEqual(self.boxes, [])
        # No file there, so no mark made beside it either.
        self.assertFalse(os.path.exists(path))


    def key(self, code, shift=False, control=False, alt=False, focus=None):
        """Press a key with the focus on `focus` (the messages, unless said otherwise); True if it was
        left to go on to the control, as a key the app does not take."""
        event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        event.SetKeyCode(code)
        event.SetShiftDown(shift)
        event.SetControlDown(control)
        event.SetAltDown(alt)
        skipped = []
        event.Skip = lambda skip=True: skipped.append(skip)
        with mock.patch.object(wx.Window, "FindFocus", return_value=focus or self.frame.messages_list):
            self.frame.on_char_hook(event)
        return bool(skipped)

    def test_shift_with_an_arrow_on_the_messages_seeks_while_a_sound_plays(self):
        self.frame.messages_list.SetSelection(0)
        self.space()
        asked = []
        with mock.patch.object(self.frame.player, "is_playing", lambda: True),                 mock.patch.object(self.frame.player, "seek", lambda seconds: asked.append(seconds) or 2.0):
            # In Arabic the window reads right to left: forward is the left arrow.
            self.key(wx.WXK_LEFT, shift=True)
            self.key(wx.WXK_RIGHT, shift=True)
            self.assertEqual(asked, [c.SEEK_SECONDS, -c.SEEK_SECONDS])
            # Where it landed, against the length Telegram gave with the message.
            self.assertEqual(self.spoken[-1], self.text(c.MSG_PLAYBACK_POSITION_FORMAT_KEY).format(
                position="0:02", duration="0:04"))
            # In the writing field Shift with an arrow selects text, as always: no seeking there.
            self.assertTrue(self.key(wx.WXK_RIGHT, shift=True, focus=self.frame.message_input))
            self.assertEqual(len(asked), 2)

    def test_shift_with_an_arrow_does_nothing_of_its_own_with_nothing_playing(self):
        self.frame.messages_list.SetSelection(0)
        with mock.patch.object(self.frame.player, "seek", lambda seconds: None):
            self.assertTrue(self.key(wx.WXK_LEFT, shift=True))

    def test_the_place_in_the_sound_is_said_on_request_from_anywhere(self):
        self.key(wx.WXK_SPACE, control=True, alt=True, focus=self.frame.message_input)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NOTHING_PLAYING_KEY))
        self.frame.messages_list.SetSelection(0)
        self.space()
        with mock.patch.object(self.frame.player, "is_playing", lambda: True),                 mock.patch.object(self.frame.player, "position", 65.4):
            self.key(wx.WXK_SPACE, control=True, alt=True, focus=self.frame.message_input)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_PLAYBACK_POSITION_FORMAT_KEY).format(
            position="1:05", duration="0:04"))

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
        long_path = os.path.join(tempfile.mkdtemp(), "long.ogg")
        audio.encode_voice(audio.numpy.zeros(audio.SAMPLE_RATE * 4, dtype=audio.SAMPLE_FORMAT), long_path)
        with open(long_path, "rb") as file:
            self.long_voice = file.read()
        with open(path, "rb") as file:
            self.voice = file.read()

    def play(self, pieces_later, on_write=None, seconds=None):
        import threading
        written = []
        player_box = []

        class Output:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def write(self, samples):
                written.append(len(samples))
                if on_write is not None:
                    on_write(player_box[0], sum(written))

            def abort(self):
                pass
        buffer = self.audio.StreamBuffer()
        done = threading.Event()
        result = []
        with mock.patch.object(self.audio.sounddevice, "OutputStream", Output):
            player = self.audio.Player()
            player_box.append(player)
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

    def send_long(self, buffer):
        buffer.feed(self.long_voice)
        buffer.finish()

    def test_going_forward_skips_and_going_back_plays_again(self):
        rate = self.audio.SAMPLE_RATE
        _, plain = self.play(self.send_long)
        whole = sum(plain)
        self.assertGreater(whole, rate * 3)
        asked = []

        def forward_once(player, so_far):
            if not asked:
                asked.append(player.seek(2))
        _, skipped = self.play(self.send_long, forward_once)
        # Two seconds fewer heard, give or take a block, and the jump said where it lands.
        self.assertAlmostEqual(sum(skipped), whole - 2 * rate, delta=self.audio.PLAY_BLOCK * 2)
        self.assertAlmostEqual(asked[0], 2, delta=0.2)

        def back_once(player, so_far):
            if not asked[1:] and so_far >= 3 * rate:
                asked.append(player.seek(-1))
        _, again = self.play(self.send_long, back_once)
        self.assertAlmostEqual(sum(again), whole + rate, delta=self.audio.PLAY_BLOCK * 2)

    def test_going_back_stops_at_the_start_and_nothing_playing_cannot_seek(self):
        rate = self.audio.SAMPLE_RATE
        _, plain = self.play(self.send_long)
        asked = []

        def far_back(player, so_far):
            if not asked and so_far >= rate:
                asked.append(player.seek(-1000))
        _, written = self.play(self.send_long, far_back)
        self.assertEqual(asked, [0.0])
        self.assertAlmostEqual(sum(written), sum(plain) + rate, delta=self.audio.PLAY_BLOCK * 2)
        self.assertIsNone(self.audio.Player().seek(5))

    def stuck_output(self, release):
        """A sound card whose write never returns until `release` is set, whatever abort does."""
        class Stuck:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def write(self, samples):
                release.wait()

            def abort(self):
                pass
        return Stuck

    def test_a_sound_card_that_does_not_let_go_holds_the_program_up_two_seconds_at_most(self):
        import threading
        import time
        release = threading.Event()
        self.addCleanup(release.set)
        finished = []
        with mock.patch.object(self.audio.sounddevice, "OutputStream", self.stuck_output(release)), \
                mock.patch.object(self.audio.sounddevice, "stop"):
            player = self.audio.Player()
            player.play(self.long_voice, lambda *result: finished.append(result))
            time.sleep(0.3)
            began = time.monotonic()
            with self.assertLogs("core.audio", "WARNING"):
                player.stop()
            self.assertLess(time.monotonic() - began, self.audio.STOP_WAIT_SECONDS + 1)
            self.assertFalse(player.is_playing())
            # The next sound is not held up by the one let go, and that one never plays again.
            old_halt = player.halt
            player.play(self.long_voice, lambda *result: None)
            self.assertTrue(old_halt.is_set())
            self.assertFalse(player.halt.is_set())
            release.set()
            player.stop()

    def test_a_song_fetched_whole_is_played_as_it_is_decoded_not_held_whole(self):
        import threading
        written = []
        done = threading.Event()

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
        result = []
        with mock.patch.object(self.audio.sounddevice, "OutputStream", Output), \
                mock.patch.object(self.audio, "decode", side_effect=AssertionError("decoded whole")):
            player = self.audio.Player()
            player.play(self.long_voice, lambda *finished: (result.append(finished), done.set()))
            self.assertTrue(done.wait(10))
        self.assertEqual(result, [(True, None)])
        self.assertAlmostEqual(sum(written), 4 * self.audio.SAMPLE_RATE, delta=self.audio.SAMPLE_RATE // 10)
