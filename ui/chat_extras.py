import os
import tempfile
import datetime
import wx
from core import audio, sounds
from ui.downloads import folder_name
from core.constants import (
    DOWNLOADS_DIR, SOUND_FILE_PATTERNS, WAV_FILE_PATTERN, SOUND_FILES_KEY, MSG_CHOOSE_SOUND_FILE_KEY, ERR_SOUND_FILE_KEY,
    SOUND_SOURCE_CUSTOM_KEY, SOUND_SOURCE_DEFAULT_KEY, SOUND_MESSAGE, CHAT_TONE_PROMPT_FORMAT_KEY, CHAT_TONE_CHOOSE_KEY,
    CHAT_TONE_TEST_KEY, CHAT_TONE_DEFAULT_KEY, MSG_CHAT_TONE_SET_FORMAT_KEY, MSG_CHAT_TONE_CLEARED_FORMAT_KEY,
    MSG_EXPORTING_FORMAT_KEY, MSG_EXPORTED_FORMAT_KEY, EXPORT_HEADER_FORMAT_KEY, EXPORT_LINE_FORMAT_KEY, ERR_EXPORT_KEY,
    EXPORT_FILE_FORMAT, ENCODING_UTF8, STATUS_READY_KEY
)

def chat_tone(chat_id):
    """The name one chat's own tone goes by among the tones."""
    return "chat_%d" % chat_id

class ChatExtrasMixin:
    """A tone of its own for a chat, and a whole chat written out to a text file."""

    def message_tone(self, dialog_id):
        """The tone a new message of this chat plays: its own if it was given one."""
        tone = chat_tone(dialog_id)
        return tone if sounds.has_custom(tone) else SOUND_MESSAGE

    def on_chat_tone(self, chat):
        """Choose, try or take away the tone of the selected chat, until the menu is left."""
        text = self.i18n.get_string
        tone = chat_tone(chat["id"])
        while True:
            source = text(SOUND_SOURCE_CUSTOM_KEY if sounds.has_custom(tone) else SOUND_SOURCE_DEFAULT_KEY)
            index = self.pick(
                text(CHAT_TONE_PROMPT_FORMAT_KEY).format(chat=chat["title"], source=source),
                [text(CHAT_TONE_CHOOSE_KEY), text(CHAT_TONE_TEST_KEY), text(CHAT_TONE_DEFAULT_KEY)]
            )
            if index is None:
                return
            if index == 0:
                if self.choose_chat_tone(chat, tone):
                    return
            elif index == 1:
                sounds.play_file(sounds.path_of(self.message_tone(chat["id"])))
            else:
                sounds.clear_custom(tone)
                self.announce(text(MSG_CHAT_TONE_CLEARED_FORMAT_KEY).format(chat=chat["title"]))
                return

    def choose_chat_tone(self, chat, tone):
        """Ask for a sound file and make it the chat's tone; whether one was taken."""
        patterns = SOUND_FILE_PATTERNS if audio.AVAILABLE else WAV_FILE_PATTERN
        with wx.FileDialog(
            self, self.i18n.get_string(MSG_CHOOSE_SOUND_FILE_KEY),
            wildcard="%s (%s)|%s" % (self.i18n.get_string(SOUND_FILES_KEY), patterns, patterns),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_OK:
                return False
            path = file_dialog.GetPath()
        draft = os.path.join(tempfile.mkdtemp(), tone + ".wav")
        if not sounds.convert(path, draft):
            self.show_error(ERR_SOUND_FILE_KEY)
            return False
        sounds.set_custom(tone, draft)
        self.announce(self.i18n.get_string(MSG_CHAT_TONE_SET_FORMAT_KEY).format(chat=chat["title"]))
        sounds.play(tone)
        return True

    def on_export_chat(self, chat):
        self.announce(self.i18n.get_string(MSG_EXPORTING_FORMAT_KEY).format(chat=chat["title"], count=0))
        self.telegram_manager.export_messages(
            chat["id"], self.on_ui_thread(self.write_export, chat),
            on_progress=lambda count: wx.CallAfter(self.show_export_progress, chat, count)
        )

    def show_export_progress(self, chat, count):
        if self:
            self.SetStatusText(self.i18n.get_string(MSG_EXPORTING_FORMAT_KEY).format(chat=chat["title"], count=count))

    def export_text(self, chat, messages):
        """The chat as plain text: a heading, then one paragraph per message, oldest first."""
        line = self.i18n.get_string(EXPORT_LINE_FORMAT_KEY)
        parts = [self.i18n.get_string(EXPORT_HEADER_FORMAT_KEY).format(
            chat=chat["title"], time=self.time_text(datetime.datetime.now().astimezone(), True)
        )]
        for message in messages:
            # Kept whole here, line breaks and all: a file has room that a list row has not.
            parts.append(line.format(
                time=self.time_text(message["date"], True), sender=self.sender_name(message) or chat["title"],
                text=self.message_text(message)
            ))
        return "\n\n".join(parts) + "\n"

    def write_export(self, messages, chat):
        self.set_status(STATUS_READY_KEY)
        path = os.path.join(DOWNLOADS_DIR, EXPORT_FILE_FORMAT.format(name=folder_name(chat["title"])))
        try:
            os.makedirs(DOWNLOADS_DIR, exist_ok=True)
            # With a byte order mark, so Notepad and every other editor see Arabic as Arabic.
            with open(path, "w", encoding=ENCODING_UTF8 + "-sig") as export_file:
                export_file.write(self.export_text(chat, messages))
        except OSError:
            self.show_error(ERR_EXPORT_KEY)
            return
        self.announce(self.i18n.get_string(MSG_EXPORTED_FORMAT_KEY).format(count=len(messages), path=path))
