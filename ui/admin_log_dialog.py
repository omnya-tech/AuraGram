import wx
from core.constants import (
    APP_TITLE_KEY, MSG_LOADING_KEY, DATE_TIME_FORMAT, BTN_CLOSE_KEY,
    ADMIN_LOG_TITLE_FORMAT_KEY, ADMIN_LOG_ENTRY_FORMAT_KEY, ADMIN_LOG_EMPTY_KEY, ADMIN_LOG_KEY_PREFIX
)

class AdminLogDialog(wx.Dialog):
    """Read-only list of what admins did recently in a channel or large group."""

    def __init__(self, parent, i18n, telegram_manager, dialog_id, title):
        super().__init__(
            parent, title=i18n.get_string(ADMIN_LOG_TITLE_FORMAT_KEY).format(title=title),
            size=(560, 480), style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER
        )
        self.i18n = i18n
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.events_list = wx.ListBox(self, choices=[i18n.get_string(MSG_LOADING_KEY)], style=wx.LB_SINGLE)
        sizer.Add(self.events_list, proportion=1, flag=wx.EXPAND|wx.ALL, border=10)
        sizer.Add(wx.Button(self, wx.ID_CANCEL, i18n.get_string(BTN_CLOSE_KEY)), flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        self.SetSizer(sizer)
        self.CenterOnParent()
        telegram_manager.load_admin_log(
            dialog_id, lambda events, error_key: wx.CallAfter(self.show_events, events, error_key)
        )

    def show_events(self, events, error_key):
        # The dialog may have been closed before Telegram answered.
        if not self:
            return
        if error_key:
            self.events_list.Clear()
            wx.MessageBox(
                self.i18n.get_string(error_key), self.i18n.get_string(APP_TITLE_KEY),
                wx.OK | wx.ICON_ERROR, self
            )
            return
        if not events:
            self.events_list.Set([self.i18n.get_string(ADMIN_LOG_EMPTY_KEY)])
            return
        self.events_list.Set([self.format_event(event) for event in events])
        self.events_list.SetSelection(0)
        self.events_list.SetFocus()

    def format_event(self, event):
        key = ADMIN_LOG_KEY_PREFIX + event["action"]
        action = self.i18n.get_string(key)
        # No translation for this kind of action: Telegram's own name is better than nothing.
        if action == key:
            action = event["action"]
        return self.i18n.get_string(ADMIN_LOG_ENTRY_FORMAT_KEY).format(
            user=event["user"], action=action,
            date=event["date"].astimezone().strftime(DATE_TIME_FORMAT)
        )
