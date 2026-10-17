import wx
from core.speech import speak
from ui.layout import prepare_window
from core.constants import (
    DOWNLOAD_FILES_TITLE_FORMAT_KEY, DOWNLOAD_FILES_LABEL_KEY, BTN_SELECT_ALL_KEY, BTN_SELECT_NONE_KEY,
    BTN_DOWNLOAD_KEY, DOWNLOAD_SELECTED_FORMAT_KEY, MSG_NOTHING_CHOSEN_KEY
)

class DownloadFilesDialog(wx.Dialog):
    """The files of one chat, each with a box to tick: one by one with Space, or all at
    once with a button or Ctrl+A. `chosen()` gives the positions ticked, in list order."""

    def __init__(self, parent, i18n, chat_title, rows):
        super().__init__(
            parent, title=i18n.get_string(DOWNLOAD_FILES_TITLE_FORMAT_KEY).format(chat=chat_title),
            size=(560, 560), style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER
        )
        prepare_window(self, i18n)
        self.i18n = i18n
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label=i18n.get_string(DOWNLOAD_FILES_LABEL_KEY)), flag=wx.ALL, border=10)
        self.files_list = wx.CheckListBox(self, choices=rows)
        self.files_list.SetName(i18n.get_string(DOWNLOAD_FILES_LABEL_KEY))
        self.files_list.Bind(wx.EVT_CHECKLISTBOX, lambda event: self.show_count())
        sizer.Add(self.files_list, proportion=1, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        self.count_label = wx.StaticText(self)
        sizer.Add(self.count_label, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        for label_key, checked in ((BTN_SELECT_ALL_KEY, True), (BTN_SELECT_NONE_KEY, False)):
            button = wx.Button(self, label=i18n.get_string(label_key))
            button.Bind(wx.EVT_BUTTON, lambda event, checked=checked: self.check_all(checked))
            buttons.Add(button, flag=wx.RIGHT, border=10)
        sizer.Add(buttons, flag=wx.LEFT|wx.RIGHT, border=10)
        dialog_buttons = self.CreateButtonSizer(wx.OK|wx.CANCEL)
        self.FindWindow(wx.ID_OK).SetLabel(i18n.get_string(BTN_DOWNLOAD_KEY))
        sizer.Add(dialog_buttons, flag=wx.EXPAND|wx.ALL, border=10)
        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.SetSizer(sizer)
        self.CenterOnParent()
        if rows:
            self.files_list.SetSelection(0)
        self.show_count()
        self.files_list.SetFocus()

    def chosen(self):
        return list(self.files_list.GetCheckedItems())

    def check_all(self, checked):
        for index in range(self.files_list.GetCount()):
            self.files_list.Check(index, checked)
        self.show_count()
        # Nothing on screen moved: say what changed.
        speak(self.count_label.GetLabel())

    def show_count(self):
        self.count_label.SetLabel(self.i18n.get_string(DOWNLOAD_SELECTED_FORMAT_KEY).format(
            count=len(self.chosen()), total=self.files_list.GetCount()
        ))

    def on_char_hook(self, event):
        if event.GetKeyCode() == ord("A") and event.GetModifiers() == wx.MOD_CONTROL:
            self.check_all(True)
        else:
            event.Skip()

    def on_ok(self, event):
        if not self.chosen():
            speak(self.i18n.get_string(MSG_NOTHING_CHOSEN_KEY))
            return
        event.Skip()
