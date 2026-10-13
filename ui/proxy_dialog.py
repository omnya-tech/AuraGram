import wx
from core import proxy
from core.speech import speak
from ui.layout import prepare_window
from core.constants import (
    APP_TITLE_KEY, PROXY_TITLE_KEY, PROXY_NOTE_KEY, PROXY_LINK_LABEL_KEY, BTN_PROXY_FILL_KEY,
    PROXY_TYPE_LABEL_KEY, PROXY_HOST_LABEL_KEY, PROXY_PORT_LABEL_KEY, PROXY_USER_LABEL_KEY,
    PROXY_PASSWORD_LABEL_KEY, PROXY_SECRET_LABEL_KEY, PROXY_TYPES, MSG_PROXY_FILLED_KEY, ERR_PROXY_LINK_KEY
)

FIELDS = (
    ("host", PROXY_HOST_LABEL_KEY), ("port", PROXY_PORT_LABEL_KEY), ("user", PROXY_USER_LABEL_KEY),
    ("password", PROXY_PASSWORD_LABEL_KEY), ("secret", PROXY_SECRET_LABEL_KEY),
)

class ProxyDialog(wx.Dialog):
    """How Telegram is reached: directly, or through a SOCKS5 or MTProto proxy.

    Open from the login window too, since where Telegram is blocked there is no
    signing in before this is set. OK saves it and reconnects at once.
    """

    def __init__(self, parent, i18n, settings, telegram_manager):
        super().__init__(parent, title=i18n.get_string(PROXY_TITLE_KEY), size=(520, 550))
        prepare_window(self, i18n)
        self.i18n = i18n
        self.settings = settings
        self.telegram_manager = telegram_manager
        self.inputs = {}
        sizer = wx.BoxSizer(wx.VERTICAL)
        note = wx.StaticText(self, label=i18n.get_string(PROXY_NOTE_KEY))
        note.Wrap(480)
        sizer.Add(note, flag=wx.ALL, border=10)
        self.link_input = self.add_input(sizer, PROXY_LINK_LABEL_KEY)
        fill_btn = wx.Button(self, label=i18n.get_string(BTN_PROXY_FILL_KEY))
        fill_btn.Bind(wx.EVT_BUTTON, self.on_fill)
        sizer.Add(fill_btn, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        sizer.Add(wx.StaticText(self, label=i18n.get_string(PROXY_TYPE_LABEL_KEY)), flag=wx.LEFT|wx.RIGHT, border=10)
        self.type_choice = wx.Choice(self, choices=[i18n.get_string(kind) for kind in PROXY_TYPES])
        sizer.Add(self.type_choice, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        for field, label_key in FIELDS:
            self.inputs[field] = self.add_input(sizer, label_key)
        sizer.Add(self.CreateButtonSizer(wx.OK|wx.CANCEL), flag=wx.EXPAND|wx.ALL, border=10)
        self.SetSizer(sizer)
        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
        self.show_proxy(proxy.from_settings(settings))
        self.CenterOnParent()
        self.type_choice.SetFocus()

    def add_input(self, sizer, label_key):
        sizer.Add(wx.StaticText(self, label=self.i18n.get_string(label_key)), flag=wx.LEFT|wx.RIGHT, border=10)
        text_input = wx.TextCtrl(self)
        sizer.Add(text_input, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        return text_input

    def show_proxy(self, values):
        self.type_choice.SetSelection(PROXY_TYPES.index(values["type"]))
        for field, text_input in self.inputs.items():
            text_input.SetValue(values[field])

    def entered(self):
        """The proxy as the fields describe it now."""
        values = {field: text_input.GetValue().strip() for field, text_input in self.inputs.items()}
        values["type"] = PROXY_TYPES[self.type_choice.GetSelection()]
        return values

    def show_error(self, error_key):
        wx.MessageBox(self.i18n.get_string(error_key), self.i18n.get_string(APP_TITLE_KEY), wx.OK | wx.ICON_ERROR, self)

    def on_fill(self, event):
        values = proxy.parse_link(self.link_input.GetValue())
        if values is None:
            self.show_error(ERR_PROXY_LINK_KEY)
            return
        self.show_proxy(values)
        speak(self.i18n.get_string(MSG_PROXY_FILLED_KEY))

    def on_ok(self, event):
        values = self.entered()
        error_key = proxy.error_key(values)
        if error_key:
            self.show_error(error_key)
            return
        proxy.to_settings(self.settings, values)
        self.settings.save()
        self.telegram_manager.set_proxy(values)
        self.EndModal(wx.ID_OK)
