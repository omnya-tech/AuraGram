"""The download manager, a channel's own posts without its name on every row, and how loud the tones play."""
import io
import os
import tempfile
import unittest
import wave
from array import array
from unittest import mock

import wx

import core.constants as c
import core.settings as s
import ui.download_files_dialog
import ui.downloads
from core import sounds
from tests.harness import FakeChooser, FakeTelegramClient, Record, WindowTestCase, make_channel, make_message, make_user, pump
from ui.download_files_dialog import DownloadFilesDialog
from ui.downloads import folder_name

ALI = make_user(1, "Ali")
NEWS = make_channel(41, "News: daily")


def attached(name=None, size=0, duration=None):
    return Record(name=name, size=size, duration=duration)


class FakeFilesDialog(FakeChooser):
    """Stands in for the window of a chat's files; `picked` is what it answers."""

    rows = None

    def __init__(self, parent, i18n, chat_title, rows):
        FakeFilesDialog.rows = list(rows)
        FakeFilesDialog.title = chat_title

    def chosen(self):
        return list(FakeChooser.picked)


class DownloadManagerTest(WindowTestCase):
    chats = [(NEWS, 0, False), (ALI, 0, False)]
    history = {-1000000000041: [
        make_message(1, "lesson one", sender=NEWS, document=True, file=attached("one.pdf", 10)),
        make_message(2, "just words", sender=NEWS),
        make_message(3, sender=NEWS, audio=True, file=attached("two.mp3", 20, 60)),
        make_message(4, sender=NEWS, photo=True, file=attached(None, 30)),
    ]}

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp()
        for patch in (
            mock.patch.object(ui.downloads, "DownloadFilesDialog", FakeFilesDialog),
            mock.patch.object(ui.downloads, "DOWNLOADS_DIR", self.folder),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def downloads(self):
        return [call[1] for call in self.calls("download")]

    def start(self, picked):
        FakeChooser.picked = picked
        self.frame.dialogs_list.SetSelection(0)
        self.frame.on_download_files_menu(None)

    def test_only_messages_with_a_file_are_offered_oldest_first(self):
        self.start([])
        self.assertTrue(pump(lambda: FakeFilesDialog.rows is not None and len(FakeFilesDialog.rows) == 3))
        self.assertIn("one.pdf", FakeFilesDialog.rows[0])
        self.assertIn("two.mp3", FakeFilesDialog.rows[1])
        self.assertIn(self.text("MEDIA_PHOTO"), FakeFilesDialog.rows[2])

    def test_chosen_files_come_down_one_after_another_into_a_folder_named_after_the_chat(self):
        FakeFilesDialog.rows = None
        self.start([0, 2])
        self.assertTrue(pump(lambda: self.downloads() == [1, 4] and self.frame.download_current is None))
        folders = {call[2] for call in self.calls("download")}
        self.assertEqual(folders, {os.path.join(self.folder, "News_ daily") + os.sep})
        self.assertEqual(self.spoken[-1], self.text(c.MSG_DOWNLOADS_DONE_FORMAT_KEY).format(total=2))

    def test_a_file_already_saved_whole_is_not_fetched_again(self):
        target = os.path.join(self.folder, "News_ daily")
        os.makedirs(target)
        with open(os.path.join(target, "one.pdf"), "wb") as saved:
            saved.write(b"x" * 10)
        self.start([0, 1])
        self.assertTrue(pump(lambda: self.downloads() == [3] and self.frame.download_current is None))

    def test_cancelling_leaves_the_rest_of_the_queue_alone(self):
        self.frame.download_queue = []
        self.start([0, 1, 2])
        self.assertTrue(pump(lambda: self.frame.download_current is not None))
        self.frame.on_cancel_downloads_menu(None)
        self.assertEqual(self.frame.download_queue, [])
        self.assertTrue(pump(lambda: self.frame.download_current is None))
        self.assertEqual(len(self.downloads()), 1)

    def test_status_says_nothing_is_downloading_when_idle(self):
        self.frame.on_download_status_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NO_DOWNLOADS_KEY))

    def test_a_chat_without_files_says_so(self):
        self.frame.dialogs_list.SetSelection(1)
        self.frame.on_download_files_menu(None)
        self.assertTrue(pump(lambda: self.spoken and self.spoken[-1] == self.text(c.MSG_NO_FILES_KEY)))

    def test_channel_posts_do_not_repeat_the_channel_name(self):
        self.open_chat(0)
        rows = [self.frame.messages_list.GetString(index) for index in range(self.frame.messages_list.GetCount())]
        self.assertTrue(any("lesson one" in row for row in rows), rows)
        for row in rows:
            self.assertNotIn("News: daily", row)


class FilesDialogTest(unittest.TestCase):
    def setUp(self):
        from tests.harness import get_app
        from core.i18n import I18NManager
        get_app()
        self.dialog = DownloadFilesDialog(None, I18NManager("ar"), "News", ["a", "b", "c"])
        self.addCleanup(self.dialog.Destroy)
        patch = mock.patch.object(ui.download_files_dialog, "speak", lambda text: None)
        patch.start()
        self.addCleanup(patch.stop)

    def test_one_by_one_or_all_at_once(self):
        self.assertEqual(self.dialog.chosen(), [])
        self.dialog.files_list.Check(1)
        self.assertEqual(self.dialog.chosen(), [1])
        self.dialog.check_all(True)
        self.assertEqual(self.dialog.chosen(), [0, 1, 2])
        self.dialog.check_all(False)
        self.assertEqual(self.dialog.chosen(), [])


class FolderNameTest(unittest.TestCase):
    def test_characters_windows_refuses_are_replaced(self):
        self.assertEqual(folder_name('a/b:c*d?"e"<f>|g\\h'), "a_b_c_d__e__f__g_h")
        self.assertEqual(folder_name("dots..."), "dots")
        self.assertEqual(folder_name("..."), "_")


class ToneVolumeTest(unittest.TestCase):
    def wav(self, samples, width=2):
        output = io.BytesIO()
        with wave.open(output, "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(width)
            target.setframerate(8000)
            target.writeframes(array("h" if width == 2 else "B", samples).tobytes())
        return output.getvalue()

    def samples(self, data, width=2):
        with wave.open(io.BytesIO(data), "rb") as source:
            return list(array("h" if width == 2 else "B", source.readframes(source.getnframes())))

    def test_samples_are_scaled_and_silence_stays_silent(self):
        self.assertEqual(self.samples(sounds.quieter(self.wav([1000, -2000, 0]), 0.5)), [500, -1000, 0])
        self.assertEqual(self.samples(sounds.quieter(self.wav([228, 28, 128], 1), 0.5), 1), [178, 78, 128])

    def test_what_is_not_a_wav_is_left_as_it_is(self):
        self.assertEqual(sounds.quieter(b"nonsense", 0.5), b"nonsense")

    def test_every_volume_has_its_words_and_full_is_the_default(self):
        self.assertEqual(s.CHOICES[s.SETTING_SOUND_VOLUME][1], c.SOUND_VOLUME_FULL)
        from core.i18n import I18NManager
        for language in c.LANGUAGES:
            strings = I18NManager(language).strings
            for name in c.SOUND_VOLUMES:
                self.assertIn(name, strings)
