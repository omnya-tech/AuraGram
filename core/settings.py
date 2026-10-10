import json
import os
from core.constants import SETTINGS_FILE, READ_MODE, ENCODING_UTF8, THEMES, THEME_SYSTEM

SETTING_PLAY_SOUND = "play_sound"
SETTING_ANNOUNCE_MESSAGES = "announce_messages"
SETTING_OPEN_ON_SELECT = "open_on_select"
SETTING_MARK_READ_ON_OPEN = "mark_read_on_open"
SETTING_SENT_SOUND = "sent_sound"
SETTING_KEEP_IN_BACKGROUND = "keep_in_background"
SETTING_LARGE_TEXT = "large_text"
# Not an on/off option: where the main window was left, as [x, y, width, height, maximized].
WINDOW_PLACEMENT = "window_placement"
# One of the THEMES names.
SETTING_THEME = "theme"

DEFAULTS = {
    SETTING_LARGE_TEXT: False,
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
        self.values[SETTING_THEME] = THEME_SYSTEM
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
        if stored.get(SETTING_THEME) in THEMES:
            self.values[SETTING_THEME] = stored[SETTING_THEME]
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
