import json
import os
from core.constants import (
    SETTINGS_FILE, READ_MODE, ENCODING_UTF8, THEMES, THEME_SYSTEM,
    ANNOUNCE_WHEN_OPTIONS, ANNOUNCE_WHEN_ALWAYS, ANNOUNCE_WHAT_OPTIONS, ANNOUNCE_WHAT_FULL,
    VOICE_SPEEDS, VOICE_SPEED_NORMAL, MIC_LEVELS, MIC_LEVEL_NORMAL, NOISE_LEVELS, NOISE_OFF
)

SETTING_PLAY_SOUND = "play_sound"
SETTING_ANNOUNCE_MESSAGES = "announce_messages"
SETTING_MARK_READ_ON_OPEN = "mark_read_on_open"
SETTING_SENT_SOUND = "sent_sound"
SETTING_KEEP_IN_BACKGROUND = "keep_in_background"
SETTING_LARGE_TEXT = "large_text"
# Not an on/off option: where the main window was left, as [x, y, width, height, maximized].
WINDOW_PLACEMENT = "window_placement"
SETTING_START_SOUND = "start_sound"
SETTING_ANNOUNCE_INTERRUPT = "announce_interrupt"
SETTING_BRAILLE_MESSAGES = "braille_messages"
SETTING_SPEAK_FEEDBACK = "speak_feedback"
SETTING_ANNOUNCE_CONNECTION = "announce_connection"
SETTING_SIMPLE_TAB = "simple_tab"
SETTING_ANNOUNCE_TYPING = "announce_typing"
SETTING_SHOW_PREVIEW = "show_preview"
# One of the THEMES names.
SETTING_THEME = "theme"
SETTING_ANNOUNCE_WHEN = "announce_when"
SETTING_ANNOUNCE_WHAT = "announce_what"
SETTING_VOICE_SPEED = "voice_speed"
SETTING_MIC_LEVEL = "mic_level"
SETTING_NOISE = "noise_reduction"
# The name of the microphone to record from; empty for the one Windows uses by default.
SETTING_MIC_DEVICE = "mic_device"

DEFAULTS = {
    SETTING_LARGE_TEXT: False,
    SETTING_PLAY_SOUND: True,
    SETTING_SENT_SOUND: True,
    SETTING_KEEP_IN_BACKGROUND: True,
    SETTING_ANNOUNCE_MESSAGES: True,
    SETTING_MARK_READ_ON_OPEN: True,
    SETTING_START_SOUND: True,
    SETTING_ANNOUNCE_INTERRUPT: False,
    SETTING_BRAILLE_MESSAGES: False,
    SETTING_SPEAK_FEEDBACK: True,
    SETTING_ANNOUNCE_CONNECTION: True,
    SETTING_SIMPLE_TAB: True,
    SETTING_ANNOUNCE_TYPING: False,
    SETTING_SHOW_PREVIEW: True,
}
# Settings that are one of a fixed list: (what may be stored, what it is until chosen).
CHOICES = {
    SETTING_THEME: (THEMES, THEME_SYSTEM),
    SETTING_ANNOUNCE_WHEN: (ANNOUNCE_WHEN_OPTIONS, ANNOUNCE_WHEN_ALWAYS),
    SETTING_ANNOUNCE_WHAT: (ANNOUNCE_WHAT_OPTIONS, ANNOUNCE_WHAT_FULL),
    SETTING_VOICE_SPEED: (tuple(VOICE_SPEEDS), VOICE_SPEED_NORMAL),
    SETTING_MIC_LEVEL: (tuple(MIC_LEVELS), MIC_LEVEL_NORMAL),
    SETTING_NOISE: (tuple(NOISE_LEVELS), NOISE_OFF),
}
# Settings that are free text.
TEXTS = {SETTING_MIC_DEVICE: ""}

class Settings:
    """The app's own preferences, kept in a JSON file on this computer only."""

    def __init__(self):
        self.values = dict(DEFAULTS)
        for key, (allowed, default) in CHOICES.items():
            self.values[key] = default
        self.values.update(TEXTS)
        self.load()

    def load(self):
        if not os.path.exists(SETTINGS_FILE):
            return
        try:
            with open(SETTINGS_FILE, READ_MODE, encoding=ENCODING_UTF8) as file:
                stored = json.load(file)
        except (OSError, ValueError):
            # A damaged file should not stop the app from starting.
            return
        for key in DEFAULTS:
            if isinstance(stored.get(key), bool):
                self.values[key] = stored[key]
        for key in TEXTS:
            if isinstance(stored.get(key), str):
                self.values[key] = stored[key]
        for key, (allowed, default) in CHOICES.items():
            if stored.get(key) in allowed:
                self.values[key] = stored[key]
        placement = stored.get(WINDOW_PLACEMENT)
        if isinstance(placement, list) and len(placement) == 5 and all(isinstance(n, int) for n in placement):
            self.values[WINDOW_PLACEMENT] = placement

    def save(self):
        with open(SETTINGS_FILE, "w", encoding=ENCODING_UTF8) as file:
            json.dump(self.values, file, indent=4)

    def get(self, key):
        return self.values[key]

    def get_window_placement(self):
        """[x, y, width, height, maximized] as last saved, or None the first time."""
        return self.values.get(WINDOW_PLACEMENT)

    def set_window_placement(self, x, y, width, height, maximized):
        self.values[WINDOW_PLACEMENT] = [x, y, width, height, int(maximized)]

    def set(self, key, value):
        self.values[key] = value
