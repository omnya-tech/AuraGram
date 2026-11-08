"""Sound files sent as sounds, as Telegram's apps send music: played in the chat with the song's title
and singer, not as a file to download; and as plain files only when that is asked for."""
import os
import tempfile
from unittest import mock

import av
import numpy
import wx

import core.constants as c
from core import audio
from tests.harness import FakeChooser, FakeTelegramClient, WindowTestCase, make_user, pump

ALI = make_user(1, "Ali")


def make_song(folder, name, title=None, artist=None, seconds=3):
    """A real sound file, tagged the way a song is."""
    path = os.path.join(folder, name)
    with av.open(path, "w") as out:
        if title:
            out.metadata["title"] = title
        if artist:
            out.metadata["artist"] = artist
        stream = out.add_stream("flac", rate=8000)
        stream.layout = "mono"
        frame = av.AudioFrame.from_ndarray(numpy.zeros((1, 8000 * seconds), dtype=numpy.int16), format="s16", layout="mono")
        frame.rate = 8000
        for packet in stream.encode(frame):
            out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)
    return path


class SoundDetailsTest(WindowTestCase.__base__):
    def test_length_title_and_singer_are_read_from_the_file(self):
        folder = tempfile.mkdtemp()
        self.assertEqual(audio.sound_details(make_song(folder, "a.flac", "Ya Msafer", "Fairuz")), (3, "Ya Msafer", "Fairuz"))
        # Untagged: its length all the same, and Telegram shows its file name.
        self.assertEqual(audio.sound_details(make_song(folder, "b.flac")), (3, None, None))
        self.assertEqual(audio.sound_details(os.path.join(folder, "missing.mp3")), (0, None, None))


class SendAudioTest(WindowTestCase):
    chats = [(ALI, 0, False)]

    def setUp(self):
        super().setUp()
        self.open_chat(0)
        self.folder = tempfile.mkdtemp()

    def sounds(self):
        return self.calls("sound")

    def test_the_audio_entry_sends_each_sound_as_a_song_without_asking_how(self):
        first = make_song(self.folder, "first.flac", "Ya Msafer", "Fairuz")
        second = make_song(self.folder, "second.flac")
        FakeChooser.values = ["for you"]
        FakeChooser.last_choices = None
        with mock.patch.object(wx, "FileDialog") as file_dialog:
            file_dialog.return_value.__enter__.return_value.ShowModal.return_value = wx.ID_OK
            file_dialog.return_value.__enter__.return_value.GetPaths.return_value = [first, second]
            self.frame.on_send_audio_menu(None)
        self.assertTrue(pump(lambda: len(self.sounds()) == 2))
        # Picked as sounds: no question whether they go as files.
        self.assertIsNone(FakeChooser.last_choices)
        self.assertEqual(self.sounds()[0][2:], (first, "Ya Msafer", "Fairuz", 3, False, "audio/flac"))
        self.assertEqual(self.sounds()[1][2:6], (second, None, None, 3))
        # Each its own message, the caption with the first.
        sent = self.calls("send_file")
        self.assertEqual([call[2:4] for call in sent], [(first, "for you"), (second, None)])

    def test_a_sound_picked_as_a_file_asks_and_can_still_go_as_a_song(self):
        song = make_song(self.folder, "song.flac", "Ya Msafer", "Fairuz")
        FakeChooser.values = [""]
        FakeChooser.selection = 0
        self.frame.send_paths([song])
        self.assertTrue(pump(lambda: self.sounds()))
        self.assertEqual(FakeChooser.last_choices, [self.text(c.SEND_AUDIO_AS_AUDIO_KEY), self.text(c.SEND_AUDIO_AS_FILES_KEY)])

    def test_or_as_a_plain_file_when_that_is_chosen(self):
        song = make_song(self.folder, "song.flac", "Ya Msafer", "Fairuz")
        FakeChooser.values = [""]
        FakeChooser.selection = 1
        self.frame.send_paths([song])
        self.assertTrue(pump(lambda: self.calls("send_file")))
        self.assertEqual(self.sounds(), [])

    def test_other_files_sent_with_sounds_still_go(self):
        song = make_song(self.folder, "song.flac")
        notes = os.path.join(self.folder, "notes.pdf")
        open(notes, "wb").close()
        FakeChooser.values = [""]
        FakeChooser.selection = 0
        self.frame.send_paths([notes, song])
        self.assertTrue(pump(lambda: len(self.calls("send_file")) == 2))
        self.assertEqual([call[2] for call in self.calls("send_file")], [notes, song])
        self.assertEqual(len(self.sounds()), 1)

    def test_the_attach_menu_is_telegrams_in_its_order_and_words(self):
        # Unigram's: photo or video, file, music, location, poll, contact.
        self.assertEqual(c.ATTACH_COMMANDS, (
            c.MENU_SEND_MEDIA_KEY, c.MENU_SEND_FILE_KEY, c.MENU_SEND_AUDIO_KEY, c.MENU_SEND_LOCATION_KEY,
            c.MENU_NEW_POLL_KEY, c.MENU_SEND_CONTACT_KEY,
        ))
        shown = []

        def popup(menu, *args):
            shown.extend(item.GetItemLabelText() for item in menu.GetMenuItems() if not item.IsSeparator())
        with mock.patch.object(self.frame, "PopupMenu", popup):
            self.frame.on_attach(None)
        # A private chat with a person takes no poll, as in Telegram.
        self.assertEqual(shown, [self.text(c.ATTACH_LABELS[key]) for key in c.ATTACH_COMMANDS if key != c.MENU_NEW_POLL_KEY])

    def test_photo_or_video_goes_shown_in_the_chat_and_file_goes_as_it_is_without_asking(self):
        picture = os.path.join(self.folder, "a.jpg")
        open(picture, "wb").close()
        for handler, as_documents in ((self.frame.on_send_media_menu, False), (self.frame.on_send_file_menu, True)):
            FakeChooser.values = [""]
            FakeChooser.last_choices = None
            with mock.patch.object(wx, "FileDialog") as file_dialog:
                file_dialog.return_value.__enter__.return_value.ShowModal.return_value = wx.ID_OK
                file_dialog.return_value.__enter__.return_value.GetPaths.return_value = [picture]
                handler(None)
            self.assertTrue(pump(lambda: self.frame.upload is None and self.calls("send_file")))
            self.assertIsNone(FakeChooser.last_choices)
            self.assertEqual(self.calls("send_file")[-1][4], as_documents)
            FakeTelegramClient.calls.clear()
