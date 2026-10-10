import datetime
import os
import wx
from core.speech import speak
from core.constants import (
    MESSAGES_LIMIT, MSG_LOAD_OLDER_KEY, MSG_DOWNLOADING_KEY,
    DOWNLOADABLE_MEDIA, SAFE_OPEN_EXTENSIONS, DIALOGS_LIMIT, SNIPPET_LENGTH,
    MSG_LOAD_MORE_DIALOGS_KEY, MENU_MESSAGE_KEY, MENU_REPLY_KEY, REPLY_LABEL_FORMAT_KEY,
    REPLY_PREFIX_FORMAT_KEY, MSG_REPLY_CANCELLED_KEY, ANNOUNCE_FORMAT_KEY,
    APP_TITLE_KEY, MAIN_TITLE_KEY, DIALOGS_LABEL_KEY, MESSAGES_LABEL_KEY,
    MESSAGE_INPUT_LABEL_KEY, BTN_SEND_MESSAGE_KEY, DIALOG_UNREAD_FORMAT_KEY,
    MESSAGE_FORMAT_KEY, SENDER_YOU_KEY, MSG_NO_TEXT_KEY, MSG_LOADING_KEY,
    STATUS_READY_KEY, TIME_FORMAT, DATE_TIME_FORMAT, SELECT_DELAY_MS,
    MEDIA_FORMAT_KEY, MENU_FILE_KEY, MENU_LOGOUT_KEY, MENU_EXIT_KEY, MSG_CONFIRM_LOGOUT_KEY
)

class MainFrame(wx.Frame):
    def __init__(self, i18n, telegram_manager, on_logout):
        super().__init__(None, title=i18n.get_string(MAIN_TITLE_KEY), size=(900, 600))
        self.i18n = i18n
        self.telegram_manager = telegram_manager
        self.on_logout = on_logout
        self.dialogs = []
        self.current_dialog_id = None
        self.select_timer = None
        self.dialogs_limit = DIALOGS_LIMIT
        self.has_more_dialogs = False
        self.reply_to = None
        self.messages = []
        self.has_older = False
        # True while older messages or a media file are being fetched.
        self.is_busy = False
        self.init_ui()
        self.telegram_manager.set_message_listener(
            lambda *args: wx.CallAfter(self.on_new_message, *args)
        )
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
        self.messages_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_activate_message)
        chat_box.Add(self.messages_list, proportion=1, flag=wx.EXPAND|wx.BOTTOM, border=15)

        self.input_label = wx.StaticText(self.panel, label=self.i18n.get_string(MESSAGE_INPUT_LABEL_KEY))
        chat_box.Add(self.input_label, flag=wx.BOTTOM, border=5)
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
        self.init_menu()
        self.CreateStatusBar()
        self.enable_chat(False)
        self.Center()
        wx.CallAfter(self.dialogs_list.SetFocus)

    def init_menu(self):
        file_menu = wx.Menu()
        logout_item = file_menu.Append(wx.ID_ANY, self.i18n.get_string(MENU_LOGOUT_KEY))
        self.Bind(wx.EVT_MENU, self.on_logout_menu, logout_item)
        file_menu.AppendSeparator()
        exit_item = file_menu.Append(wx.ID_EXIT, self.i18n.get_string(MENU_EXIT_KEY))
        self.Bind(wx.EVT_MENU, lambda event: self.Close(), exit_item)

        message_menu = wx.Menu()
        reply_item = message_menu.Append(wx.ID_ANY, self.i18n.get_string(MENU_REPLY_KEY))
        self.Bind(wx.EVT_MENU, self.on_reply_menu, reply_item)

        menu_bar = wx.MenuBar()
        menu_bar.Append(file_menu, self.i18n.get_string(MENU_FILE_KEY))
        menu_bar.Append(message_menu, self.i18n.get_string(MENU_MESSAGE_KEY))
        self.SetMenuBar(menu_bar)

    def on_reply_menu(self, event):
        index = self.messages_list.GetSelection() - self.message_offset()
        if 0 <= index < len(self.messages):
            self.set_reply(self.messages[index])

    def set_reply(self, message):
        """Make the next sent message a reply to `message`; None goes back to a normal message."""
        self.reply_to = message
        if message is None:
            label = self.i18n.get_string(MESSAGE_INPUT_LABEL_KEY)
        else:
            label = self.i18n.get_string(REPLY_LABEL_FORMAT_KEY).format(
                sender=self.sender_name(message), text=self.message_snippet(message)
            )
        # The field's label is what the screen reader reads when it gets focus.
        self.input_label.SetLabel(label)
        self.message_input.SetName(label)
        self.panel.Layout()
        if message is not None:
            self.message_input.SetFocus()
            speak(label)

    def on_logout_menu(self, event):
        answer = wx.MessageBox(
            self.i18n.get_string(MSG_CONFIRM_LOGOUT_KEY), self.i18n.get_string(APP_TITLE_KEY),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self
        )
        if answer == wx.YES:
            self.on_logout()

    def enable_chat(self, enabled):
        self.message_input.Enable(enabled)
        self.send_btn.Enable(enabled)

    def set_status(self, key):
        self.SetStatusText(self.i18n.get_string(key))

    def show_error(self, error_key):
        self.set_status(STATUS_READY_KEY)
        self.is_busy = False
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
        self.telegram_manager.load_dialogs(self.on_ui_thread(self.show_dialogs), self.dialogs_limit)

    def show_dialogs(self, dialogs):
        selected = self.dialogs_list.GetSelection()
        was_on_load_more = self.has_more_dialogs and selected == len(self.dialogs)
        first_new_index = len(self.dialogs)
        selected_id = self.dialogs[selected]["id"] if 0 <= selected < len(self.dialogs) else None

        self.dialogs = dialogs
        # A full page means Telegram most likely has more chats after it.
        self.has_more_dialogs = len(dialogs) == self.dialogs_limit
        items = [self.format_dialog(dialog) for dialog in dialogs]
        if self.has_more_dialogs:
            items.append(self.i18n.get_string(MSG_LOAD_MORE_DIALOGS_KEY))
        self.dialogs_list.Set(items)

        if was_on_load_more and first_new_index < len(dialogs):
            # Continue from the first chat that was just added.
            self.dialogs_list.SetSelection(first_new_index)
        elif self.find_dialog_index(selected_id) != wx.NOT_FOUND:
            self.dialogs_list.SetSelection(self.find_dialog_index(selected_id))
        elif dialogs:
            self.dialogs_list.SetSelection(0)
        self.set_status(STATUS_READY_KEY)

    def load_more_dialogs(self):
        self.dialogs_limit += DIALOGS_LIMIT
        self.load_dialogs()

    def format_dialog(self, dialog):
        if not dialog["unread"]:
            return dialog["title"]
        return self.i18n.get_string(DIALOG_UNREAD_FORMAT_KEY).format(
            title=dialog["title"], count=dialog["unread"]
        )

    def on_char_hook(self, event):
        is_enter = event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
        focused = wx.Window.FindFocus()
        if is_enter and focused is self.dialogs_list:
            self.on_open_dialog(event)
        elif is_enter and focused is self.messages_list:
            self.on_activate_message(event)
        elif event.GetKeyCode() == wx.WXK_ESCAPE and self.reply_to is not None:
            self.set_reply(None)
            speak(self.i18n.get_string(MSG_REPLY_CANCELLED_KEY))
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
        if index >= len(self.dialogs):
            # The "load more chats" row: act on Enter only, not on merely passing over it.
            if focus_messages:
                self.load_more_dialogs()
            return
        dialog_id = self.dialogs[index]["id"]
        if dialog_id == self.current_dialog_id:
            if focus_messages:
                self.messages_list.SetFocus()
            return
        self.current_dialog_id = dialog_id
        self.set_reply(None)
        self.messages = []
        self.has_older = False
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
        self.messages = messages
        # A full page means Telegram most likely has more before it.
        self.has_older = len(messages) == MESSAGES_LIMIT
        self.render_messages(len(messages) - 1)
        # Loading a chat marks it as read on Telegram's side.
        self.set_unread(dialog_id, 0)
        self.enable_chat(True)
        self.set_status(STATUS_READY_KEY)
        if focus_messages:
            self.messages_list.SetFocus()

    def render_messages(self, selected_message_index):
        """Refill the list; when older messages exist, its first row is the "load older" action."""
        items = [self.format_message(message) for message in self.messages]
        if self.has_older:
            items.insert(0, self.i18n.get_string(MSG_LOAD_OLDER_KEY))
        self.messages_list.Set(items)
        if self.messages:
            self.messages_list.SetSelection(selected_message_index + self.message_offset())

    def message_offset(self):
        return 1 if self.has_older else 0

    def on_activate_message(self, event):
        index = self.messages_list.GetSelection()
        if index == wx.NOT_FOUND or self.is_busy:
            return
        if self.has_older and index == 0:
            self.load_older_messages()
            return
        message = self.messages[index - self.message_offset()]
        if message["media"] in DOWNLOADABLE_MEDIA:
            self.download_media(message)

    def load_older_messages(self):
        self.is_busy = True
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        self.telegram_manager.load_messages(
            dialog_id, self.on_ui_thread(self.show_older_messages, dialog_id),
            before_id=self.messages[0]["id"]
        )

    def show_older_messages(self, older, dialog_id):
        self.is_busy = False
        if dialog_id != self.current_dialog_id:
            return
        self.messages = older + self.messages
        self.has_older = len(older) == MESSAGES_LIMIT
        # Land on the message just before the ones already read, so Up keeps going back in time.
        self.render_messages(max(len(older) - 1, 0))
        self.set_status(STATUS_READY_KEY)

    def download_media(self, message):
        self.is_busy = True
        self.set_status(MSG_DOWNLOADING_KEY)
        self.telegram_manager.download_media(
            self.current_dialog_id, message["id"], self.on_ui_thread(self.open_media)
        )

    def open_media(self, path):
        self.is_busy = False
        self.set_status(STATUS_READY_KEY)
        # Only hand known media formats to their default app; anything else
        # could be a program, so just show the folder it was saved in.
        if os.path.splitext(path)[1].lower() in SAFE_OPEN_EXTENSIONS:
            wx.LaunchDefaultApplication(path)
        else:
            wx.LaunchDefaultApplication(os.path.dirname(path))

    def find_dialog_index(self, dialog_id):
        for index, dialog in enumerate(self.dialogs):
            if dialog["id"] == dialog_id:
                return index
        return wx.NOT_FOUND

    def set_unread(self, dialog_id, count):
        index = self.find_dialog_index(dialog_id)
        if index == wx.NOT_FOUND or self.dialogs[index]["unread"] == count:
            return
        self.dialogs[index]["unread"] = count
        self.dialogs_list.SetString(index, self.format_dialog(self.dialogs[index]))

    def on_new_message(self, dialog_id, title, message):
        if not self:
            return
        index = self.find_dialog_index(dialog_id)
        if index == wx.NOT_FOUND:
            dialog = {"id": dialog_id, "title": title, "unread": 0, "pinned": False, "muted": False}
        else:
            dialog = self.dialogs[index]

        is_current = dialog_id == self.current_dialog_id
        if not message["outgoing"] and not dialog["muted"]:
            if not (is_current and self.IsActive()):
                wx.Bell()
            # In the open chat the sender is what matters; elsewhere, which chat it came from.
            speak(self.i18n.get_string(ANNOUNCE_FORMAT_KEY).format(
                source=message["sender"] if is_current else dialog["title"],
                text=self.message_snippet(message)
            ))

        if dialog_id == self.current_dialog_id:
            self.append_message(message)
            if not message["outgoing"]:
                self.telegram_manager.mark_read(dialog_id)
        elif not message["outgoing"]:
            dialog["unread"] += 1
        self.move_dialog_to_top(index, dialog)

    def append_message(self, message):
        if any(shown["id"] == message["id"] for shown in self.messages):
            return
        self.messages.append(message)
        count = self.messages_list.GetCount()
        was_at_end = self.messages_list.GetSelection() in (wx.NOT_FOUND, count - 1)
        self.messages_list.Append(self.format_message(message))
        # Follow the conversation only if the user is not reading older messages.
        if was_at_end:
            self.messages_list.SetSelection(count)

    def move_dialog_to_top(self, index, dialog):
        """Put the dialog where Telegram shows the most recent chat: right below the pinned ones."""
        selected = self.dialogs_list.GetSelection()
        selected_id = self.dialogs[selected]["id"] if 0 <= selected < len(self.dialogs) else None

        if index != wx.NOT_FOUND:
            del self.dialogs[index]
            self.dialogs_list.Delete(index)
        if dialog["pinned"] and index != wx.NOT_FOUND:
            new_index = index
        else:
            new_index = sum(1 for other in self.dialogs if other["pinned"])
        self.dialogs.insert(new_index, dialog)
        self.dialogs_list.Insert(self.format_dialog(dialog), new_index)

        if selected_id is not None:
            self.dialogs_list.SetSelection(self.find_dialog_index(selected_id))

    def sender_name(self, message):
        if message["outgoing"]:
            return self.i18n.get_string(SENDER_YOU_KEY)
        return message["sender"]

    def message_text(self, message):
        text = message["text"]
        if message["media"]:
            text = self.i18n.get_string(MEDIA_FORMAT_KEY).format(
                media=self.i18n.get_string(message["media"]), text=text
            ).strip()
        return text or self.i18n.get_string(MSG_NO_TEXT_KEY)

    def message_snippet(self, message):
        text = " ".join(self.message_text(message).split())
        if len(text) > SNIPPET_LENGTH:
            text = text[:SNIPPET_LENGTH] + "…"
        return text

    def format_message(self, message):
        local_date = message["date"].astimezone()
        is_today = local_date.date() == datetime.date.today()
        text = self.message_text(message)
        # The replied-to message can only be quoted if it is among the loaded ones.
        replied = next((m for m in self.messages if m["id"] == message["reply_to"]), None)
        if replied is not None:
            text = self.i18n.get_string(REPLY_PREFIX_FORMAT_KEY).format(
                sender=self.sender_name(replied), quote=self.message_snippet(replied), text=text
            )
        return self.i18n.get_string(MESSAGE_FORMAT_KEY).format(
            sender=self.sender_name(message),
            text=text,
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
            dialog_id, text, self.on_ui_thread(self.on_message_sent, dialog_id),
            reply_to=self.reply_to["id"] if self.reply_to else None
        )

    def on_message_sent(self, result, dialog_id):
        if dialog_id != self.current_dialog_id:
            return
        self.set_reply(None)
        # Re-enable before focusing: a disabled field cannot take focus.
        self.enable_chat(True)
        self.message_input.Clear()
        self.load_messages()
        self.message_input.SetFocus()
