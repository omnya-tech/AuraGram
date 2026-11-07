"""A song is a song however it was sent, and the attachment's button says what pressing it does:
"Download" while the file is not here, then "Play" or "Open"."""
import os
import tempfile
from unittest import mock

import wx

import core.constants as c
import core.settings as s
from tests.harness import Record, WindowTestCase, make_message, make_user, pump

ALI = make_user(1, "Ali")


def document(message_id, name, size, mime_type, **extra):
    return make_message(message_id, sender=ALI, document=True, file=Record(
        name=name, size=size, duration=extra.pop("duration", 0), mime_type=mime_type,
        title=extra.pop("title", None), performer=extra.pop("performer", None),
    ), **extra)


class AttachmentTest(WindowTestCase):
    chats = [(ALI, 0, False)]
    history = {1: [
        # An mp3 sent as a plain file, with nothing in it saying it is a song.
        document(1, "lecture.mp3", 4000, "application/octet-stream"),
        # A song with its details, as Telegram sends music.
        make_message(2, sender=ALI, audio=True, document=True, file=Record(
            name="track01.mp3", size=5000, duration=200, mime_type="audio/mpeg", title="Ya Msafer", performer="Fairuz"
        )),
        document(3, "report.pdf", 500, "application/pdf"),
        make_message(4, "words only", sender=ALI),
    ]}

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp()
        self.frame.settings.set(s.SETTING_DOWNLOAD_FOLDER, self.folder)
        self.streams = []
        for patch in (
            mock.patch.object(self.frame.player, "play_stream", lambda buffer, on_finished, speed=1.0: self.streams.append(buffer)),
            mock.patch("core.audio.AVAILABLE", True),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.open_chat(0)
        pump(timeout=0.1)

    def select(self, index):
        self.frame.messages_list.SetSelection(index)
        self.frame.update_preview()

    def button(self):
        return next(button for button in self.frame.mouse_buttons if button.command == c.MENU_OPEN_MEDIA_KEY)

    def menu_entry(self):
        """The attachment's entry in the message's own menu (the Applications key on it)."""
        self.frame.on_message_context_menu(self.context_event(self.frame.messages_list))
        named = {self.text(key) for key in (
            c.CONTEXT_DOWNLOAD_MEDIA_KEY, c.CONTEXT_PLAY_MEDIA_KEY, c.CONTEXT_OPEN_FILE_KEY, c.CONTEXT_OPEN_MEDIA_KEY
        )}
        found = [label for label in self.menu_labels if label in named]
        return found[0] if found else None

    def test_a_sound_sent_as_a_plain_file_is_a_song_and_space_plays_it(self):
        self.assertEqual(self.frame.messages[0]["media"], c.MEDIA_AUDIO)
        self.assertEqual(self.frame.messages[2]["media"], c.MEDIA_FILE)
        self.select(0)
        event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        event.SetKeyCode(wx.WXK_SPACE)
        with mock.patch.object(wx.Window, "FindFocus", return_value=self.frame.messages_list):
            self.frame.on_char_hook(event)
        # Played as it comes from Telegram: nothing downloaded.
        self.assertEqual(len(self.streams), 1)
        self.assertEqual(self.calls("download"), [])

    def test_a_song_is_named_by_its_title_and_singer_rather_than_its_file(self):
        row = self.frame.messages_list.GetString(1)
        self.assertIn("Ya Msafer", row)
        self.assertIn("Fairuz", row)
        self.assertIn("3:20", row)
        self.assertNotIn("track01.mp3", row)
        # Without those details, the file's name is what it is known by.
        self.assertIn("lecture.mp3", self.frame.messages_list.GetString(0))

    def test_the_button_and_the_menu_say_download_then_play_or_open(self):
        self.select(2)
        self.assertEqual(self.button().GetLabel(), self.text(c.BTN_DOWNLOAD_KEY))
        self.assertEqual(self.menu_entry(), self.text(c.CONTEXT_DOWNLOAD_MEDIA_KEY))
        # There already, from an earlier run: as big as Telegram says, so it is that file.
        with open(os.path.join(self.folder, "report.pdf"), "wb") as file:
            file.write(b"x" * 500)
        self.select(2)
        self.assertEqual(self.button().GetLabel(), self.text(c.BTN_OPEN_KEY))
        self.assertEqual(self.menu_entry(), self.text(c.CONTEXT_OPEN_FILE_KEY))
        with mock.patch.object(wx, "LaunchDefaultApplication", return_value=True) as launch:
            self.frame.on_activate_message(None)
        launch.assert_called_once_with(os.path.join(self.folder, "report.pdf"))
        self.assertEqual(self.calls("download"), [])

    def test_a_file_of_the_same_name_but_another_size_is_not_taken_for_it(self):
        with open(os.path.join(self.folder, "report.pdf"), "wb") as file:
            file.write(b"other")
        self.select(2)
        self.assertEqual(self.button().GetLabel(), self.text(c.BTN_DOWNLOAD_KEY))

    def test_a_song_here_already_is_played_and_a_message_without_a_file_has_the_general_names(self):
        with open(os.path.join(self.folder, "lecture.mp3"), "wb") as file:
            file.write(b"x" * 4000)
        self.select(0)
        self.assertEqual(self.button().GetLabel(), self.text(c.BTN_PLAY_FILE_KEY))
        self.assertEqual(self.menu_entry(), self.text(c.CONTEXT_PLAY_MEDIA_KEY))
        self.select(3)
        self.assertEqual(self.button().GetLabel(), self.text(c.BTN_OPEN_KEY))
        # Nothing to download or open: the message's menu offers no entry for it at all.
        self.assertIsNone(self.menu_entry())

    def test_the_shortcut_downloads_first_too(self):
        self.select(2)
        with mock.patch.object(wx, "LaunchDefaultApplication") as launch:
            self.frame.all_commands()[c.MENU_OPEN_MEDIA_KEY](None)
            self.assertTrue(pump(lambda: self.calls("download") and not self.frame.transfers))
        self.assertFalse(launch.called)
