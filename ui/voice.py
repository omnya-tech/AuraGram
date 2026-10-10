import os
import wx
from core import audio
from core.constants import (
    VOICE_NOTE_FILE, MIN_VOICE_SECONDS, MSG_RECORDING_KEY, MSG_RECORDING_CANCELLED_KEY,
    MSG_RECORDING_TOO_SHORT_KEY, MSG_SENDING_VOICE_KEY, MSG_VOICE_SENT_KEY, MSG_PLAYING_KEY,
    MSG_PLAYBACK_STOPPED_KEY, ERR_AUDIO_KEY, ERR_NO_AUDIO_SUPPORT_KEY, STATUS_READY_KEY
)

class VoiceMixin:
    """Recording voice notes and playing them back.

    Mixed into MainFrame, which owns the widgets and the shared state.
    """

    def on_record_menu(self, event):
        if not audio.AVAILABLE:
            self.show_error(ERR_NO_AUDIO_SUPPORT_KEY)
        elif self.recorder.is_recording():
            self.finish_recording()
        elif self.current_dialog_id is not None and not self.is_busy:
            self.start_recording()

    def start_recording(self):
        self.stop_playback()
        try:
            self.recorder.start()
        except Exception:
            self.recorder.cancel()
            self.show_error(ERR_AUDIO_KEY)
            return
        # The recording goes to the chat it was started in, even if another is opened meanwhile.
        self.recording_dialog_id = self.current_dialog_id
        self.notify(MSG_RECORDING_KEY)

    def finish_recording(self):
        try:
            os.makedirs(os.path.dirname(VOICE_NOTE_FILE), exist_ok=True)
            seconds = self.recorder.finish(VOICE_NOTE_FILE)
        except Exception:
            self.recorder.cancel()
            self.show_error(ERR_AUDIO_KEY)
            return
        if seconds < MIN_VOICE_SECONDS:
            self.notify(MSG_RECORDING_TOO_SHORT_KEY)
            return
        self.is_busy = True
        self.notify(MSG_SENDING_VOICE_KEY)
        dialog_id = self.recording_dialog_id
        self.telegram_manager.send_file(
            dialog_id, VOICE_NOTE_FILE,
            self.on_ui_thread(self.on_file_sent, dialog_id, MSG_VOICE_SENT_KEY), voice_note=True
        )

    def cancel_recording(self):
        self.recorder.cancel()
        self.notify(MSG_RECORDING_CANCELLED_KEY)

    def play_voice(self, path):
        # Status bar only: speaking here would talk over the start of the recording.
        self.set_status(MSG_PLAYING_KEY)
        self.player.play(
            path, lambda completed, error: wx.CallAfter(self.on_playback_finished, completed, error)
        )

    def on_playback_finished(self, completed, error):
        if not self:
            return
        if error is not None:
            self.show_error(ERR_AUDIO_KEY)
        elif completed:
            self.set_status(STATUS_READY_KEY)

    def stop_playback(self):
        """Returns True if something was playing."""
        if not self.player.is_playing():
            return False
        self.player.stop()
        self.notify(MSG_PLAYBACK_STOPPED_KEY)
        return True
