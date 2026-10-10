import json
import os
from core.constants import SETTINGS_FILE, READ_MODE, ENCODING_UTF8

SETTING_PLAY_SOUND = "play_sound"
SETTING_ANNOUNCE_MESSAGES = "announce_messages"
SETTING_OPEN_ON_SELECT = "open_on_select"
SETTING_MARK_READ_ON_OPEN = "mark_read_on_open"
SETTING_SENT_SOUND = "sent_sound"
SETTING_KEEP_IN_BACKGROUND = "keep_in_background"

DEFAULTS = {
    SETTING_PLAY_SOUND: True,
    SETTING_SENT_SOUND: True,
    SETTING_KEEP_IN_BACKGROUND: True,
    SETTING_ANNOUNCE_MESSAGES: True,
    SETTING_OPEN_ON_SELECT: True,
    SETTING_MARK_READ_ON_OPEN: True,
}

class Settings:
    """The app's own preferences, kept in a JSON file on this computer only."""

    def __init__(self):
        self.values = dict(DEFAULTS)
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

    def save(self):
        with open(SETTINGS_FILE, "w", encoding=ENCODING_UTF8) as file:
            json.dump(self.values, file, indent=4)

    def get(self, key):
        return self.values[key]

    def set(self, key, value):
        self.values[key] = value
