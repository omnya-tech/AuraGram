import json
import os
from core.constants import (
    SETTINGS_FILE, READ_MODE, ENCODING_UTF8, THEMES, THEME_SYSTEM,
    ANNOUNCE_WHEN_OPTIONS, ANNOUNCE_WHEN_ALWAYS, ANNOUNCE_WHAT_OPTIONS, ANNOUNCE_WHAT_FULL,
    VOICE_SPEEDS, VOICE_SPEED_NORMAL, MIC_LEVELS, MIC_LEVEL_NORMAL, NOISE_LEVELS, NOISE_OFF,
    LANGUAGES, DEFAULT_LANG, PROXY_TYPES, PROXY_NONE, CHAT_KIND_PLACES, CHAT_KIND_PLACE_AFTER,
    MESSAGE_STATS_PLACES, MESSAGE_STATS_AFTER, TIME_STYLES, TIME_STYLE_NUMBERS
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
# One of LANGUAGES; the language the whole interface loads in.
SETTING_LANGUAGE = "language"
SETTING_CHECK_UPDATES = "check_updates"
# One of CHAT_KIND_PLACES: where a group's or a channel's row says which of the two it is.
SETTING_CHAT_KIND = "chat_kind"
# One of MESSAGE_STATS_PLACES: which end of a message's row its views, comments and reactions go.
SETTING_MESSAGE_STATS = "message_stats"
# One of TIME_STYLES: how a message's row tells when it was sent.
SETTING_TIME_STYLE = "time_style"
# A tone when a voice recording starts and when it ends, in place of spoken words.
SETTING_RECORD_SOUND = "record_sound"
# On: Enter sends and Shift+Enter starts a new line. Off: Enter starts a new line and Ctrl+Enter sends.
SETTING_ENTER_SENDS = "enter_sends"
# How Telegram is reached: one of PROXY_TYPES, and what that kind of proxy needs. All text, the port too.
SETTING_PROXY_TYPE = "proxy_type"
SETTING_PROXY_HOST = "proxy_host"
SETTING_PROXY_PORT = "proxy_port"
SETTING_PROXY_USER = "proxy_user"
SETTING_PROXY_PASSWORD = "proxy_password"
SETTING_PROXY_SECRET = "proxy_secret"
# The user's own Google Gemini API key, for describing pictures; empty leaves that turned off.
SETTING_GEMINI_KEY = "gemini_key"
# Not an on/off option: {command: shortcut} for the commands whose shortcut the user changed,
# "" where they took it away. See core/shortcuts.py for the ones every command starts with.
SETTING_SHORTCUTS = "shortcuts"
# The shortcuts already reported as held by other programs, so the same news is not told at every start.
SHORTCUT_CONFLICTS_TOLD = "shortcut_conflicts_told"

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
    SETTING_CHECK_UPDATES: True,
    SETTING_RECORD_SOUND: True,
    SETTING_ENTER_SENDS: True,
}
# Settings that are one of a fixed list: (what may be stored, what it is until chosen).
CHOICES = {
    SETTING_THEME: (THEMES, THEME_SYSTEM),
    SETTING_ANNOUNCE_WHEN: (ANNOUNCE_WHEN_OPTIONS, ANNOUNCE_WHEN_ALWAYS),
    SETTING_ANNOUNCE_WHAT: (ANNOUNCE_WHAT_OPTIONS, ANNOUNCE_WHAT_FULL),
    SETTING_VOICE_SPEED: (tuple(VOICE_SPEEDS), VOICE_SPEED_NORMAL),
    SETTING_MIC_LEVEL: (tuple(MIC_LEVELS), MIC_LEVEL_NORMAL),
    SETTING_NOISE: (tuple(NOISE_LEVELS), NOISE_OFF),
    SETTING_LANGUAGE: (LANGUAGES, DEFAULT_LANG),
    SETTING_PROXY_TYPE: (PROXY_TYPES, PROXY_NONE),
    SETTING_CHAT_KIND: (CHAT_KIND_PLACES, CHAT_KIND_PLACE_AFTER),
    SETTING_MESSAGE_STATS: (MESSAGE_STATS_PLACES, MESSAGE_STATS_AFTER),
    SETTING_TIME_STYLE: (TIME_STYLES, TIME_STYLE_NUMBERS),
}
# Settings that are free text.
TEXTS = {
    SETTING_MIC_DEVICE: "", SETTING_PROXY_HOST: "", SETTING_PROXY_PORT: "", SETTING_PROXY_USER: "",
    SETTING_PROXY_PASSWORD: "", SETTING_PROXY_SECRET: "", SETTING_GEMINI_KEY: "",
}

class Settings:
    """The app's own preferences, kept in a JSON file on this computer only."""

    def __init__(self):
        self.values = dict(DEFAULTS)
        for key, (allowed, default) in CHOICES.items():
            self.values[key] = default
        self.values.update(TEXTS)
        self.values[SETTING_SHORTCUTS] = {}
        self.values[SHORTCUT_CONFLICTS_TOLD] = []
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
        changed = stored.get(SETTING_SHORTCUTS)
        if isinstance(changed, dict) and all(isinstance(text, str) for text in changed.values()):
            self.values[SETTING_SHORTCUTS] = changed
        told = stored.get(SHORTCUT_CONFLICTS_TOLD)
        if isinstance(told, list) and all(isinstance(text, str) for text in told):
            self.values[SHORTCUT_CONFLICTS_TOLD] = told

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
