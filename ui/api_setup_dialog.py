import wx
from ui.layout import prepare_window
from core.config import clean_api_hash
from core.constants import (
    APP_TITLE_KEY, API_SETUP_TITLE_KEY, API_SETUP_NOTE_KEY, API_ID_LABEL_KEY,
    API_HASH_LABEL_KEY, ERR_API_ID_KEY
)

class ApiSetupDialog(wx.Dialog):
    """First run: asks for the Telegram API id and hash the app signs in with."""

    def __init__(self, i18n):
        super().__init__(None, title=i18n.get_string(API_SETUP_TITLE_KEY), size=(520, 360))
        prepare_window(self, i18n)
        self.i18n = i18n
        self.credentials = None
        sizer = wx.BoxSizer(wx.VERTICAL)
        # A read-only field rather than a label, so a screen reader can go through it.
        note = wx.TextCtrl(
            self, value=i18n.get_string(API_SETUP_NOTE_KEY),
            style=wx.TE_MULTILINE|wx.TE_READONLY, size=(-1, 90)
        )
        sizer.Add(note, flag=wx.EXPAND|wx.ALL, border=10)
        sizer.Add(wx.StaticText(self, label=i18n.get_string(API_ID_LABEL_KEY)), flag=wx.LEFT|wx.RIGHT, border=10)
        self.id_input = wx.TextCtrl(self)
        sizer.Add(self.id_input, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        sizer.Add(wx.StaticText(self, label=i18n.get_string(API_HASH_LABEL_KEY)), flag=wx.LEFT|wx.RIGHT, border=10)
        self.hash_input = wx.TextCtrl(self)
        sizer.Add(self.hash_input, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        sizer.Add(self.CreateButtonSizer(wx.OK|wx.CANCEL), flag=wx.EXPAND|wx.ALL, border=10)
        self.SetSizer(sizer)
        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
        self.CenterOnScreen()
        self.id_input.SetFocus()

    def on_ok(self, event):
        api_id = self.id_input.GetValue().strip()
        # Checked here, not by Telegram later: a hash with one stray character
        # would be saved, and then every sign-in attempt would fail.
        api_hash = clean_api_hash(self.hash_input.GetValue())
        if not api_id.isdigit() or not api_hash:
            wx.MessageBox(
                self.i18n.get_string(ERR_API_ID_KEY), self.i18n.get_string(APP_TITLE_KEY),
                wx.OK | wx.ICON_ERROR, self
            )
            return
        self.credentials = (int(api_id), api_hash)
        self.EndModal(wx.ID_OK)
