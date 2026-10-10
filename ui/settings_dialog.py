import wx
from core.settings import (
    SETTING_PLAY_SOUND, SETTING_ANNOUNCE_MESSAGES,
    SETTING_OPEN_ON_SELECT, SETTING_MARK_READ_ON_OPEN
)
from core.constants import (
    SETTINGS_TITLE_KEY, SETTINGS_TAB_APP_KEY, SETTINGS_TAB_ACCOUNT_KEY,
    SETTINGS_APP_NOTE_KEY, SETTINGS_ACCOUNT_NOTE_KEY, SETTINGS_PLAY_SOUND_KEY,
    SETTINGS_ANNOUNCE_KEY, SETTINGS_OPEN_ON_SELECT_KEY, SETTINGS_MARK_READ_KEY,
    PROFILE_FIRST_NAME_KEY, PROFILE_LAST_NAME_KEY, PROFILE_ABOUT_KEY,
    MSG_LOADING_KEY, ERR_PROFILE_LOAD_KEY, APP_TITLE_KEY, DATE_TIME_FORMAT,
    PRIVACY_LEVELS, PRIVACY_CUSTOM_KEY, PRIVACY_LABEL_KEY_PREFIX, SETTINGS_TAB_PRIVACY_KEY,
    SETTINGS_TAB_SESSIONS_KEY, SETTINGS_PRIVACY_NOTE_KEY, SESSIONS_LABEL_KEY, SESSION_FORMAT_KEY,
    SESSION_CURRENT_FORMAT_KEY, BTN_END_SESSION_KEY, MSG_CONFIRM_END_SESSION_KEY,
    MSG_SESSION_ENDED_KEY, MSG_CANNOT_END_CURRENT_KEY
)
from core.speech import speak

# Order of the privacy settings on their tab; each has a "PRIVACY_LABEL_<name>" string.
PRIVACY_NAMES = ("last_seen", "phone", "photo", "invites", "calls", "forwards")

APP_OPTIONS = (
    (SETTING_PLAY_SOUND, SETTINGS_PLAY_SOUND_KEY),
    (SETTING_ANNOUNCE_MESSAGES, SETTINGS_ANNOUNCE_KEY),
    (SETTING_OPEN_ON_SELECT, SETTINGS_OPEN_ON_SELECT_KEY),
    (SETTING_MARK_READ_ON_OPEN, SETTINGS_MARK_READ_KEY),
)
PROFILE_FIELDS = (
    ("first_name", PROFILE_FIRST_NAME_KEY),
    ("last_name", PROFILE_LAST_NAME_KEY),
    ("about", PROFILE_ABOUT_KEY),
)

class SettingsDialog(wx.Dialog):
    """Two tabs kept apart on purpose: app preferences stay on this computer,
    account settings change the Telegram account everywhere."""

    def __init__(self, parent, i18n, settings, telegram_manager):
        super().__init__(parent, title=i18n.get_string(SETTINGS_TITLE_KEY), size=(560, 560))
        self.i18n = i18n
        self.settings = settings
        self.telegram_manager = telegram_manager
        self.profile = None
        self.privacy = None
        self.sessions = []
        self.checkboxes = {}
        self.profile_inputs = {}
        self.privacy_choices = {}

        notebook = wx.Notebook(self)
        notebook.AddPage(self.create_app_page(notebook), i18n.get_string(SETTINGS_TAB_APP_KEY))
        notebook.AddPage(self.create_account_page(notebook), i18n.get_string(SETTINGS_TAB_ACCOUNT_KEY))
        notebook.AddPage(self.create_privacy_page(notebook), i18n.get_string(SETTINGS_TAB_PRIVACY_KEY))
        notebook.AddPage(self.create_sessions_page(notebook), i18n.get_string(SETTINGS_TAB_SESSIONS_KEY))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(notebook, proportion=1, flag=wx.EXPAND|wx.ALL, border=10)
        sizer.Add(self.CreateButtonSizer(wx.OK|wx.CANCEL), flag=wx.EXPAND|wx.ALL, border=10)
        self.SetSizer(sizer)
        self.CenterOnParent()

        telegram_manager.load_profile(
            lambda profile, error_key: wx.CallAfter(self.on_profile_loaded, profile, error_key)
        )
        telegram_manager.load_privacy(
            lambda privacy, error_key: wx.CallAfter(self.on_privacy_loaded, privacy, error_key)
        )
        self.load_sessions()

    def create_app_page(self, notebook):
        page = wx.Panel(notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(page, label=self.i18n.get_string(SETTINGS_APP_NOTE_KEY)), flag=wx.ALL, border=10)
        for setting, label_key in APP_OPTIONS:
            checkbox = wx.CheckBox(page, label=self.i18n.get_string(label_key))
            checkbox.SetValue(self.settings.get(setting))
            sizer.Add(checkbox, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
            self.checkboxes[setting] = checkbox
        page.SetSizer(sizer)
        return page

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
        page.SetSizer(sizer)
        return page

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
        self.settings.save()

    def changed_profile(self):
        """The edited profile, or None if it was not loaded or nothing was changed."""
        if self.profile is None:
            return None
        edited = {field: text_input.GetValue().strip() for field, text_input in self.profile_inputs.items()}
        return edited if edited != self.profile else None
