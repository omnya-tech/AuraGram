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
    MSG_LOADING_KEY, ERR_PROFILE_LOAD_KEY
)

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
        super().__init__(parent, title=i18n.get_string(SETTINGS_TITLE_KEY), size=(520, 420))
        self.i18n = i18n
        self.settings = settings
        self.profile = None
        self.checkboxes = {}
        self.profile_inputs = {}

        notebook = wx.Notebook(self)
        notebook.AddPage(self.create_app_page(notebook), i18n.get_string(SETTINGS_TAB_APP_KEY))
        notebook.AddPage(self.create_account_page(notebook), i18n.get_string(SETTINGS_TAB_ACCOUNT_KEY))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(notebook, proportion=1, flag=wx.EXPAND|wx.ALL, border=10)
        sizer.Add(self.CreateButtonSizer(wx.OK|wx.CANCEL), flag=wx.EXPAND|wx.ALL, border=10)
        self.SetSizer(sizer)
        self.CenterOnParent()

        telegram_manager.load_profile(
            lambda profile, error_key: wx.CallAfter(self.on_profile_loaded, profile, error_key)
        )

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
