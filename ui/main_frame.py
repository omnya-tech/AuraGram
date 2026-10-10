import datetime
import wx
from core.constants import (
    APP_TITLE_KEY, MAIN_TITLE_KEY, DIALOGS_LABEL_KEY, MESSAGES_LABEL_KEY,
    MESSAGE_INPUT_LABEL_KEY, BTN_SEND_MESSAGE_KEY, DIALOG_UNREAD_FORMAT_KEY,
    MESSAGE_FORMAT_KEY, SENDER_YOU_KEY, MSG_NO_TEXT_KEY, MSG_LOADING_KEY,
    STATUS_READY_KEY, TIME_FORMAT, DATE_TIME_FORMAT, SELECT_DELAY_MS
)

class MainFrame(wx.Frame):
    def __init__(self, i18n, telegram_manager):
        super().__init__(None, title=i18n.get_string(MAIN_TITLE_KEY), size=(900, 600))
        self.i18n = i18n
        self.telegram_manager = telegram_manager
        self.dialogs = []
        self.current_dialog_id = None
        self.select_timer = None
        self.init_ui()
        self.load_dialogs()

    def init_ui(self):
        self.panel = wx.Panel(self)
        hbox = wx.BoxSizer(wx.HORIZONTAL)

        dialogs_box = wx.BoxSizer(wx.VERTICAL)
        dialogs_label = wx.StaticText(self.panel, label=self.i18n.get_string(DIALOGS_LABEL_KEY))
        dialogs_box.Add(dialogs_label, flag=wx.BOTTOM, border=5)
        self.dialogs_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        self.dialogs_list.Bind(wx.EVT_LISTBOX, self.on_select_dialog)
        self.dialogs_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_open_dialog)
        # Enter never reaches the list as a key event inside a panel, so catch it here.
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        dialogs_box.Add(self.dialogs_list, proportion=1, flag=wx.EXPAND)
        hbox.Add(dialogs_box, proportion=1, flag=wx.EXPAND|wx.ALL, border=15)

        chat_box = wx.BoxSizer(wx.VERTICAL)
        messages_label = wx.StaticText(self.panel, label=self.i18n.get_string(MESSAGES_LABEL_KEY))
        chat_box.Add(messages_label, flag=wx.BOTTOM, border=5)
        self.messages_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        chat_box.Add(self.messages_list, proportion=1, flag=wx.EXPAND|wx.BOTTOM, border=15)

        input_label = wx.StaticText(self.panel, label=self.i18n.get_string(MESSAGE_INPUT_LABEL_KEY))
        chat_box.Add(input_label, flag=wx.BOTTOM, border=5)
        input_box = wx.BoxSizer(wx.HORIZONTAL)
        self.message_input = wx.TextCtrl(self.panel, style=wx.TE_PROCESS_ENTER)
        self.message_input.Bind(wx.EVT_TEXT_ENTER, self.on_send_message)
        input_box.Add(self.message_input, proportion=1, flag=wx.EXPAND|wx.RIGHT, border=10)
        self.send_btn = wx.Button(self.panel, label=self.i18n.get_string(BTN_SEND_MESSAGE_KEY))
        self.send_btn.Bind(wx.EVT_BUTTON, self.on_send_message)
        input_box.Add(self.send_btn)
        chat_box.Add(input_box, flag=wx.EXPAND)
        hbox.Add(chat_box, proportion=2, flag=wx.EXPAND|wx.TOP|wx.RIGHT|wx.BOTTOM, border=15)

        self.panel.SetSizer(hbox)
        self.CreateStatusBar()
        self.enable_chat(False)
        self.Center()
        wx.CallAfter(self.dialogs_list.SetFocus)

    def enable_chat(self, enabled):
        self.message_input.Enable(enabled)
        self.send_btn.Enable(enabled)

    def set_status(self, key):
        self.SetStatusText(self.i18n.get_string(key))

    def show_error(self, error_key):
        self.set_status(STATUS_READY_KEY)
        self.enable_chat(self.current_dialog_id is not None)
        wx.MessageBox(
            self.i18n.get_string(error_key), self.i18n.get_string(APP_TITLE_KEY),
            wx.OK | wx.ICON_ERROR, self
        )

    def on_ui_thread(self, handler, *args):
        """Wrap a handler so the Telegram thread can deliver its result to the UI."""
        def deliver(result, error_key):
            wx.CallAfter(self.handle_result, handler, result, error_key, *args)
        return deliver

    def handle_result(self, handler, result, error_key, *args):
        if not self:
            return
        if error_key:
            self.show_error(error_key)
        else:
            handler(result, *args)

    def load_dialogs(self):
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.load_dialogs(self.on_ui_thread(self.show_dialogs))

    def show_dialogs(self, dialogs):
        self.dialogs = dialogs
        self.dialogs_list.Set([self.format_dialog(dialog) for dialog in dialogs])
        if dialogs:
            self.dialogs_list.SetSelection(0)
        self.set_status(STATUS_READY_KEY)

    def format_dialog(self, dialog):
        if not dialog["unread"]:
            return dialog["title"]
        return self.i18n.get_string(DIALOG_UNREAD_FORMAT_KEY).format(
            title=dialog["title"], count=dialog["unread"]
        )

    def on_char_hook(self, event):
        is_enter = event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
        if is_enter and wx.Window.FindFocus() is self.dialogs_list:
            self.on_open_dialog(event)
        else:
            event.Skip()

    def on_select_dialog(self, event):
        # Wait for the selection to settle so arrowing through the list
        # does not send a request per chat.
        if self.select_timer:
            self.select_timer.Stop()
        self.select_timer = wx.CallLater(SELECT_DELAY_MS, self.open_selected_dialog, False)

    def on_open_dialog(self, event):
        if self.select_timer:
            self.select_timer.Stop()
        self.open_selected_dialog(True)

    def open_selected_dialog(self, focus_messages):
        index = self.dialogs_list.GetSelection()
        if index == wx.NOT_FOUND:
            return
        dialog_id = self.dialogs[index]["id"]
        if dialog_id == self.current_dialog_id:
            if focus_messages:
                self.messages_list.SetFocus()
            return
        self.current_dialog_id = dialog_id
        self.messages_list.Clear()
        self.enable_chat(False)
        self.load_messages(focus_messages)

    def load_messages(self, focus_messages=False):
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        self.telegram_manager.load_messages(
            dialog_id, self.on_ui_thread(self.show_messages, dialog_id, focus_messages)
        )

    def show_messages(self, messages, dialog_id, focus_messages):
        # The user may have opened another chat while this one was loading.
        if dialog_id != self.current_dialog_id:
            return
        self.messages_list.Set([self.format_message(message) for message in messages])
        if messages:
            self.messages_list.SetSelection(len(messages) - 1)
        self.enable_chat(True)
        self.set_status(STATUS_READY_KEY)
        if focus_messages:
            self.messages_list.SetFocus()

    def format_message(self, message):
        if message["outgoing"]:
            sender = self.i18n.get_string(SENDER_YOU_KEY)
        else:
            sender = message["sender"]
        local_date = message["date"].astimezone()
        is_today = local_date.date() == datetime.date.today()
        return self.i18n.get_string(MESSAGE_FORMAT_KEY).format(
            sender=sender,
            text=message["text"] or self.i18n.get_string(MSG_NO_TEXT_KEY),
            time=local_date.strftime(TIME_FORMAT if is_today else DATE_TIME_FORMAT)
        )

    def on_send_message(self, event):
        text = self.message_input.GetValue().strip()
        if not text or self.current_dialog_id is None:
            return
        self.enable_chat(False)
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        self.telegram_manager.send_message(
            dialog_id, text, self.on_ui_thread(self.on_message_sent, dialog_id)
        )

    def on_message_sent(self, result, dialog_id):
        if dialog_id != self.current_dialog_id:
            return
        self.message_input.Clear()
        self.load_messages()
        self.message_input.SetFocus()
