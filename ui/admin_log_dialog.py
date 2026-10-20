import wx
from ui.layout import prepare_window
from core.constants import (
    FEEDBACK_RESULT,
    APP_TITLE_KEY, MSG_LOADING_KEY, DATE_TIME_FORMAT, BTN_CLOSE_KEY,
    ADMIN_LOG_TITLE_FORMAT_KEY, ADMIN_LOG_ENTRY_FORMAT_KEY, ADMIN_LOG_EMPTY_KEY, ADMIN_LOG_KEY_PREFIX,
    ADMIN_LOG_FILTERS, ADMIN_LOG_KIND_LABEL_KEY, ADMIN_LOG_ADMIN_LABEL_KEY, ADMIN_LOG_ALL_ADMINS_KEY,
    ADMIN_LOG_EVENTS_LABEL_KEY, BTN_NOT_SPAM_KEY, MSG_CONFIRM_NOT_SPAM_KEY, MSG_NOT_SPAM_REPORTED_KEY,
    ADMIN_LOG_ANTISPAM_FORMAT_KEY, ADMIN_LOG_DELETED_TEXT_FORMAT_KEY
)
from core.speech import speak, say

class AdminLogDialog(wx.Dialog):
    """Read-only list of what admins did recently in a channel or large group, narrowed if wished
    to one kind of event, or to what one admin did."""

    def __init__(self, parent, i18n, telegram_manager, dialog_id, title):
        super().__init__(
            parent, title=i18n.get_string(ADMIN_LOG_TITLE_FORMAT_KEY).format(title=title),
            size=(560, 520), style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER
        )
        prepare_window(self, i18n)
        self.i18n = i18n
        self.telegram_manager = telegram_manager
        self.dialog_id = dialog_id
        # The admins to narrow the log to, after "all of them"; filled once Telegram names them.
        self.admins = []
        self.events = []
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label=i18n.get_string(ADMIN_LOG_KIND_LABEL_KEY)), flag=wx.LEFT|wx.RIGHT|wx.TOP, border=10)
        self.kind_choice = wx.Choice(self, choices=[i18n.get_string(name) for name in ADMIN_LOG_FILTERS])
        self.kind_choice.SetName(i18n.get_string(ADMIN_LOG_KIND_LABEL_KEY))
        self.kind_choice.SetSelection(0)
        self.kind_choice.Bind(wx.EVT_CHOICE, lambda event: self.load())
        sizer.Add(self.kind_choice, flag=wx.EXPAND|wx.ALL, border=10)
        sizer.Add(wx.StaticText(self, label=i18n.get_string(ADMIN_LOG_ADMIN_LABEL_KEY)), flag=wx.LEFT|wx.RIGHT, border=10)
        self.admin_choice = wx.Choice(self, choices=[i18n.get_string(ADMIN_LOG_ALL_ADMINS_KEY)])
        self.admin_choice.SetName(i18n.get_string(ADMIN_LOG_ADMIN_LABEL_KEY))
        self.admin_choice.SetSelection(0)
        self.admin_choice.Bind(wx.EVT_CHOICE, lambda event: self.load())
        sizer.Add(self.admin_choice, flag=wx.EXPAND|wx.ALL, border=10)
        sizer.Add(wx.StaticText(self, label=i18n.get_string(ADMIN_LOG_EVENTS_LABEL_KEY)), flag=wx.LEFT|wx.RIGHT, border=10)
        self.events_list = wx.ListBox(self, choices=[i18n.get_string(MSG_LOADING_KEY)], style=wx.LB_SINGLE)
        self.events_list.SetName(i18n.get_string(ADMIN_LOG_EVENTS_LABEL_KEY))
        sizer.Add(self.events_list, proportion=1, flag=wx.EXPAND|wx.ALL, border=10)
        self.events_list.Bind(wx.EVT_LISTBOX, lambda event: self.update_not_spam())
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        # For a message anti-spam deleted that was not spam.
        self.not_spam_btn = wx.Button(self, label=i18n.get_string(BTN_NOT_SPAM_KEY))
        self.not_spam_btn.Bind(wx.EVT_BUTTON, self.on_not_spam)
        self.not_spam_btn.Disable()
        buttons.Add(self.not_spam_btn, flag=wx.RIGHT, border=10)
        buttons.Add(wx.Button(self, wx.ID_CANCEL, i18n.get_string(BTN_CLOSE_KEY)))
        sizer.Add(buttons, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        self.SetSizer(sizer)
        self.CenterOnParent()
        telegram_manager.load_admins(dialog_id, lambda admins, error_key: wx.CallAfter(self.show_admins, admins))
        self.load()

    def load(self):
        """Ask for the log again, narrowed as the two choices now say."""
        kinds = list(ADMIN_LOG_FILTERS.values())[max(self.kind_choice.GetSelection(), 0)]
        admin_index = self.admin_choice.GetSelection()
        admin_id = self.admins[admin_index - 1]["id"] if admin_index > 0 else None
        self.events = []
        self.events_list.Set([self.i18n.get_string(MSG_LOADING_KEY)])
        self.update_not_spam()
        self.telegram_manager.load_admin_log(
            self.dialog_id, lambda events, error_key: wx.CallAfter(self.show_events, events, error_key),
            kinds=kinds, admin_id=admin_id
        )

    def show_admins(self, admins):
        # Without them, the log is still there, only not to be narrowed by admin.
        if not self or not admins:
            return
        self.admins = admins
        self.admin_choice.Set([self.i18n.get_string(ADMIN_LOG_ALL_ADMINS_KEY)] + [admin["name"] for admin in admins])
        self.admin_choice.SetSelection(0)

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
        self.events = events
        self.events_list.Set([self.format_event(event) for event in events])
        self.events_list.SetSelection(0)
        self.update_not_spam()

    def selected_event(self):
        index = self.events_list.GetSelection()
        return self.events[index] if 0 <= index < len(self.events) else None

    def update_not_spam(self):
        event = self.selected_event()
        self.not_spam_btn.Enable(bool(event and event["by_antispam"] and event["message_id"]))

    def on_not_spam(self, event):
        chosen = self.selected_event()
        if not chosen or not chosen["message_id"]:
            return
        answer = wx.MessageBox(
            self.i18n.get_string(MSG_CONFIRM_NOT_SPAM_KEY), self.i18n.get_string(APP_TITLE_KEY),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self
        )
        if answer == wx.YES:
            self.telegram_manager.report_not_spam(
                self.dialog_id, chosen["message_id"], lambda result, error_key: wx.CallAfter(self.on_reported, error_key)
            )

    def on_reported(self, error_key):
        if not self:
            return
        if error_key:
            wx.MessageBox(
                self.i18n.get_string(error_key), self.i18n.get_string(APP_TITLE_KEY), wx.OK | wx.ICON_ERROR, self
            )
        else:
            say(self.i18n.get_string(MSG_NOT_SPAM_REPORTED_KEY), FEEDBACK_RESULT)

    def format_event(self, event):
        key = ADMIN_LOG_KEY_PREFIX + event["action"]
        action = self.i18n.get_string(key)
        # No translation for this kind of action: Telegram's own name is better than nothing.
        if action == key:
            action = event["action"]
        entry = self.i18n.get_string(ADMIN_LOG_ENTRY_FORMAT_KEY).format(
            user=event["user"], action=action,
            date=event["date"].astimezone().strftime(DATE_TIME_FORMAT)
        )
        if event.get("by_antispam"):
            entry = self.i18n.get_string(ADMIN_LOG_ANTISPAM_FORMAT_KEY).format(entry=entry)
        if event.get("text"):
            entry = self.i18n.get_string(ADMIN_LOG_DELETED_TEXT_FORMAT_KEY).format(entry=entry, text=event["text"])
        return entry
