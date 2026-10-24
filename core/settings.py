import json
import os
import sys
from core.constants import (
    INSTALL_LANGUAGE_FILE, IS_FROZEN, BASE_DIR,
    FEEDBACK_KINDS, FEEDBACK_PERCENT, FEEDBACK_UNAVAILABLE, FEEDBACK_RESULT, FEEDBACK_CONFIRM,
    SPEECH_LEVELS, SPEECH_LEVEL_BEGINNER, SPEECH_LEVEL_INTERMEDIATE, SPEECH_LEVEL_ADVANCED,
    SETTINGS_FILE, READ_MODE, ENCODING_UTF8, THEMES, THEME_SYSTEM,
    ANNOUNCE_WHEN_OPTIONS, ANNOUNCE_WHEN_ALWAYS, ANNOUNCE_WHAT_OPTIONS, ANNOUNCE_WHAT_FULL,
    VOICE_SPEEDS, VOICE_SPEED_NORMAL, MIC_LEVELS, MIC_LEVEL_NORMAL, NOISE_LEVELS, NOISE_OFF,
    LANGUAGES, DEFAULT_LANG, PROXY_TYPES, PROXY_NONE, CHAT_KIND_PLACES, CHAT_KIND_PLACE_AFTER,
    MESSAGE_STATS_PLACES, MESSAGE_STATS_AFTER, TIME_STYLES, TIME_STYLE_NUMBERS, SOUND_VOLUMES, SOUND_VOLUME_FULL,
    DOWNLOAD_KINDS, DOWNLOAD_KINDS_ALL
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
# One of SOUND_VOLUMES: how loud the app's own tones play.
SETTING_SOUND_VOLUME = "sound_volume"
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
# The download manager. The folder is empty for the usual one; the kinds are one of DOWNLOAD_KINDS.
SETTING_DOWNLOAD_FOLDER = "download_folder"
SETTING_DOWNLOAD_PER_CHAT = "download_per_chat"
SETTING_DOWNLOAD_SKIP = "download_skip_existing"
SETTING_DOWNLOAD_SPEAK_EACH = "download_speak_each"
SETTING_DOWNLOAD_DONE_SOUND = "download_done_sound"
SETTING_DOWNLOAD_CHECK_ALL = "download_check_all"
SETTING_DOWNLOAD_KINDS = "download_kinds"
# Not an on/off option: {command: shortcut} for the commands whose shortcut the user changed,
# "" where they took it away. See core/shortcuts.py for the ones every command starts with.
SETTING_SHORTCUTS = "shortcuts"
# The shortcuts already reported as held by other programs, so the same news is not told at every start.
SHORTCUT_CONFLICTS_TOLD = "shortcut_conflicts_told"
# The ids of the chats the user put among the favourites, kept on this computer.
SETTING_FAVORITES = "favorites"
# One on/off setting for each kind of thing said besides the messages; see FEEDBACK_KINDS.
FEEDBACK_SETTINGS = {kind: "speak_" + kind for kind in FEEDBACK_KINDS}
# How much is said, as a level that ticks those, or the user's own choice of them.
SETTING_SPEECH_LEVEL = "speech_level"
# Whether the level was asked for, the first time the main window opened.
SPEECH_LEVEL_ASKED = "speech_level_asked"
# Which install's language the program last took on, so each install sets it once.
INSTALL_STAMP = "install_stamp"
# The accounts signed in on this computer, as [{"id", "name", "phone"}], and the one in use.
SETTING_ACCOUNTS = "accounts"
SETTING_CURRENT_ACCOUNT = "current_account"
# The countries Telegram listed at the last sign-in, for the next one: {"language", "countries"}.
SETTING_COUNTRIES = "countries"
# The poll settings used last, offered again for the next poll: {setting name: bool, "close_after": seconds}.
SETTING_POLL_DEFAULTS = "poll_defaults"
POLL_DEFAULT_FLAGS = ("anonymous", "multiple", "quiz", "shuffle", "hide_results", "no_revote")

DEFAULTS = {
    **{setting: kind != FEEDBACK_PERCENT for kind, setting in FEEDBACK_SETTINGS.items()},
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
    SETTING_ANNOUNCE_TYPING: True,
    SETTING_SHOW_PREVIEW: True,
    SETTING_CHECK_UPDATES: True,
    SETTING_RECORD_SOUND: True,
    SETTING_ENTER_SENDS: True,
    SETTING_DOWNLOAD_PER_CHAT: True,
    SETTING_DOWNLOAD_SKIP: True,
    SETTING_DOWNLOAD_SPEAK_EACH: False,
    SETTING_DOWNLOAD_DONE_SOUND: True,
    SETTING_DOWNLOAD_CHECK_ALL: False,
}
# Settings that are one of a fixed list: (what may be stored, what it is until chosen).
CHOICES = {
    SETTING_THEME: (THEMES, THEME_SYSTEM),
    SETTING_ANNOUNCE_WHEN: (ANNOUNCE_WHEN_OPTIONS, ANNOUNCE_WHEN_ALWAYS),
    SETTING_ANNOUNCE_WHAT: (ANNOUNCE_WHAT_OPTIONS, ANNOUNCE_WHAT_FULL),
    SETTING_VOICE_SPEED: (tuple(VOICE_SPEEDS), VOICE_SPEED_NORMAL),
    SETTING_SOUND_VOLUME: (tuple(SOUND_VOLUMES), SOUND_VOLUME_FULL),
    SETTING_DOWNLOAD_KINDS: (tuple(DOWNLOAD_KINDS), DOWNLOAD_KINDS_ALL),
    SETTING_MIC_LEVEL: (tuple(MIC_LEVELS), MIC_LEVEL_NORMAL),
    SETTING_NOISE: (tuple(NOISE_LEVELS), NOISE_OFF),
    SETTING_LANGUAGE: (LANGUAGES, DEFAULT_LANG),
    SETTING_PROXY_TYPE: (PROXY_TYPES, PROXY_NONE),
    SETTING_CHAT_KIND: (CHAT_KIND_PLACES, CHAT_KIND_PLACE_AFTER),
    SETTING_MESSAGE_STATS: (MESSAGE_STATS_PLACES, MESSAGE_STATS_AFTER),
    SETTING_TIME_STYLE: (TIME_STYLES, TIME_STYLE_NUMBERS),
    SETTING_SPEECH_LEVEL: (SPEECH_LEVELS, SPEECH_LEVEL_BEGINNER),
}
# What each level ticks among the speech settings; the others it leaves unticked. Of the ten the
# accessibility tab has for this, the beginner hears nine, the intermediate four, the advanced three.
LEVEL_SETTINGS = {
    SPEECH_LEVEL_BEGINNER: {setting for kind, setting in FEEDBACK_SETTINGS.items() if kind != FEEDBACK_PERCENT}
    | {SETTING_ANNOUNCE_CONNECTION, SETTING_ANNOUNCE_TYPING},
    SPEECH_LEVEL_INTERMEDIATE: {
        FEEDBACK_SETTINGS[FEEDBACK_UNAVAILABLE], FEEDBACK_SETTINGS[FEEDBACK_RESULT], FEEDBACK_SETTINGS[FEEDBACK_CONFIRM],
        SETTING_ANNOUNCE_CONNECTION,
    },
    SPEECH_LEVEL_ADVANCED: {
        FEEDBACK_SETTINGS[FEEDBACK_UNAVAILABLE], FEEDBACK_SETTINGS[FEEDBACK_RESULT], SETTING_ANNOUNCE_CONNECTION,
    },
}
LEVEL_OPTIONS = tuple(FEEDBACK_SETTINGS.values()) + (SETTING_ANNOUNCE_CONNECTION, SETTING_ANNOUNCE_TYPING)
# Settings that are free text.
TEXTS = {
    SETTING_MIC_DEVICE: "", SETTING_PROXY_HOST: "", SETTING_PROXY_PORT: "", SETTING_PROXY_USER: "",
    SETTING_PROXY_PASSWORD: "", SETTING_PROXY_SECRET: "", SETTING_GEMINI_KEY: "", SETTING_DOWNLOAD_FOLDER: "",
}

# What a copy of the settings in a file is known by, and what it leaves out unless asked.
BACKUP_MARK = "AuraGram settings"
BACKUP_SECRETS = (SETTING_GEMINI_KEY, SETTING_PROXY_PASSWORD, SETTING_PROXY_SECRET)
# Of this computer only, or kept for the program's own use: no copy carries them.
BACKUP_LEFT_OUT = (
    WINDOW_PLACEMENT, SHORTCUT_CONFLICTS_TOLD, SETTING_COUNTRIES, SPEECH_LEVEL_ASKED, SETTING_ACCOUNTS,
    SETTING_CURRENT_ACCOUNT, INSTALL_STAMP,
)

def installed_language():
    """(language, stamp) the installer left beside the program: the language it was run in, and what
    tells this install from the one before. (None, None) if there is none; a stamp of None from an
    installer that wrote none."""
    folder = os.path.dirname(sys.executable) if IS_FROZEN else BASE_DIR
    try:
        with open(os.path.join(folder, INSTALL_LANGUAGE_FILE), READ_MODE, encoding=ENCODING_UTF8) as file:
            lines = file.read().split()
    except OSError:
        return None, None
    if not lines or lines[0] not in LANGUAGES:
        return None, None
    return lines[0], (lines[1] if len(lines) > 1 else None)


class Settings:
    """The app's own preferences, kept in a JSON file on this computer only."""

    def __init__(self):
        self.values = dict(DEFAULTS)
        for key, (allowed, default) in CHOICES.items():
            self.values[key] = default
        # Until a language is chosen in the settings, the one the program was installed in.
        self.values[SETTING_LANGUAGE] = installed_language()[0] or DEFAULT_LANG
        self.values.update(TEXTS)
        self.values[SETTING_SHORTCUTS] = {}
        self.values[SHORTCUT_CONFLICTS_TOLD] = []
        self.values[SETTING_FAVORITES] = []
        self.values[SETTING_COUNTRIES] = {}
        self.values[SETTING_POLL_DEFAULTS] = {"anonymous": True}
        self.values[SPEECH_LEVEL_ASKED] = False
        self.values[SETTING_ACCOUNTS] = []
        self.values[SETTING_CURRENT_ACCOUNT] = 0
        self.values[INSTALL_STAMP] = ""
        self.load()
        # With or without settings saved before: a new install has its say once.
        self.follow_installer()

    def load(self):
        if not os.path.exists(SETTINGS_FILE):
            return
        try:
            with open(SETTINGS_FILE, READ_MODE, encoding=ENCODING_UTF8) as file:
                stored = json.load(file)
        except (OSError, ValueError):
            # A damaged file should not stop the app from starting.
            return
        if not isinstance(stored, dict):
            return
        self.take(stored)
        if stored.get(SPEECH_LEVEL_ASKED) is True:
            self.values[SPEECH_LEVEL_ASKED] = True
        if isinstance(stored.get(INSTALL_STAMP), str):
            self.values[INSTALL_STAMP] = stored[INSTALL_STAMP]

    def follow_installer(self):
        """Installed again, or updated, in a language: the program now speaks it, whatever was chosen
        before. Each install counts once, so a language chosen in the settings afterwards stays."""
        language, stamp = installed_language()
        if language is None or stamp is None or stamp == self.values[INSTALL_STAMP]:
            return
        self.values[SETTING_LANGUAGE] = language
        self.values[INSTALL_STAMP] = stamp
        try:
            self.save()
        except OSError:
            pass

    def apply_level(self, level):
        """Tick what a level of experience says, and untick the rest of what it decides."""
        self.values[SETTING_SPEECH_LEVEL] = level
        for setting in LEVEL_OPTIONS:
            self.values[setting] = setting in LEVEL_SETTINGS[level]

    def export_to(self, path, with_secrets):
        """Write a copy of the settings to a file, without what belongs to this computer alone."""
        values = {key: value for key, value in self.values.items() if key not in BACKUP_LEFT_OUT}
        if not with_secrets:
            for key in BACKUP_SECRETS:
                values[key] = ""
        with open(path, "w", encoding=ENCODING_UTF8) as file:
            json.dump({"app": BACKUP_MARK, "settings": values}, file, ensure_ascii=False, indent=4)

    def import_from(self, path):
        """Take the settings of a copy made by export_to; False, changing nothing, if the file is no such copy.
        Secrets left out of the copy stay as they are here."""
        try:
            with open(path, READ_MODE, encoding=ENCODING_UTF8) as file:
                stored = json.load(file)
        except (OSError, ValueError):
            return False
        if not isinstance(stored, dict) or stored.get("app") != BACKUP_MARK or not isinstance(stored.get("settings"), dict):
            return False
        values = dict(stored["settings"])
        for key in BACKUP_SECRETS:
            if not values.get(key):
                values.pop(key, None)
        for key in BACKUP_LEFT_OUT:
            values.pop(key, None)
        self.take(values)
        return True

    def take(self, stored):
        """Keep, of what was read from a file, every value that is of the right kind for its setting."""
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
        favorites = stored.get(SETTING_FAVORITES)
        if isinstance(favorites, list) and all(isinstance(n, int) and not isinstance(n, bool) for n in favorites):
            self.values[SETTING_FAVORITES] = favorites
        countries = stored.get(SETTING_COUNTRIES)
        if isinstance(countries, dict) and isinstance(countries.get("countries"), list) and all(
            isinstance(country, dict) and isinstance(country.get("name"), str) and isinstance(country.get("code"), str)
            and isinstance(country.get("codes"), list) and all(isinstance(code, str) for code in country["codes"])
            for country in countries["countries"]
        ):
            self.values[SETTING_COUNTRIES] = countries
        accounts = stored.get(SETTING_ACCOUNTS)
        if isinstance(accounts, list) and all(
            isinstance(account, dict) and isinstance(account.get("id"), int)
            and isinstance(account.get("name"), str) and isinstance(account.get("phone"), str)
            for account in accounts
        ):
            self.values[SETTING_ACCOUNTS] = accounts
        current = stored.get(SETTING_CURRENT_ACCOUNT)
        if isinstance(current, int) and not isinstance(current, bool) and current >= 0:
            self.values[SETTING_CURRENT_ACCOUNT] = current
        polls = stored.get(SETTING_POLL_DEFAULTS)
        if isinstance(polls, dict) and all(
            (key in POLL_DEFAULT_FLAGS and isinstance(value, bool))
            or (key == "close_after" and isinstance(value, int) and not isinstance(value, bool))
            for key, value in polls.items()
        ):
            self.values[SETTING_POLL_DEFAULTS] = polls
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
