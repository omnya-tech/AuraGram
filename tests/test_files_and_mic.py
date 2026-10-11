"""Saying what a file is, and the microphone: which one, how loud, and how much of the noise behind the voice goes."""
import json
import os
import tempfile
import unittest
from unittest import mock

import numpy
import wx

import core.constants as c
import core.settings as s
import ui.settings_dialog
from core import audio
from core.i18n import I18NManager
from tests.harness import FakeChooser, Record, WindowTestCase, make_message, make_user, pump
from ui.layout import duration_text, file_kind, file_size
from ui.settings_dialog import SettingsDialog

ALI = make_user(1, "Ali")
RATE = audio.SAMPLE_RATE


def attached(name=None, size=0, duration=None):
    return Record(name=name, size=size, duration=duration)


class FileNamingTest(unittest.TestCase):
    def setUp(self):
        self.i18n = I18NManager("ar")

    def test_kind_is_told_from_the_end_of_the_name_whatever_its_case(self):
        text = self.i18n.get_string
        self.assertEqual(file_kind(self.i18n, "Report.PDF"), text("FILE_KIND_PDF"))
        self.assertEqual(file_kind(self.i18n, "backup.tar.gz"), text("FILE_KIND_ARCHIVE"))
        self.assertEqual(file_kind(self.i18n, "setup.exe"), text("FILE_KIND_PROGRAM"))
        self.assertEqual(file_kind(self.i18n, "data.xyz"), text(c.FILE_KIND_OTHER_FORMAT_KEY).format(extension="XYZ"))
        self.assertEqual(file_kind(self.i18n, "README"), "")

    def test_every_kind_has_its_text_and_no_ending_belongs_to_two(self):
        endings = [ending for kind, group in c.FILE_KINDS for ending in group]
        self.assertEqual(len(endings), len(set(endings)))
        for kind, group in c.FILE_KINDS:
            self.assertIn(kind, self.i18n.strings)
        for unit in c.FILE_SIZE_UNITS:
            self.assertIn(unit, self.i18n.strings)

    def test_sizes_read_the_way_people_say_them(self):
        units = [self.i18n.get_string(unit) for unit in c.FILE_SIZE_UNITS]
        for size, expected in (
            (0, "0 " + units[0]), (1023, "1023 " + units[0]), (1024, "1 " + units[1]), (1536, "1.5 " + units[1]),
            (2400000, "2.3 " + units[2]), (150 * 1024 ** 2, "150 " + units[2]), (3 * 1024 ** 3, "3 " + units[3]),
        ):
            self.assertEqual(file_size(self.i18n, size), expected)

    def test_durations(self):
        self.assertEqual([duration_text(seconds) for seconds in (5, 42, 185, 59.6)], ["0:05", "0:42", "3:05", "1:00"])


class FilesInChatTest(WindowTestCase):
    chats = [(ALI, 0, False)]
    history = {1: [
        make_message(1, "the numbers", sender=ALI, document=True, file=attached("report.pdf", 2400000)),
        make_message(2, sender=ALI, voice=True, file=attached(None, 30000, 42)),
        make_message(3, sender=ALI, photo=True, file=attached(None, 90000)),
        make_message(4, sender=ALI, audio=True, file=attached("song.mp3", 5 * 1024 ** 2, 185)),
        make_message(5, sender=ALI, document=True, file=attached("setup.exe", 1024)),
        make_message(6, "plain words", sender=ALI),
    ]}

    def test_rows_say_what_each_attachment_is(self):
        self.open_chat(0)
        rows = [self.frame.messages_list.GetString(index) for index in range(6)]
        megabytes = self.text("FILE_SIZE_MB")
        # A file: its real kind instead of the bare word "file", its name, its size, and the caption after.
        self.assertIn("[%s، report.pdf، 2.3 %s] the numbers" % (self.text("FILE_KIND_PDF"), megabytes), rows[0])
        self.assertNotIn(self.text("MEDIA_FILE") + "،", rows[0])
        # A voice message: how long it is.
        self.assertIn("[%s، 0:42، " % self.text("MEDIA_VOICE"), rows[1])
        # A photo: nothing more to say.
        self.assertIn("[%s]" % self.text("MEDIA_PHOTO"), rows[2])
        self.assertIn("[%s، song.mp3، 3:05، 5 %s]" % (self.text("MEDIA_AUDIO"), megabytes), rows[3])
        # Something that would run if opened is called that.
        self.assertIn(self.text("FILE_KIND_PROGRAM"), rows[4])
        self.assertNotIn("[", rows[5])
        self.assertIsNone(self.frame.messages[5]["file"])

    def test_files_are_named_and_sized_before_they_are_sent(self):
        self.open_chat(0)
        path = os.path.join(tempfile.mkdtemp(), "notes.txt")
        with open(path, "wb") as file:
            file.write(b"x" * 2048)
        FakeChooser.values = [""]
        self.frame.send_paths([path, "gone.zip"])
        self.assertTrue(pump(lambda: self.calls("send_file")))
        asked = FakeChooser.last_message
        self.assertIn("notes.txt، %s، 2 %s" % (self.text("FILE_KIND_TEXT"), self.text("FILE_SIZE_KB")), asked)
        # A file that is not there has a name and a kind, but no size to give.
        self.assertIn("gone.zip، " + self.text("FILE_KIND_ARCHIVE"), asked)
        self.assertIn(self.text(c.MSG_CAPTION_PROMPT_KEY), asked)


@unittest.skipUnless(audio.AVAILABLE, "needs the audio packages")
class CleaningTest(unittest.TestCase):
    """Measured on a made-up voice (a wandering pitch with its overtones, in bursts) over hiss and mains hum."""

    @classmethod
    def setUpClass(cls):
        rng = numpy.random.default_rng(1)
        t = numpy.arange(RATE * 6) / RATE
        phase = 2 * numpy.pi * numpy.cumsum(150 + 20 * numpy.sin(2 * numpy.pi * 0.7 * t)) / RATE
        cls.speaking = numpy.floor(t * 1.5) % 2 == 1
        cls.voice = sum(numpy.sin(k * phase) / k for k in range(1, 20)) * 3000 * cls.speaking
        noise = rng.normal(0, 400, len(t)) + numpy.sin(2 * numpy.pi * 50 * t) * 500
        cls.noisy = numpy.clip(cls.voice + noise, -32768, 32767).astype("int16")

    def loudness(self, samples):
        return 20 * numpy.log10(numpy.sqrt(numpy.mean(numpy.asarray(samples, dtype=float) ** 2)) + 1e-9)

    def test_each_step_takes_more_of_the_noise_and_leaves_the_voice(self):
        before = self.loudness(self.noisy[~self.speaking])
        dropped = []
        for name, reduction in c.NOISE_LEVELS.items():
            cleaned = audio.reduce_noise(self.noisy, reduction).astype(float)
            dropped.append(before - self.loudness(cleaned[~self.speaking]))
            spoken, reference = cleaned[self.speaking], self.voice[self.speaking]
            kept = numpy.dot(spoken, reference) / numpy.dot(reference, reference)
            # The voice comes through at nine tenths or more of its strength at every step.
            self.assertGreater(kept, 0.9, name)
            self.assertLess(kept, 1.05, name)
        self.assertEqual(dropped[0], 0)
        self.assertGreater(dropped[1], 5)
        self.assertGreater(dropped[2], dropped[1] + 2)
        self.assertGreater(dropped[3], dropped[2] + 2)

    def test_recording_without_noise_comes_out_as_it_went_in(self):
        clean = self.voice.astype("int16")
        cleaned = audio.reduce_noise(clean, c.NOISE_LEVELS["NOISE_STRONG"]).astype(float)
        changed = self.loudness(cleaned - self.voice)
        self.assertGreater(self.loudness(self.voice) - changed, 30)
        self.assertEqual(len(cleaned), len(clean))

    def test_off_and_too_short_to_judge_are_left_alone(self):
        self.assertIs(audio.reduce_noise(self.noisy, 0), self.noisy)
        short = self.noisy[:1000]
        self.assertIs(audio.reduce_noise(short, 20), short)

    def test_level_never_clips(self):
        quiet = (numpy.sin(numpy.arange(RATE) / 20) * 2000).astype("int16")
        loud = (numpy.sin(numpy.arange(RATE) / 20) * 30000).astype("int16")
        self.assertAlmostEqual(numpy.abs(audio.set_level(quiet, 1.8)).max(), 3600, delta=5)
        self.assertAlmostEqual(numpy.abs(audio.set_level(quiet, 0.6)).max(), 1200, delta=5)
        # Asked for more than there is room for: as loud as it goes, with its shape intact.
        raised = audio.set_level(loud, 1.8)
        self.assertLessEqual(numpy.abs(raised.astype(int)).max(), audio.LOUDEST)
        self.assertGreater(numpy.corrcoef(raised, loud)[0, 1], 0.9999)

    def test_automatic_level_fills_the_room_but_does_not_blow_up_near_silence(self):
        quiet = (numpy.sin(numpy.arange(RATE) / 20) * 8000).astype("int16")
        self.assertAlmostEqual(numpy.abs(audio.set_level(quiet, None)).max(), audio.LOUDEST * audio.AUTO_LEVEL_PEAK, delta=50)
        hiss = (numpy.sin(numpy.arange(RATE) / 20) * 10).astype("int16")
        self.assertLessEqual(numpy.abs(audio.set_level(hiss, None)).max(), 10 * audio.AUTO_LEVEL_MAX_GAIN)
        silence = numpy.zeros(100, dtype="int16")
        self.assertIs(audio.set_level(silence, None), silence)


class FakeTester:
    """A microphone that hears whatever the test gives it."""

    def __init__(self, samples):
        self.samples = samples
        self.started = 0

    def start(self):
        self.started += 1

    def take(self):
        return self.samples

    def cancel(self):
        pass


class MicrophoneSettingsTest(WindowTestCase):
    chats = [(ALI, 0, False)]

    def settings_dialog(self, devices=("Desk mic", "Headset")):
        with mock.patch.object(audio, "input_devices", return_value=list(devices)):
            dialog = SettingsDialog(self.frame, self.i18n, self.frame.settings, self.manager)
        self.addCleanup(dialog.Destroy)
        return dialog

    def test_microphone_level_and_cleaning_are_chosen_and_kept(self):
        dialog = self.settings_dialog()
        self.assertEqual(dialog.mic_choice.GetStrings(), [self.text(c.MIC_DEVICE_DEFAULT_KEY), "Desk mic", "Headset"])
        self.assertEqual(dialog.mic_choice.GetSelection(), 0)
        dialog.mic_choice.SetSelection(2)
        dialog.choices[s.SETTING_NOISE].SetSelection(list(c.NOISE_LEVELS).index("NOISE_MEDIUM"))
        dialog.choices[s.SETTING_MIC_LEVEL].SetSelection(list(c.MIC_LEVELS).index("MIC_LEVEL_AUTO"))
        dialog.apply_app_settings()
        saved = s.Settings()
        self.assertEqual(saved.get(s.SETTING_MIC_DEVICE), "Headset")
        self.assertEqual(saved.get(s.SETTING_NOISE), "NOISE_MEDIUM")
        self.assertEqual(saved.get(s.SETTING_MIC_LEVEL), "MIC_LEVEL_AUTO")
        self.assertEqual(self.settings_dialog().mic_choice.GetStringSelection(), "Headset")

    def test_microphone_that_was_unplugged_falls_back_to_the_default(self):
        self.frame.settings.set(s.SETTING_MIC_DEVICE, "Headset")
        dialog = self.settings_dialog(devices=("Desk mic",))
        self.assertEqual(dialog.mic_choice.GetSelection(), 0)
        with mock.patch.object(audio.sounddevice, "query_devices", return_value=[]):
            self.assertIsNone(audio.find_input("Headset"))

    def test_setting_saved_as_something_else_than_text_is_ignored(self):
        path = os.path.join(tempfile.mkdtemp(), "settings.json")
        with open(path, "w") as file:
            json.dump({s.SETTING_MIC_DEVICE: 7, s.SETTING_NOISE: "NOISE_EXTREME"}, file)
        with mock.patch.object(s, "SETTINGS_FILE", path):
            settings = s.Settings()
        self.assertEqual(settings.get(s.SETTING_MIC_DEVICE), "")
        self.assertEqual(settings.get(s.SETTING_NOISE), c.NOISE_OFF)

    def test_recording_uses_the_microphone_settings_of_the_moment(self):
        self.frame.settings.set(s.SETTING_NOISE, "NOISE_STRONG")
        self.frame.settings.set(s.SETTING_MIC_LEVEL, "MIC_LEVEL_HIGH")
        self.frame.settings.set(s.SETTING_MIC_DEVICE, "Headset")
        self.frame.recorder = FakeTester(numpy.zeros(0, dtype="int16"))
        self.frame.recorder.is_recording = lambda: False
        self.open_chat(0)
        with mock.patch.object(audio, "find_input", return_value=4) as find_input:
            self.frame.start_recording()
        find_input.assert_called_once_with("Headset")
        recorder = self.frame.recorder
        self.assertEqual((recorder.device, recorder.level, recorder.reduction_db), (4, 1.8, 20))
        self.assertEqual(recorder.started, 1)

    def test_test_button_records_with_what_is_chosen_and_plays_it_back(self):
        dialog = self.settings_dialog()
        heard = (numpy.sin(numpy.arange(2000) / 10) * 5000).astype("int16")
        dialog.mic_tester = FakeTester(heard)
        dialog.mic_choice.SetSelection(1)
        dialog.choices[s.SETTING_NOISE].SetSelection(list(c.NOISE_LEVELS).index("NOISE_LIGHT"))
        with mock.patch.object(ui.settings_dialog, "MIC_TEST_MS", 20), \
                mock.patch.object(audio, "AVAILABLE", True), \
                mock.patch.object(audio, "find_input", return_value=3), \
                mock.patch.object(audio, "play_samples") as play:
            dialog.on_test_mic(None)
            self.assertFalse(dialog.mic_test_btn.IsEnabled())
            self.assertEqual(self.spoken[-1], self.text(c.MSG_MIC_TEST_SPEAK_KEY))
            self.assertTrue(pump(lambda: play.called))
        # Not saved yet: the test goes by what the dialog shows.
        self.assertEqual((dialog.mic_tester.device, dialog.mic_tester.reduction_db), (3, 6))
        self.assertIs(play.call_args.args[0], heard)
        self.assertTrue(dialog.mic_test_btn.IsEnabled())
        self.assertEqual(self.frame.settings.get(s.SETTING_NOISE), c.NOISE_OFF)

    def test_microphone_that_hears_nothing_is_reported(self):
        dialog = self.settings_dialog()
        dialog.mic_tester = FakeTester(numpy.zeros(4000, dtype="int16"))
        with mock.patch.object(ui.settings_dialog, "MIC_TEST_MS", 20), \
                mock.patch.object(audio, "AVAILABLE", True), \
                mock.patch.object(audio, "find_input", return_value=None), \
                mock.patch.object(audio, "play_samples") as play:
            dialog.on_test_mic(None)
            self.assertTrue(pump(lambda: self.boxes == [self.text(c.MSG_MIC_TEST_SILENT_KEY)]))
        play.assert_not_called()
