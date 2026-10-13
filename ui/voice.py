import os
import wx
from core import audio, sounds
from core.settings import (
    SETTING_VOICE_SPEED, SETTING_MIC_DEVICE, SETTING_MIC_LEVEL, SETTING_NOISE, SETTING_RECORD_SOUND
)
from core.constants import (
    MSG_UPLOAD_PROGRESS_FORMAT_KEY, VOICE_SPEEDS, MSG_VOICE_SPEED_FORMAT_KEY, MIC_LEVELS, NOISE_LEVELS,
    BTN_RECORD_KEY, BTN_STOP_AND_SEND_KEY, VOICE_NOTE_FILE, MIN_VOICE_SECONDS, MSG_RECORDING_KEY, MSG_RECORDING_CANCELLED_KEY,
    MSG_RECORDING_TOO_SHORT_KEY, MSG_SENDING_VOICE_KEY, MSG_VOICE_SENT_KEY, MSG_PLAYING_KEY,
    MSG_PLAYBACK_STOPPED_KEY, ERR_AUDIO_KEY, ERR_NO_AUDIO_SUPPORT_KEY, STATUS_READY_KEY,
    SOUND_RECORD_START, SOUND_RECORD_STOP
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
        elif self.can_send_now():
            self.start_recording()

    def update_record_buttons(self):
        """Make the record button say what pressing it does now, and offer Cancel only mid-recording."""
        recording = self.recorder.is_recording()
        self.record_btn.SetLabel(self.i18n.get_string(BTN_STOP_AND_SEND_KEY if recording else BTN_RECORD_KEY))
        self.cancel_record_btn.Show(recording)
        self.panel.Layout()

    def start_recording(self):
        self.stop_playback()
        # As set now: a change in the settings applies from the next recording.
        self.recorder.device = audio.find_input(self.settings.get(SETTING_MIC_DEVICE))
        self.recorder.level = MIC_LEVELS[self.settings.get(SETTING_MIC_LEVEL)]
        self.recorder.reduction_db = NOISE_LEVELS[self.settings.get(SETTING_NOISE)]
        try:
            self.recorder.start()
        except Exception:
            self.recorder.cancel()
            self.show_error(ERR_AUDIO_KEY)
            return
        # The recording goes to the chat it was started in, even if another is opened meanwhile.
        self.recording_dialog_id = self.current_dialog_id
        # Where exactly: the topic or the comments it was started in, even if they are left meanwhile.
        self.recording_target = (self.peer(self.current_dialog_id), self.thread_root())
        self.update_record_buttons()
        if self.settings.get(SETTING_RECORD_SOUND):
            # A tone, and the words only on screen: spoken, they would be the start of the voice message.
            sounds.play(SOUND_RECORD_START)
            self.set_status(MSG_RECORDING_KEY)
        else:
            self.notify(MSG_RECORDING_KEY)

    def finish_recording(self):
        try:
            os.makedirs(os.path.dirname(VOICE_NOTE_FILE), exist_ok=True)
            seconds = self.recorder.finish(VOICE_NOTE_FILE)
        except Exception:
            self.recorder.cancel()
            self.update_record_buttons()
            self.show_error(ERR_AUDIO_KEY)
            return
        self.update_record_buttons()
        if self.settings.get(SETTING_RECORD_SOUND):
            sounds.play(SOUND_RECORD_STOP)
        if seconds < MIN_VOICE_SECONDS:
            self.notify(MSG_RECORDING_TOO_SHORT_KEY)
            return
        self.is_busy = True
        self.notify(MSG_SENDING_VOICE_KEY)
        dialog_id = self.recording_dialog_id
        peer, reply_to = self.recording_target
        self.telegram_manager.send_file(
            peer, VOICE_NOTE_FILE,
            self.on_ui_thread(self.on_file_sent, dialog_id, MSG_VOICE_SENT_KEY), voice_note=True, reply_to=reply_to,
            on_progress=self.progress_reporter(MSG_UPLOAD_PROGRESS_FORMAT_KEY)
        )

    def cancel_recording(self):
        self.recorder.cancel()
        self.update_record_buttons()
        # The Cancel button just vanished from under the focus; put it somewhere sensible.
        self.record_btn.SetFocus()
        self.notify(MSG_RECORDING_CANCELLED_KEY)

    def play_voice(self, path):
        # Status bar only: speaking here would talk over the start of the recording.
        self.set_status(MSG_PLAYING_KEY)
        self.player.play(
            path, lambda completed, error: wx.CallAfter(self.on_playback_finished, completed, error),
            speed=VOICE_SPEEDS[self.settings.get(SETTING_VOICE_SPEED)]
        )

    def on_voice_speed_menu(self, event):
        """Step to the next playback speed, round and round; it applies from the next voice message played."""
        speeds = list(VOICE_SPEEDS)
        speed = speeds[(speeds.index(self.settings.get(SETTING_VOICE_SPEED)) + 1) % len(speeds)]
        self.settings.set(SETTING_VOICE_SPEED, speed)
        self.settings.save()
        self.announce(self.i18n.get_string(MSG_VOICE_SPEED_FORMAT_KEY).format(speed=self.i18n.get_string(speed)))

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
