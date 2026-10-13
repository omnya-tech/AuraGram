import os
import shutil
import tempfile
import wx
from core import audio, key_conflicts, shortcuts, sounds
from core.settings import (
    SETTING_THEME, SETTING_LARGE_TEXT, SETTING_KEEP_IN_BACKGROUND, SETTING_SENT_SOUND, SETTING_PLAY_SOUND, SETTING_ANNOUNCE_MESSAGES,
    SETTING_MARK_READ_ON_OPEN, SETTING_START_SOUND, SETTING_ANNOUNCE_INTERRUPT,
    SETTING_BRAILLE_MESSAGES, SETTING_SPEAK_FEEDBACK, SETTING_ANNOUNCE_CONNECTION, SETTING_SIMPLE_TAB,
    SETTING_SHOW_PREVIEW, SETTING_ANNOUNCE_WHEN, SETTING_ANNOUNCE_WHAT, SETTING_ANNOUNCE_TYPING,
    SETTING_VOICE_SPEED, SETTING_MIC_DEVICE, SETTING_MIC_LEVEL, SETTING_NOISE, SETTING_LANGUAGE, CHOICES,
    SETTING_CHECK_UPDATES, SETTING_GEMINI_KEY, SETTING_CHAT_KIND, SETTING_MESSAGE_STATS, SETTING_TIME_STYLE,
    SETTING_RECORD_SOUND, SETTING_ENTER_SENDS
)
from ui.layout import prepare_window
from ui.proxy_dialog import ProxyDialog
from ui.shortcut_dialog import ShortcutDialog
from core.constants import (
    SOUNDS_DIR, SETTINGS_THEME_LABEL_KEY, SETTINGS_LARGE_TEXT_KEY, SETTINGS_KEEP_IN_BACKGROUND_KEY, SETTINGS_SENT_SOUND_KEY, SETTINGS_TITLE_KEY, SETTINGS_TAB_APP_KEY, SETTINGS_TAB_ACCOUNT_KEY,
    SETTINGS_APP_NOTE_KEY, SETTINGS_ACCOUNT_NOTE_KEY, SETTINGS_PLAY_SOUND_KEY,
    SETTINGS_ANNOUNCE_KEY, SETTINGS_MARK_READ_KEY,
    PROFILE_FIRST_NAME_KEY, PROFILE_LAST_NAME_KEY, PROFILE_ABOUT_KEY,
    MSG_LOADING_KEY, ERR_PROFILE_LOAD_KEY, APP_TITLE_KEY, DATE_TIME_FORMAT,
    PRIVACY_LEVELS, PRIVACY_CUSTOM_KEY, PRIVACY_LABEL_KEY_PREFIX, SETTINGS_TAB_PRIVACY_KEY,
    SETTINGS_TAB_SESSIONS_KEY, SETTINGS_PRIVACY_NOTE_KEY, SESSIONS_LABEL_KEY, SESSION_FORMAT_KEY,
    SESSION_CURRENT_FORMAT_KEY, BTN_END_SESSION_KEY, MSG_CONFIRM_END_SESSION_KEY,
    MSG_SESSION_ENDED_KEY, MSG_CANNOT_END_CURRENT_KEY,
    SOUND_NAMES, SOUND_FILE_PATTERNS, WAV_FILE_PATTERN, SETTINGS_TAB_SOUNDS_KEY, SOUNDS_NOTE_KEY,
    SOUNDS_WAV_NOTE_KEY, SOUNDS_LABEL_KEY, SOUND_LABEL_KEY_PREFIX, SOUND_ROW_FORMAT_KEY,
    SOUND_SOURCE_DEFAULT_KEY, SOUND_SOURCE_CUSTOM_KEY, BTN_CHOOSE_SOUND_KEY, BTN_TEST_SOUND_KEY,
    BTN_DEFAULT_SOUND_KEY, MSG_CHOOSE_SOUND_FILE_KEY, SOUND_FILES_KEY, MSG_SOUND_CHOSEN_FORMAT_KEY,
    MSG_SOUND_DEFAULT_KEY, ERR_SOUND_FILE_KEY, SETTINGS_START_SOUND_KEY, SETTINGS_TAB_ACCESSIBILITY_KEY,
    ACCESS_GROUP_READER_KEY, ACCESS_GROUP_KEYBOARD_KEY, ACCESS_GROUP_VISION_KEY,
    SETTINGS_ANNOUNCE_WHEN_LABEL_KEY, SETTINGS_ANNOUNCE_WHAT_LABEL_KEY, SETTINGS_ANNOUNCE_INTERRUPT_KEY,
    SETTINGS_BRAILLE_KEY, SETTINGS_SPEAK_FEEDBACK_KEY, SETTINGS_ANNOUNCE_CONNECTION_KEY,
    SETTINGS_SIMPLE_TAB_KEY, SETTINGS_SHOW_PREVIEW_KEY, SETTINGS_ANNOUNCE_TYPING_KEY,
    PROFILE_USERNAME_KEY, BTN_SET_PHOTO_KEY, BTN_DELETE_PHOTO_KEY, MSG_CHOOSE_PHOTO_KEY, PHOTO_FILES_KEY,
    PHOTO_FILE_PATTERNS, MSG_PHOTO_SET_KEY, MSG_PHOTO_DELETED_KEY, MSG_NO_PHOTO_KEY, MSG_CONFIRM_DELETE_PHOTO_KEY,
    BTN_TWO_STEP_KEY, MSG_TWO_STEP_OFF_KEY, MSG_TWO_STEP_ON_KEY, TWO_STEP_CHANGE_KEY, TWO_STEP_DISABLE_KEY,
    MSG_TWO_STEP_CURRENT_KEY, MSG_TWO_STEP_NEW_KEY, MSG_TWO_STEP_REPEAT_KEY, MSG_TWO_STEP_HINT_KEY,
    ERR_TWO_STEP_MISMATCH_KEY, MSG_CONFIRM_TWO_STEP_DISABLE_KEY, MSG_TWO_STEP_SAVED_KEY,
    MSG_TWO_STEP_DISABLED_KEY, NOTIFY_SCOPES, NOTIFY_LABEL_KEY_PREFIX, NOTIFY_GROUP_KEY,
    MSG_TWO_STEP_EMAIL_KEY, MSG_TWO_STEP_EMAIL_CODE_KEY, BTN_CHANGE_PHONE_KEY, MSG_NEW_PHONE_PROMPT_KEY,
    MSG_NEW_PHONE_CODE_KEY, MSG_PHONE_CHANGED_KEY, BTN_DELETE_ACCOUNT_KEY, MSG_CONFIRM_DELETE_ACCOUNT_KEY,
    MSG_DELETE_ACCOUNT_WORD_KEY, DELETE_ACCOUNT_WORD_KEY, MSG_DELETE_ACCOUNT_CANCELLED_KEY,
    MSG_ACCOUNT_DELETED_KEY, SETTINGS_VOICE_SPEED_LABEL_KEY, SETTINGS_TAB_MICROPHONE_KEY, MIC_NOTE_KEY,
    MIC_DEVICE_LABEL_KEY, MIC_DEVICE_DEFAULT_KEY, MIC_LEVEL_LABEL_KEY, MIC_NOISE_LABEL_KEY, BTN_TEST_MIC_KEY,
    MSG_MIC_TEST_SPEAK_KEY, MSG_MIC_TEST_PLAYING_KEY, MSG_MIC_TEST_SILENT_KEY, MIC_LEVELS, NOISE_LEVELS,
    MIC_TEST_MS, ERR_AUDIO_KEY, ERR_NO_AUDIO_SUPPORT_KEY, LANGUAGES, LANGUAGE_NAMES, SETTINGS_LANGUAGE_LABEL_KEY,
    SETTINGS_CHECK_UPDATES_KEY, SETTINGS_TAB_SERVICES_KEY, BTN_PROXY_KEY, MSG_PROXY_SAVED_KEY,
    SETTINGS_GEMINI_KEY_LABEL_KEY, SETTINGS_GEMINI_NOTE_KEY, SETTINGS_CHAT_KIND_LABEL_KEY,
    SETTINGS_MESSAGE_STATS_LABEL_KEY, SETTINGS_TIME_STYLE_LABEL_KEY, SETTINGS_RECORD_SOUND_KEY,
    SETTINGS_ENTER_SENDS_KEY, SETTINGS_TAB_SHORTCUTS_KEY, SHORTCUTS_NOTE_KEY, SHORTCUTS_LIST_LABEL_KEY,
    SHORTCUT_ROW_FORMAT_KEY, SHORTCUT_ROW_CONFLICT_FORMAT_KEY, SHORTCUT_NONE_KEY, BTN_SHORTCUT_CHANGE_KEY,
    BTN_SHORTCUT_REMOVE_KEY, BTN_SHORTCUT_DEFAULT_KEY, BTN_SHORTCUTS_DEFAULTS_KEY, BTN_SHORTCUTS_CHECK_KEY,
    MSG_SHORTCUT_USED_FORMAT_KEY, MSG_SHORTCUT_CONFLICT_FORMAT_KEY, MSG_CONFIRM_SHORTCUTS_DEFAULTS_KEY,
    MSG_SHORTCUTS_DEFAULTS_KEY, MSG_SHORTCUTS_NO_CONFLICTS_KEY, MSG_SHORTCUTS_CONFLICTS_FORMAT_KEY
)
from core.speech import speak

# Order of the privacy settings on their tab; each has a "PRIVACY_LABEL_<name>" string.
PRIVACY_NAMES = ("last_seen", "phone", "photo", "invites", "calls", "forwards")

APP_OPTIONS = (
    (SETTING_KEEP_IN_BACKGROUND, SETTINGS_KEEP_IN_BACKGROUND_KEY),
    (SETTING_MARK_READ_ON_OPEN, SETTINGS_MARK_READ_KEY),
    (SETTING_CHECK_UPDATES, SETTINGS_CHECK_UPDATES_KEY),
)
# What the screen reader is told, beyond what it reads by itself as the user moves around.
READER_OPTIONS = (
    (SETTING_ANNOUNCE_INTERRUPT, SETTINGS_ANNOUNCE_INTERRUPT_KEY),
    (SETTING_BRAILLE_MESSAGES, SETTINGS_BRAILLE_KEY),
    (SETTING_ANNOUNCE_TYPING, SETTINGS_ANNOUNCE_TYPING_KEY),
    (SETTING_SPEAK_FEEDBACK, SETTINGS_SPEAK_FEEDBACK_KEY),
    (SETTING_ANNOUNCE_CONNECTION, SETTINGS_ANNOUNCE_CONNECTION_KEY),
)
VISION_OPTIONS = (
    (SETTING_LARGE_TEXT, SETTINGS_LARGE_TEXT_KEY),
    (SETTING_SHOW_PREVIEW, SETTINGS_SHOW_PREVIEW_KEY),
)
SOUND_OPTIONS = (
    (SETTING_PLAY_SOUND, SETTINGS_PLAY_SOUND_KEY),
    (SETTING_SENT_SOUND, SETTINGS_SENT_SOUND_KEY),
    (SETTING_START_SOUND, SETTINGS_START_SOUND_KEY),
    (SETTING_RECORD_SOUND, SETTINGS_RECORD_SOUND_KEY),
)
PROFILE_FIELDS = (
    ("first_name", PROFILE_FIRST_NAME_KEY),
    ("last_name", PROFILE_LAST_NAME_KEY),
    ("about", PROFILE_ABOUT_KEY),
    ("username", PROFILE_USERNAME_KEY),
)

class SettingsDialog(wx.Dialog):
    """Two tabs kept apart on purpose: app preferences stay on this computer,
    account settings change the Telegram account everywhere."""

    def __init__(self, parent, i18n, settings, telegram_manager):
        super().__init__(parent, title=i18n.get_string(SETTINGS_TITLE_KEY), size=(720, 710))
        prepare_window(self, i18n)
        self.i18n = i18n
        self.settings = settings
        self.telegram_manager = telegram_manager
        self.profile = None
        self.privacy = None
        self.notify_settings = None
        self.notify_boxes = {}
        self.mic_tester = audio.Recorder()
        # Set once the account is gone: whoever opened the dialog has to close the app.
        self.account_deleted = False
        # Set when the chosen language differs from the one running now.
        self.language_changed = False
        self.sessions = []
        self.checkboxes = {}
        self.choices = {}
        self.profile_inputs = {}
        self.privacy_choices = {}
        # Tones changed in this dialog, not yet saved: the converted file to use, or None for the bundled tone.
        self.sound_changes = {}
        self.sound_drafts_dir = None
        # {command: shortcut} as it stands in this dialog, saved with the rest on OK.
        self.shortcut_table = shortcuts.current(settings)
        # {shortcut: who else holds it}, as last looked for on this computer.
        self.shortcut_conflicts = key_conflicts.find(self.shortcut_table.values())

        notebook = self.notebook = wx.Notebook(self)
        notebook.AddPage(self.create_app_page(notebook), i18n.get_string(SETTINGS_TAB_APP_KEY))
        notebook.AddPage(self.create_accessibility_page(notebook), i18n.get_string(SETTINGS_TAB_ACCESSIBILITY_KEY))
        notebook.AddPage(self.create_shortcuts_page(notebook), i18n.get_string(SETTINGS_TAB_SHORTCUTS_KEY))
        notebook.AddPage(self.create_sounds_page(notebook), i18n.get_string(SETTINGS_TAB_SOUNDS_KEY))
        notebook.AddPage(self.create_microphone_page(notebook), i18n.get_string(SETTINGS_TAB_MICROPHONE_KEY))
        notebook.AddPage(self.create_services_page(notebook), i18n.get_string(SETTINGS_TAB_SERVICES_KEY))
        notebook.AddPage(self.create_account_page(notebook), i18n.get_string(SETTINGS_TAB_ACCOUNT_KEY))
        notebook.AddPage(self.create_privacy_page(notebook), i18n.get_string(SETTINGS_TAB_PRIVACY_KEY))
        notebook.AddPage(self.create_sessions_page(notebook), i18n.get_string(SETTINGS_TAB_SESSIONS_KEY))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(notebook, proportion=1, flag=wx.EXPAND|wx.ALL, border=10)
        sizer.Add(self.CreateButtonSizer(wx.OK|wx.CANCEL), flag=wx.EXPAND|wx.ALL, border=10)
        self.SetSizer(sizer)
        self.CenterOnParent()
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)

        telegram_manager.load_profile(
            lambda profile, error_key: wx.CallAfter(self.on_profile_loaded, profile, error_key)
        )
        telegram_manager.load_privacy(
            lambda privacy, error_key: wx.CallAfter(self.on_privacy_loaded, privacy, error_key)
        )
        telegram_manager.load_notify(
            lambda enabled, error_key: wx.CallAfter(self.on_notify_loaded, enabled, error_key)
        )
        self.load_sessions()

    def create_app_page(self, notebook):
        page = wx.Panel(notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(page, label=self.i18n.get_string(SETTINGS_APP_NOTE_KEY)), flag=wx.ALL, border=10)
        self.add_checkboxes(page, sizer, APP_OPTIONS)
        # What the rows of the two lists say, and in what order: a screen reader reads a row from its start.
        self.add_choice(page, sizer, SETTINGS_CHAT_KIND_LABEL_KEY, SETTING_CHAT_KIND)
        self.add_choice(page, sizer, SETTINGS_MESSAGE_STATS_LABEL_KEY, SETTING_MESSAGE_STATS)
        self.add_choice(page, sizer, SETTINGS_TIME_STYLE_LABEL_KEY, SETTING_TIME_STYLE)
        # The interface language. Each one is named in its own script; takes effect after a restart.
        sizer.Add(wx.StaticText(page, label=self.i18n.get_string(SETTINGS_LANGUAGE_LABEL_KEY)), flag=wx.LEFT|wx.RIGHT, border=10)
        self.language_choice = wx.Choice(page, choices=[LANGUAGE_NAMES[code] for code in LANGUAGES])
        self.language_choice.SetSelection(LANGUAGES.index(self.settings.get(SETTING_LANGUAGE)))
        sizer.Add(self.language_choice, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        page.SetSizer(sizer)
        return page

    def add_checkboxes(self, parent, sizer, options):
        for setting, label_key in options:
            checkbox = wx.CheckBox(parent, label=self.i18n.get_string(label_key))
            checkbox.SetValue(self.settings.get(setting))
            sizer.Add(checkbox, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
            self.checkboxes[setting] = checkbox

    def add_choice(self, parent, sizer, label_key, setting):
        """A labelled drop-down for one of the CHOICES settings."""
        options = CHOICES[setting][0]
        sizer.Add(wx.StaticText(parent, label=self.i18n.get_string(label_key)), flag=wx.LEFT|wx.RIGHT, border=10)
        choice = wx.Choice(parent, choices=[self.i18n.get_string(option) for option in options])
        choice.SetSelection(options.index(self.settings.get(setting)))
        sizer.Add(choice, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        self.choices[setting] = choice
        return choice

    def add_group(self, page, sizer, label_key):
        """A titled box: a screen reader names it when focus enters one of its controls."""
        group = wx.StaticBoxSizer(wx.VERTICAL, page, self.i18n.get_string(label_key))
        sizer.Add(group, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        group.AddSpacer(5)
        return group.GetStaticBox(), group

    def create_accessibility_page(self, notebook):
        page = wx.Panel(notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(page, label=self.i18n.get_string(SETTINGS_APP_NOTE_KEY)), flag=wx.ALL, border=10)

        box, group = self.add_group(page, sizer, ACCESS_GROUP_READER_KEY)
        self.add_checkboxes(box, group, ((SETTING_ANNOUNCE_MESSAGES, SETTINGS_ANNOUNCE_KEY),))
        self.add_choice(box, group, SETTINGS_ANNOUNCE_WHEN_LABEL_KEY, SETTING_ANNOUNCE_WHEN)
        self.add_choice(box, group, SETTINGS_ANNOUNCE_WHAT_LABEL_KEY, SETTING_ANNOUNCE_WHAT)
        self.add_checkboxes(box, group, READER_OPTIONS)

        box, group = self.add_group(page, sizer, ACCESS_GROUP_KEYBOARD_KEY)
        self.add_checkboxes(box, group, (
            (SETTING_SIMPLE_TAB, SETTINGS_SIMPLE_TAB_KEY), (SETTING_ENTER_SENDS, SETTINGS_ENTER_SENDS_KEY),
        ))

        box, group = self.add_group(page, sizer, ACCESS_GROUP_VISION_KEY)
        self.add_checkboxes(box, group, VISION_OPTIONS)
        self.theme_choice = self.add_choice(box, group, SETTINGS_THEME_LABEL_KEY, SETTING_THEME)
        page.SetSizer(sizer)
        return page

    def create_shortcuts_page(self, notebook):
        """Every command with its shortcut, as one list to walk with the arrows."""
        page = self.shortcuts_page = wx.Panel(notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        note = wx.StaticText(page, label=self.i18n.get_string(SHORTCUTS_NOTE_KEY))
        note.Wrap(660)
        sizer.Add(note, flag=wx.ALL, border=10)
        sizer.Add(wx.StaticText(page, label=self.i18n.get_string(SHORTCUTS_LIST_LABEL_KEY)), flag=wx.LEFT|wx.RIGHT, border=10)
        self.shortcuts_list = wx.ListBox(page, style=wx.LB_SINGLE)
        self.shortcuts_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_change_shortcut)
        sizer.Add(self.shortcuts_list, proportion=1, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        for label_key, handler in (
            (BTN_SHORTCUT_CHANGE_KEY, self.on_change_shortcut),
            (BTN_SHORTCUT_REMOVE_KEY, self.on_remove_shortcut),
            (BTN_SHORTCUT_DEFAULT_KEY, self.on_default_shortcut),
            (BTN_SHORTCUTS_DEFAULTS_KEY, self.on_default_shortcuts),
            (BTN_SHORTCUTS_CHECK_KEY, self.on_check_shortcuts),
        ):
            button = wx.Button(page, label=self.i18n.get_string(label_key))
            button.Bind(wx.EVT_BUTTON, handler)
            sizer.Add(button, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        page.SetSizer(sizer)
        self.show_shortcuts(0)
        return page

    def show_shortcuts_page(self):
        """Open on the shortcuts, for whoever came to change one."""
        self.notebook.SetSelection(self.notebook.FindPage(self.shortcuts_page))
        self.shortcuts_list.SetFocus()

    def shortcut_row(self, command):
        text = self.shortcut_table[command]
        row = self.i18n.get_string(SHORTCUT_ROW_FORMAT_KEY).format(
            command=shortcuts.label(self.i18n, command), shortcut=text or self.i18n.get_string(SHORTCUT_NONE_KEY)
        )
        if text in self.shortcut_conflicts:
            row = self.i18n.get_string(SHORTCUT_ROW_CONFLICT_FORMAT_KEY).format(
                row=row, holder=shortcuts.holder_text(self.i18n, self.shortcut_conflicts[text])
            )
        return row

    def show_shortcuts(self, selection):
        self.shortcuts_list.Set([self.shortcut_row(command) for command in shortcuts.COMMANDS])
        self.shortcuts_list.SetSelection(selection)

    def selected_command(self):
        return shortcuts.COMMANDS[max(self.shortcuts_list.GetSelection(), 0)]

    def ask(self, text):
        """A yes or no question where yes is the usual answer."""
        answer = wx.MessageBox(text, self.i18n.get_string(APP_TITLE_KEY), wx.YES_NO | wx.ICON_QUESTION, self)
        return answer == wx.YES

    def ask_shortcut(self, command):
        """The shortcut the user presses for a command; None if they back out."""
        with ShortcutDialog(self, self.i18n, shortcuts.label(self.i18n, command), command) as shortcut_dialog:
            if shortcut_dialog.ShowModal() != wx.ID_OK:
                return None
            return shortcut_dialog.shortcut

    def on_change_shortcut(self, event):
        command = self.selected_command()
        while True:
            text = self.ask_shortcut(command)
            if text is None:
                return
            if not self.may_take(command, text):
                return
            holder = key_conflicts.find([text]).get(text)
            if holder is None:
                self.shortcut_conflicts.pop(text, None)
                break
            # Something else on this computer answers to it: the user is told, and asked for another.
            self.shortcut_conflicts[text] = holder
            if not self.ask(self.i18n.get_string(MSG_SHORTCUT_CONFLICT_FORMAT_KEY).format(
                shortcut=text, holder=shortcuts.holder_text(self.i18n, holder)
            )):
                break
        self.set_shortcut(command, text)

    def may_take(self, command, text):
        """Whether a shortcut is free for a command, or the user agrees to take it from the command that has it."""
        other = shortcuts.owner(self.shortcut_table, text, command)
        return other is None or self.ask(self.i18n.get_string(MSG_SHORTCUT_USED_FORMAT_KEY).format(
            shortcut=text, command=shortcuts.label(self.i18n, other)
        ))

    def set_shortcut(self, command, text):
        """Give a command its shortcut in the dialog; whichever command had it is left without one."""
        other = shortcuts.owner(self.shortcut_table, text, command)
        if other is not None:
            self.shortcut_table[other] = ""
        self.shortcut_table[command] = text
        self.show_shortcuts(shortcuts.COMMANDS.index(command))
        speak(self.shortcut_row(command))

    def on_remove_shortcut(self, event):
        self.set_shortcut(self.selected_command(), "")

    def on_default_shortcut(self, event):
        command = self.selected_command()
        text = shortcuts.defaults()[command]
        if self.may_take(command, text):
            self.set_shortcut(command, text)

    def on_default_shortcuts(self, event):
        if self.confirm(MSG_CONFIRM_SHORTCUTS_DEFAULTS_KEY):
            self.shortcut_table = shortcuts.defaults()
            self.show_shortcuts(self.shortcuts_list.GetSelection())
            speak(self.i18n.get_string(MSG_SHORTCUTS_DEFAULTS_KEY))

    def on_check_shortcuts(self, event):
        """Look again at what other programs on this computer hold, and say what was found."""
        self.shortcut_conflicts = key_conflicts.find(self.shortcut_table.values())
        self.show_shortcuts(self.shortcuts_list.GetSelection())
        if not self.shortcut_conflicts:
            self.show_message(self.i18n.get_string(MSG_SHORTCUTS_NO_CONFLICTS_KEY))
            return
        lines = shortcuts.conflict_lines(self.i18n, self.shortcut_table, self.shortcut_conflicts)
        self.show_message(self.i18n.get_string(MSG_SHORTCUTS_CONFLICTS_FORMAT_KEY).format(
            count=len(lines.splitlines()), conflicts=lines
        ), wx.ICON_WARNING)

    def on_char_hook(self, event):
        # On a command of the shortcuts list, Enter changes its shortcut rather than closing the dialog.
        on_list = wx.Window.FindFocus() is self.shortcuts_list and not event.HasAnyModifiers()
        if on_list and event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.on_change_shortcut(event)
        elif on_list and event.GetKeyCode() == wx.WXK_DELETE:
            self.on_remove_shortcut(event)
        else:
            event.Skip()

    def create_sounds_page(self, notebook):
        page = wx.Panel(notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        note = wx.StaticText(page, label=self.i18n.get_string(SOUNDS_NOTE_KEY if audio.AVAILABLE else SOUNDS_WAV_NOTE_KEY))
        note.Wrap(460)
        self.add_checkboxes(page, sizer, SOUND_OPTIONS)
        self.add_choice(page, sizer, SETTINGS_VOICE_SPEED_LABEL_KEY, SETTING_VOICE_SPEED)
        sizer.Add(note, flag=wx.ALL, border=10)
        sizer.Add(wx.StaticText(page, label=self.i18n.get_string(SOUNDS_LABEL_KEY)), flag=wx.LEFT|wx.RIGHT, border=10)
        self.sounds_list = wx.ListBox(page, style=wx.LB_SINGLE)
        sizer.Add(self.sounds_list, proportion=1, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        for label_key, handler in (
            (BTN_CHOOSE_SOUND_KEY, self.on_choose_sound),
            (BTN_TEST_SOUND_KEY, self.on_test_sound),
            (BTN_DEFAULT_SOUND_KEY, self.on_default_sound),
        ):
            button = wx.Button(page, label=self.i18n.get_string(label_key))
            button.Bind(wx.EVT_BUTTON, handler)
            sizer.Add(button, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        page.SetSizer(sizer)
        self.show_sounds(0)
        return page

    def show_sounds(self, selection):
        rows = []
        for name in SOUND_NAMES:
            is_custom = self.sound_changes[name] is not None if name in self.sound_changes else sounds.has_custom(name)
            rows.append(self.i18n.get_string(SOUND_ROW_FORMAT_KEY).format(
                sound=self.i18n.get_string(SOUND_LABEL_KEY_PREFIX + name),
                source=self.i18n.get_string(SOUND_SOURCE_CUSTOM_KEY if is_custom else SOUND_SOURCE_DEFAULT_KEY)
            ))
        self.sounds_list.Set(rows)
        self.sounds_list.SetSelection(selection)

    def selected_sound(self):
        return SOUND_NAMES[max(self.sounds_list.GetSelection(), 0)]

    def on_choose_sound(self, event):
        patterns = SOUND_FILE_PATTERNS if audio.AVAILABLE else WAV_FILE_PATTERN
        with wx.FileDialog(
            self, self.i18n.get_string(MSG_CHOOSE_SOUND_FILE_KEY),
            wildcard="%s (%s)|%s" % (self.i18n.get_string(SOUND_FILES_KEY), patterns, patterns),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_OK:
                return
            path = file_dialog.GetPath()
        self.use_sound_file(self.selected_sound(), path)

    def use_sound_file(self, name, path):
        """Take the user's file for a tone; it replaces the old one only when the settings are saved."""
        if self.sound_drafts_dir is None:
            self.sound_drafts_dir = tempfile.mkdtemp()
        draft = os.path.join(self.sound_drafts_dir, name + ".wav")
        if not sounds.convert(path, draft):
            wx.MessageBox(
                self.i18n.get_string(ERR_SOUND_FILE_KEY), self.i18n.get_string(APP_TITLE_KEY),
                wx.OK | wx.ICON_ERROR, self
            )
            return
        self.sound_changes[name] = draft
        self.show_sounds(SOUND_NAMES.index(name))
        speak(self.i18n.get_string(MSG_SOUND_CHOSEN_FORMAT_KEY).format(file=os.path.basename(path)))
        sounds.play_file(draft)

    def on_test_sound(self, event):
        name = self.selected_sound()
        if self.sound_changes.get(name) is not None:
            sounds.play_file(self.sound_changes[name])
        elif name in self.sound_changes:
            # Going back to the bundled tone, though the user's file is still in place until saving.
            sounds.play_file(os.path.join(SOUNDS_DIR, name + ".wav"))
        else:
            sounds.play(name)

    def on_default_sound(self, event):
        name = self.selected_sound()
        self.sound_changes[name] = None
        self.show_sounds(SOUND_NAMES.index(name))
        speak(self.i18n.get_string(MSG_SOUND_DEFAULT_KEY))

    def Destroy(self):
        if self.sound_drafts_dir is not None:
            shutil.rmtree(self.sound_drafts_dir, ignore_errors=True)
        # A microphone test may be half way through.
        self.mic_tester.cancel()
        return super().Destroy()

    def create_microphone_page(self, notebook):
        page = wx.Panel(notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        note = wx.StaticText(page, label=self.i18n.get_string(MIC_NOTE_KEY))
        note.Wrap(460)
        sizer.Add(note, flag=wx.ALL, border=10)
        sizer.Add(wx.StaticText(page, label=self.i18n.get_string(MIC_DEVICE_LABEL_KEY)), flag=wx.LEFT|wx.RIGHT, border=10)
        # The first entry follows whatever Windows uses; the rest name one microphone each.
        self.mic_names = [""] + (audio.input_devices() if audio.AVAILABLE else [])
        saved = self.settings.get(SETTING_MIC_DEVICE)
        self.mic_choice = wx.Choice(
            page, choices=[self.i18n.get_string(MIC_DEVICE_DEFAULT_KEY)] + self.mic_names[1:]
        )
        # One that has been unplugged since falls back to the default.
        self.mic_choice.SetSelection(self.mic_names.index(saved) if saved in self.mic_names else 0)
        sizer.Add(self.mic_choice, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        self.add_choice(page, sizer, MIC_LEVEL_LABEL_KEY, SETTING_MIC_LEVEL)
        self.add_choice(page, sizer, MIC_NOISE_LABEL_KEY, SETTING_NOISE)
        self.mic_test_btn = wx.Button(page, label=self.i18n.get_string(BTN_TEST_MIC_KEY))
        self.mic_test_btn.Bind(wx.EVT_BUTTON, self.on_test_mic)
        sizer.Add(self.mic_test_btn, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        page.SetSizer(sizer)
        return page

    def create_services_page(self, notebook):
        """What the app reaches over the internet besides the account itself: the way to Telegram, and Gemini."""
        page = wx.Panel(notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        # Acts at once, from its own window: not part of what OK saves.
        proxy_btn = wx.Button(page, label=self.i18n.get_string(BTN_PROXY_KEY))
        proxy_btn.Bind(wx.EVT_BUTTON, self.on_proxy)
        sizer.Add(proxy_btn, flag=wx.ALL, border=10)
        sizer.Add(wx.StaticText(page, label=self.i18n.get_string(SETTINGS_GEMINI_KEY_LABEL_KEY)), flag=wx.LEFT|wx.RIGHT, border=10)
        self.gemini_key_input = wx.TextCtrl(page, value=self.settings.get(SETTING_GEMINI_KEY))
        sizer.Add(self.gemini_key_input, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        # A read-only field rather than a label, so a screen reader can go through it.
        note = wx.TextCtrl(
            page, value=self.i18n.get_string(SETTINGS_GEMINI_NOTE_KEY),
            style=wx.TE_MULTILINE|wx.TE_READONLY, size=(-1, 110)
        )
        sizer.Add(note, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        page.SetSizer(sizer)
        return page

    def on_proxy(self, event):
        with ProxyDialog(self, self.i18n, self.settings, self.telegram_manager) as proxy_dialog:
            if proxy_dialog.ShowModal() == wx.ID_OK:
                speak(self.i18n.get_string(MSG_PROXY_SAVED_KEY))

    def chosen(self, setting):
        """What a drop-down of the dialog is set to now, saved or not."""
        return CHOICES[setting][0][self.choices[setting].GetSelection()]

    def on_test_mic(self, event):
        """Record a few seconds with the settings as they stand in the dialog, then play them back."""
        if not audio.AVAILABLE:
            self.show_message(self.i18n.get_string(ERR_NO_AUDIO_SUPPORT_KEY), wx.ICON_ERROR)
            return
        tester = self.mic_tester
        tester.device = audio.find_input(self.mic_names[self.mic_choice.GetSelection()])
        tester.level = MIC_LEVELS[self.chosen(SETTING_MIC_LEVEL)]
        tester.reduction_db = NOISE_LEVELS[self.chosen(SETTING_NOISE)]
        try:
            tester.start()
        except Exception:
            tester.cancel()
            self.show_message(self.i18n.get_string(ERR_AUDIO_KEY), wx.ICON_ERROR)
            return
        self.mic_test_btn.Disable()
        speak(self.i18n.get_string(MSG_MIC_TEST_SPEAK_KEY))
        wx.CallLater(MIC_TEST_MS, self.finish_mic_test)

    def finish_mic_test(self):
        if not self:
            return
        self.mic_test_btn.Enable()
        samples = self.mic_tester.take()
        if not len(samples) or not samples.any():
            self.show_message(self.i18n.get_string(MSG_MIC_TEST_SILENT_KEY), wx.ICON_ERROR)
            return
        speak(self.i18n.get_string(MSG_MIC_TEST_PLAYING_KEY))
        audio.play_samples(samples)

    def create_account_page(self, notebook):
        page = wx.Panel(notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.account_note = wx.StaticText(page, label=self.i18n.get_string(MSG_LOADING_KEY))
        sizer.Add(self.account_note, flag=wx.ALL, border=10)
        for field, label_key in PROFILE_FIELDS:
            sizer.Add(wx.StaticText(page, label=self.i18n.get_string(label_key)), flag=wx.LEFT|wx.RIGHT, border=10)
            text_input = wx.TextCtrl(page)
            # Nothing to edit until the current values arrive from Telegram.
            text_input.Disable()
            sizer.Add(text_input, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
            self.profile_inputs[field] = text_input
        # These act at once, each after its own question: they are not part of what OK saves.
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        for label_key, handler in (
            (BTN_SET_PHOTO_KEY, self.on_set_photo),
            (BTN_DELETE_PHOTO_KEY, self.on_delete_photo),
            (BTN_TWO_STEP_KEY, self.on_two_step),
        ):
            button = wx.Button(page, label=self.i18n.get_string(label_key))
            button.Bind(wx.EVT_BUTTON, handler)
            buttons.Add(button, flag=wx.RIGHT, border=10)
        sizer.Add(buttons, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        for label_key, handler in (
            (BTN_CHANGE_PHONE_KEY, self.on_change_phone),
            (BTN_DELETE_ACCOUNT_KEY, self.on_delete_account),
        ):
            button = wx.Button(page, label=self.i18n.get_string(label_key))
            button.Bind(wx.EVT_BUTTON, handler)
            buttons.Add(button, flag=wx.RIGHT, border=10)
        sizer.Add(buttons, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        box, group = self.add_group(page, sizer, NOTIFY_GROUP_KEY)
        for kind in NOTIFY_SCOPES:
            checkbox = wx.CheckBox(box, label=self.i18n.get_string(NOTIFY_LABEL_KEY_PREFIX + kind))
            # Unknown until Telegram answers.
            checkbox.Disable()
            group.Add(checkbox, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
            self.notify_boxes[kind] = checkbox
        page.SetSizer(sizer)
        return page

    def on_notify_loaded(self, enabled, error_key):
        if not self or error_key:
            return
        self.notify_settings = enabled
        for kind, checkbox in self.notify_boxes.items():
            checkbox.SetValue(enabled[kind])
            checkbox.Enable()

    def changed_notify(self):
        """Only the notification defaults the user actually changed, as {kind: enabled}."""
        if self.notify_settings is None:
            return {}
        return {
            kind: checkbox.GetValue() for kind, checkbox in self.notify_boxes.items()
            if checkbox.GetValue() != self.notify_settings[kind]
        }

    def on_account_result(self, handler):
        """Wrap a handler for an answer from Telegram: errors are shown here, the rest goes to the handler."""
        def deliver(result, error_key):
            wx.CallAfter(self.handle_account_result, handler, result, error_key)
        return deliver

    def handle_account_result(self, handler, result, error_key):
        if not self:
            return
        if error_key:
            self.show_message(self.i18n.get_string(error_key), wx.ICON_ERROR)
        else:
            handler(result)

    def show_message(self, text, icon=wx.ICON_INFORMATION):
        return wx.MessageBox(text, self.i18n.get_string(APP_TITLE_KEY), wx.OK | icon, self)

    def confirm(self, key):
        answer = wx.MessageBox(
            self.i18n.get_string(key), self.i18n.get_string(APP_TITLE_KEY),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self
        )
        return answer == wx.YES

    def on_set_photo(self, event):
        with wx.FileDialog(
            self, self.i18n.get_string(MSG_CHOOSE_PHOTO_KEY),
            wildcard="%s (%s)|%s" % (self.i18n.get_string(PHOTO_FILES_KEY), PHOTO_FILE_PATTERNS, PHOTO_FILE_PATTERNS),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_OK:
                return
            path = file_dialog.GetPath()
        self.set_photo(path)

    def set_photo(self, path):
        self.telegram_manager.set_profile_photo(
            path, self.on_account_result(lambda result: speak(self.i18n.get_string(MSG_PHOTO_SET_KEY)))
        )

    def on_delete_photo(self, event):
        if self.confirm(MSG_CONFIRM_DELETE_PHOTO_KEY):
            self.telegram_manager.delete_profile_photo(self.on_account_result(
                lambda deleted: speak(self.i18n.get_string(MSG_PHOTO_DELETED_KEY if deleted else MSG_NO_PHOTO_KEY))
            ))

    def on_two_step(self, event):
        self.telegram_manager.load_two_step_state(self.on_account_result(self.ask_two_step))

    def ask_password(self, prompt_key):
        """A password typed unseen; None if the user backs out or leaves it empty."""
        with wx.PasswordEntryDialog(
            self, self.i18n.get_string(prompt_key), self.i18n.get_string(APP_TITLE_KEY)
        ) as password_dialog:
            if password_dialog.ShowModal() != wx.ID_OK:
                return None
            return password_dialog.GetValue() or None

    def ask_two_step(self, is_on):
        current = None
        if is_on:
            with wx.SingleChoiceDialog(
                self, self.i18n.get_string(MSG_TWO_STEP_ON_KEY), self.i18n.get_string(APP_TITLE_KEY),
                [self.i18n.get_string(TWO_STEP_CHANGE_KEY), self.i18n.get_string(TWO_STEP_DISABLE_KEY)]
            ) as action_dialog:
                if action_dialog.ShowModal() != wx.ID_OK:
                    return
                disabling = action_dialog.GetSelection() == 1
            current = self.ask_password(MSG_TWO_STEP_CURRENT_KEY)
            if current is None:
                return
            if disabling:
                if self.confirm(MSG_CONFIRM_TWO_STEP_DISABLE_KEY):
                    self.telegram_manager.change_two_step(current, None, "", self.on_account_result(
                        lambda result: self.show_message(self.i18n.get_string(MSG_TWO_STEP_DISABLED_KEY))
                    ))
                return
        elif not self.confirm(MSG_TWO_STEP_OFF_KEY):
            return
        new = self.ask_password(MSG_TWO_STEP_NEW_KEY)
        if new is None:
            return
        # Typed blind, so typed twice: a slip here would lock the user out of their own account.
        if self.ask_password(MSG_TWO_STEP_REPEAT_KEY) != new:
            self.show_message(self.i18n.get_string(ERR_TWO_STEP_MISMATCH_KEY), wx.ICON_ERROR)
            return
        with wx.TextEntryDialog(
            self, self.i18n.get_string(MSG_TWO_STEP_HINT_KEY), self.i18n.get_string(APP_TITLE_KEY)
        ) as hint_dialog:
            if hint_dialog.ShowModal() != wx.ID_OK:
                return
            hint = hint_dialog.GetValue().strip()
        email = self.ask_line(MSG_TWO_STEP_EMAIL_KEY)
        if email is None:
            return
        self.telegram_manager.change_two_step(
            current, new, hint,
            self.on_account_result(lambda result: self.show_message(self.i18n.get_string(MSG_TWO_STEP_SAVED_KEY))),
            email=email, ask_code=lambda reply: wx.CallAfter(self.ask_email_code, reply)
        )

    def ask_line(self, prompt_key):
        """One line of text; None if the user backs out, "" if they leave it empty."""
        with wx.TextEntryDialog(
            self, self.i18n.get_string(prompt_key), self.i18n.get_string(APP_TITLE_KEY)
        ) as line_dialog:
            if line_dialog.ShowModal() != wx.ID_OK:
                return None
            return line_dialog.GetValue().strip()

    def ask_email_code(self, reply):
        # Answered either way: Telegram's side of this is waiting on it.
        reply(self.ask_line(MSG_TWO_STEP_EMAIL_CODE_KEY) if self else None)

    def on_change_phone(self, event):
        phone = self.ask_line(MSG_NEW_PHONE_PROMPT_KEY)
        if phone:
            self.telegram_manager.request_phone_change(phone, self.on_account_result(self.ask_phone_code))

    def ask_phone_code(self, result):
        code = self.ask_line(MSG_NEW_PHONE_CODE_KEY)
        if code:
            self.telegram_manager.confirm_phone_change(code, self.on_account_result(
                lambda result: self.show_message(self.i18n.get_string(MSG_PHONE_CHANGED_KEY))
            ))

    def on_delete_account(self, event):
        # Three steps on purpose: a question, a word to type, and the password where there is one.
        answer = wx.MessageBox(
            self.i18n.get_string(MSG_CONFIRM_DELETE_ACCOUNT_KEY), self.i18n.get_string(APP_TITLE_KEY),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self
        )
        if answer != wx.YES or self.ask_line(MSG_DELETE_ACCOUNT_WORD_KEY) != self.i18n.get_string(DELETE_ACCOUNT_WORD_KEY):
            speak(self.i18n.get_string(MSG_DELETE_ACCOUNT_CANCELLED_KEY))
            return
        self.telegram_manager.load_two_step_state(self.on_account_result(self.delete_account))

    def delete_account(self, has_password):
        password = None
        if has_password:
            password = self.ask_password(MSG_TWO_STEP_CURRENT_KEY)
            if password is None:
                speak(self.i18n.get_string(MSG_DELETE_ACCOUNT_CANCELLED_KEY))
                return
        self.telegram_manager.delete_account(password, self.on_account_result(self.on_account_deleted))

    def on_account_deleted(self, result):
        self.account_deleted = True
        self.show_message(self.i18n.get_string(MSG_ACCOUNT_DELETED_KEY))
        if self.IsModal():
            self.EndModal(wx.ID_CANCEL)

    def on_profile_loaded(self, profile, error_key):
        # The dialog may have been closed before Telegram answered.
        if not self:
            return
        if error_key:
            self.account_note.SetLabel(self.i18n.get_string(ERR_PROFILE_LOAD_KEY))
            return
        self.profile = profile
        self.account_note.SetLabel(self.i18n.get_string(SETTINGS_ACCOUNT_NOTE_KEY))
        for field, text_input in self.profile_inputs.items():
            text_input.SetValue(profile[field])
            text_input.Enable()

    def create_privacy_page(self, notebook):
        page = wx.Panel(notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.privacy_note = wx.StaticText(page, label=self.i18n.get_string(MSG_LOADING_KEY))
        sizer.Add(self.privacy_note, flag=wx.ALL, border=10)
        levels = [self.i18n.get_string(level) for level in PRIVACY_LEVELS]
        for name in PRIVACY_NAMES:
            label = wx.StaticText(page, label=self.i18n.get_string(PRIVACY_LABEL_KEY_PREFIX + name))
            sizer.Add(label, flag=wx.LEFT|wx.RIGHT, border=10)
            choice = wx.Choice(page, choices=levels)
            choice.Disable()
            sizer.Add(choice, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
            self.privacy_choices[name] = choice
        page.SetSizer(sizer)
        return page

    def on_privacy_loaded(self, privacy, error_key):
        if not self:
            return
        if error_key:
            self.privacy_note.SetLabel(self.i18n.get_string(ERR_PROFILE_LOAD_KEY))
            return
        self.privacy = privacy
        self.privacy_note.SetLabel(self.i18n.get_string(SETTINGS_PRIVACY_NOTE_KEY))
        self.privacy_note.Wrap(460)
        for name, choice in self.privacy_choices.items():
            level = privacy[name]
            if level is None:
                # Has per-person exceptions: shown but locked, so saving cannot wipe them.
                choice.Set([self.i18n.get_string(PRIVACY_CUSTOM_KEY)])
                choice.SetSelection(0)
            else:
                choice.SetSelection(PRIVACY_LEVELS.index(level))
                choice.Enable()

    def changed_privacy(self):
        """Only the privacy settings the user actually changed, as {name: level}."""
        if self.privacy is None:
            return {}
        changes = {}
        for name, choice in self.privacy_choices.items():
            if self.privacy[name] is None:
                continue
            level = PRIVACY_LEVELS[choice.GetSelection()]
            if level != self.privacy[name]:
                changes[name] = level
        return changes

    def create_sessions_page(self, notebook):
        page = wx.Panel(notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(page, label=self.i18n.get_string(SESSIONS_LABEL_KEY)), flag=wx.ALL, border=10)
        self.sessions_list = wx.ListBox(page, style=wx.LB_SINGLE)
        sizer.Add(self.sessions_list, proportion=1, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        self.end_session_btn = wx.Button(page, label=self.i18n.get_string(BTN_END_SESSION_KEY))
        self.end_session_btn.Bind(wx.EVT_BUTTON, self.on_end_session)
        sizer.Add(self.end_session_btn, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        page.SetSizer(sizer)
        return page

    def load_sessions(self):
        self.sessions = []
        self.sessions_list.Set([self.i18n.get_string(MSG_LOADING_KEY)])
        self.telegram_manager.load_sessions(
            lambda sessions, error_key: wx.CallAfter(self.on_sessions_loaded, sessions, error_key)
        )

    def on_sessions_loaded(self, sessions, error_key):
        if not self:
            return
        if error_key:
            self.sessions_list.Set([self.i18n.get_string(ERR_PROFILE_LOAD_KEY)])
            return
        # This device first, then the most recently used.
        self.sessions = sorted(sessions, key=lambda s: (not s["current"], -s["last_active"].timestamp()))
        self.sessions_list.Set([self.format_session(session) for session in self.sessions])
        if self.sessions:
            self.sessions_list.SetSelection(0)

    def format_session(self, session):
        key = SESSION_CURRENT_FORMAT_KEY if session["current"] else SESSION_FORMAT_KEY
        return self.i18n.get_string(key).format(
            device=session["device"], app=session["app"], country=session["country"],
            date=session["last_active"].astimezone().strftime(DATE_TIME_FORMAT)
        )

    def on_end_session(self, event):
        index = self.sessions_list.GetSelection()
        if not 0 <= index < len(self.sessions):
            return
        session = self.sessions[index]
        title = self.i18n.get_string(APP_TITLE_KEY)
        if session["current"]:
            wx.MessageBox(self.i18n.get_string(MSG_CANNOT_END_CURRENT_KEY), title, wx.OK | wx.ICON_INFORMATION, self)
            return
        answer = wx.MessageBox(
            self.i18n.get_string(MSG_CONFIRM_END_SESSION_KEY).format(session=self.format_session(session)),
            title, wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self
        )
        if answer != wx.YES:
            return
        self.telegram_manager.end_session(
            session["hash"], lambda result, error_key: wx.CallAfter(self.on_session_ended, error_key)
        )

    def on_session_ended(self, error_key):
        if not self:
            return
        if error_key:
            wx.MessageBox(
                self.i18n.get_string(error_key), self.i18n.get_string(APP_TITLE_KEY),
                wx.OK | wx.ICON_ERROR, self
            )
            return
        speak(self.i18n.get_string(MSG_SESSION_ENDED_KEY))
        self.load_sessions()

    def apply_app_settings(self):
        for setting, checkbox in self.checkboxes.items():
            self.settings.set(setting, checkbox.GetValue())
        for setting, choice in self.choices.items():
            self.settings.set(setting, CHOICES[setting][0][choice.GetSelection()])
        self.settings.set(SETTING_MIC_DEVICE, self.mic_names[self.mic_choice.GetSelection()])
        self.settings.set(SETTING_GEMINI_KEY, self.gemini_key_input.GetValue().strip())
        language = LANGUAGES[self.language_choice.GetSelection()]
        self.language_changed = language != self.settings.get(SETTING_LANGUAGE)
        self.settings.set(SETTING_LANGUAGE, language)
        shortcuts.store(self.settings, self.shortcut_table)
        self.settings.save()
        for name, draft in self.sound_changes.items():
            if draft is None:
                sounds.clear_custom(name)
            else:
                sounds.set_custom(name, draft)

    def changed_profile(self):
        """The edited profile, or None if it was not loaded or nothing was changed."""
        if self.profile is None:
            return None
        edited = {field: text_input.GetValue().strip() for field, text_input in self.profile_inputs.items()}
        return edited if edited != self.profile else None
