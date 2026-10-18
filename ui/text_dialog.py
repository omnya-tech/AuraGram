import wx
from ui.layout import prepare_window
from core.constants import BTN_CLOSE_KEY, BTN_EXPORT_KEY

class TextDialog(wx.Dialog):
    """Shows text in a read-only field, so a screen reader can go through it
    line by line, word by word, and copy from it. With `on_export`, an Export button calls it."""

    def __init__(self, parent, i18n, title, text, on_export=None):
        super().__init__(parent, title=title, size=(560, 420), style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
        prepare_window(self, i18n)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.text = wx.TextCtrl(self, value=text, style=wx.TE_MULTILINE|wx.TE_READONLY)
        sizer.Add(self.text, proportion=1, flag=wx.EXPAND|wx.ALL, border=10)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        if on_export is not None:
            export_button = wx.Button(self, label=i18n.get_string(BTN_EXPORT_KEY))
            export_button.Bind(wx.EVT_BUTTON, lambda event: on_export())
            buttons.Add(export_button, flag=wx.RIGHT, border=10)
        buttons.Add(wx.Button(self, wx.ID_CANCEL, i18n.get_string(BTN_CLOSE_KEY)))
        sizer.Add(buttons, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        self.SetSizer(sizer)
        self.CenterOnParent()
        self.text.SetFocus()
        self.text.SetInsertionPoint(0)
