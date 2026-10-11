"""Replacing the app's tones with the user's own audio files, from the settings."""
import os
import tempfile
import unittest
import wave
from unittest import mock

import numpy

import core.constants as c
import core.sounds as sounds
from core import audio
from tests.harness import WindowTestCase, make_user
from ui.settings_dialog import SettingsDialog

ALI = make_user(1, "Ali")


def write_wav(path, seconds, rate=22050):
    t = numpy.arange(int(rate * seconds)) / rate
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes((numpy.sin(2 * numpy.pi * 440 * t) * 8000).astype("<i2").tobytes())


def wav_seconds(path):
    with wave.open(path, "rb") as wav:
        return wav.getnframes() / wav.getframerate()


class CustomSoundsTest(WindowTestCase):
    chats = [(ALI, 0, False)]

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp()
        self.previewed = []
        for patch in (
            mock.patch.object(sounds, "USER_SOUNDS_DIR", os.path.join(self.folder, "mine")),
            mock.patch.object(sounds, "play_file", self.previewed.append),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.source = os.path.join(self.folder, "my tone.wav")
        write_wav(self.source, 0.3)
        self.dialog = SettingsDialog(self.frame, self.i18n, self.frame.settings, self.manager)
        self.addCleanup(self.dialog.Destroy)

    def row(self, name):
        return self.dialog.sounds_list.GetString(c.SOUND_NAMES.index(name))

    def test_every_tone_is_listed_with_where_it_comes_from(self):
        self.assertEqual(self.dialog.sounds_list.GetCount(), len(c.SOUND_NAMES))
        for name in c.SOUND_NAMES:
            self.assertIn(self.text(c.SOUND_LABEL_KEY_PREFIX + name), self.row(name))
            self.assertIn(self.text(c.SOUND_SOURCE_DEFAULT_KEY), self.row(name))

    def test_chosen_file_is_heard_at_once_but_replaces_the_tone_only_on_saving(self):
        self.dialog.use_sound_file(c.SOUND_SENT, self.source)
        self.assertIn(self.text(c.SOUND_SOURCE_CUSTOM_KEY), self.row(c.SOUND_SENT))
        self.assertIn(self.text(c.SOUND_SOURCE_DEFAULT_KEY), self.row(c.SOUND_MESSAGE))
        self.assertEqual(len(self.previewed), 1)
        self.assertIn("my tone.wav", self.spoken[-1])
        self.assertFalse(sounds.has_custom(c.SOUND_SENT))

        self.dialog.apply_app_settings()
        self.assertTrue(sounds.has_custom(c.SOUND_SENT))
        self.assertEqual(sounds.path_of(c.SOUND_SENT), sounds.custom_path(c.SOUND_SENT))
        self.assertFalse(sounds.has_custom(c.SOUND_MESSAGE))
        self.assertTrue(sounds.path_of(c.SOUND_MESSAGE).startswith(c.SOUNDS_DIR))

    def test_cancelling_leaves_the_tones_alone_and_no_drafts_behind(self):
        self.dialog.use_sound_file(c.SOUND_MESSAGE, self.source)
        drafts = self.dialog.sound_drafts_dir
        self.dialog.Destroy()
        self.assertFalse(sounds.has_custom(c.SOUND_MESSAGE))
        self.assertFalse(os.path.exists(drafts))

    def test_going_back_to_the_bundled_tone(self):
        self.dialog.use_sound_file(c.SOUND_MESSAGE, self.source)
        self.dialog.apply_app_settings()
        again = SettingsDialog(self.frame, self.i18n, self.frame.settings, self.manager)
        self.addCleanup(again.Destroy)
        index = c.SOUND_NAMES.index(c.SOUND_MESSAGE)
        self.assertIn(self.text(c.SOUND_SOURCE_CUSTOM_KEY), again.sounds_list.GetString(index))
        again.sounds_list.SetSelection(index)
        again.on_default_sound(None)
        self.assertIn(self.text(c.SOUND_SOURCE_DEFAULT_KEY), again.sounds_list.GetString(index))
        # Trying it now plays the bundled file, though the user's is still there until saving.
        again.on_test_sound(None)
        self.assertTrue(self.previewed[-1].startswith(c.SOUNDS_DIR))
        self.assertTrue(sounds.has_custom(c.SOUND_MESSAGE))
        again.apply_app_settings()
        self.assertFalse(sounds.has_custom(c.SOUND_MESSAGE))

    def test_file_that_is_not_audio_is_refused(self):
        bad = os.path.join(self.folder, "notes.wav")
        with open(bad, "w") as file:
            file.write("not a sound")
        self.dialog.use_sound_file(c.SOUND_SENT, bad)
        self.assertEqual(self.boxes, [self.text(c.ERR_SOUND_FILE_KEY)])
        self.assertEqual(self.dialog.sound_changes, {})
        self.assertEqual(self.previewed, [])

    @unittest.skipUnless(audio.AVAILABLE, "needs the audio packages")
    def test_other_formats_are_converted_and_long_files_cut(self):
        song = os.path.join(self.folder, "song.ogg")
        audio.encode_voice(numpy.zeros(audio.SAMPLE_RATE * (c.CUSTOM_SOUND_MAX_SECONDS + 5), dtype="int16"), song)
        self.dialog.use_sound_file(c.SOUND_SENT, song)
        self.assertEqual(self.boxes, [])
        self.assertAlmostEqual(wav_seconds(self.dialog.sound_changes[c.SOUND_SENT]), c.CUSTOM_SOUND_MAX_SECONDS, places=1)
