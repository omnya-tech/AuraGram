import datetime
import os
import wx
from core import audio
from core.speech import speak
from core.settings import (
    SETTING_PLAY_SOUND, SETTING_ANNOUNCE_MESSAGES,
    SETTING_OPEN_ON_SELECT, SETTING_MARK_READ_ON_OPEN
)
from ui.settings_dialog import SettingsDialog
from ui.chat_info_dialog import ChatInfoDialog
from core.chat_views import build_views
from core.constants import (
    VIEW_LABEL_KEY, MSG_VIEW_COUNT_FORMAT_KEY, MSG_PRIVACY_SAVED_KEY, MENU_CHATS_KEY, MENU_NEW_CHAT_KEY,
    MENU_FIND_CHAT_KEY, MENU_FORWARD_KEY, CONTEXT_FORWARD_KEY, MSG_CHOOSE_CONTACT_KEY,
    MSG_NO_CONTACTS_KEY, MSG_FIND_CHAT_PROMPT_KEY, MSG_FORWARD_TO_KEY, MSG_FORWARDED_FORMAT_KEY,
    CONTEXT_INFO_KEY, MSG_CHAT_SAVED_KEY, MENU_PIN_KEY, CONTEXT_PIN_KEY, CONTEXT_UNPIN_KEY,
    MSG_PINNED_KEY, MSG_UNPINNED_KEY, MSG_CANNOT_PIN_KEY, PINNED_FORMAT_KEY,
    MSG_CONFIRM_DELETE_OTHER_KEY,
    MENU_SETTINGS_KEY, MSG_SETTINGS_SAVED_KEY, MSG_PROFILE_SAVED_KEY, ERR_FIRST_NAME_REQUIRED_KEY,
    CONTEXT_OPEN_KEY, CONTEXT_MARK_READ_KEY, CONTEXT_MUTE_KEY, CONTEXT_UNMUTE_KEY,
    CONTEXT_REPLY_KEY, CONTEXT_EDIT_KEY, CONTEXT_DELETE_KEY, CONTEXT_COPY_KEY,
    CONTEXT_OPEN_MEDIA_KEY, MSG_MARKED_READ_KEY, MSG_MUTED_KEY, MSG_UNMUTED_KEY, MSG_COPIED_KEY,
    EVENT_NEW_MESSAGE, EVENT_MESSAGE_EDITED, EVENT_MESSAGES_DELETED,
    VOICE_NOTE_FILE, MIN_VOICE_SECONDS, MENU_RECORD_KEY, MENU_SEARCH_MESSAGES_KEY,
    MSG_RECORDING_KEY, MSG_RECORDING_CANCELLED_KEY, MSG_RECORDING_TOO_SHORT_KEY,
    MSG_SENDING_VOICE_KEY, MSG_VOICE_SENT_KEY, MSG_PLAYING_KEY, MSG_PLAYBACK_STOPPED_KEY,
    MSG_SEARCH_MESSAGES_PROMPT_KEY, MSG_SEARCH_RESULTS_FORMAT_KEY, MSG_SEARCH_NO_RESULTS_KEY,
    MSG_SEARCH_CLOSED_KEY, ERR_AUDIO_KEY, ERR_NO_AUDIO_SUPPORT_KEY, MEDIA_VOICE,
    MESSAGES_LIMIT, MSG_LOAD_OLDER_KEY, MSG_DOWNLOADING_KEY,
    DOWNLOADABLE_MEDIA, SAFE_OPEN_EXTENSIONS, DIALOGS_LIMIT, SNIPPET_LENGTH,
    MSG_LOAD_MORE_DIALOGS_KEY, MENU_MESSAGE_KEY, MENU_REPLY_KEY, REPLY_LABEL_FORMAT_KEY,
    REPLY_PREFIX_FORMAT_KEY, MSG_REPLY_CANCELLED_KEY, ANNOUNCE_FORMAT_KEY,
    MENU_EDIT_KEY, MENU_DELETE_KEY, MENU_SEND_FILE_KEY, MENU_SEARCH_KEY, MENU_FIND_KEY,
    MENU_FIND_NEXT_KEY, EDIT_LABEL_KEY, MSG_CANNOT_EDIT_KEY, MSG_CANNOT_DELETE_KEY,
    MSG_CONFIRM_DELETE_KEY, MSG_DELETED_KEY, MSG_CHOOSE_FILE_KEY, MSG_UPLOADING_KEY,
    MSG_FILE_SENT_KEY, MSG_FIND_PROMPT_KEY, MSG_NOT_FOUND_KEY,
    APP_TITLE_KEY, MAIN_TITLE_KEY, DIALOGS_LABEL_KEY, MESSAGES_LABEL_KEY,
    MESSAGE_INPUT_LABEL_KEY, BTN_SEND_MESSAGE_KEY, DIALOG_UNREAD_FORMAT_KEY,
    MESSAGE_FORMAT_KEY, SENDER_YOU_KEY, MSG_NO_TEXT_KEY, MSG_LOADING_KEY,
    STATUS_READY_KEY, TIME_FORMAT, DATE_TIME_FORMAT, SELECT_DELAY_MS,
    MEDIA_FORMAT_KEY, MENU_FILE_KEY, MENU_LOGOUT_KEY, MENU_EXIT_KEY, MSG_CONFIRM_LOGOUT_KEY
)

class MainFrame(wx.Frame):
    def __init__(self, i18n, telegram_manager, settings, on_logout):
        super().__init__(None, title=i18n.get_string(MAIN_TITLE_KEY), size=(900, 600))
        self.i18n = i18n
        self.telegram_manager = telegram_manager
        self.settings = settings
        self.on_logout = on_logout
        # Every loaded chat, and the subset the current view shows in the list.
        self.all_dialogs = []
        self.dialogs = []
        self.views = build_views(i18n, [])
        self.view_index = 0
        self.current_dialog_id = None
        self.select_timer = None
        self.dialogs_limit = DIALOGS_LIMIT
        self.has_more_dialogs = False
        self.reply_to = None
        self.editing = None
        self.find_text = ""
        # Set while the message list shows search results instead of the conversation.
        self.search_query = None
        self.player = audio.Player()
        self.recorder = audio.Recorder()
        self.recording_dialog_id = None
        # (dialog id, message id) -> path, so replaying a voice note does not download it again.
        self.downloaded = {}
        self.messages = []
        self.has_older = False
        # True while older messages or a media file are being fetched.
        self.is_busy = False
        self.init_ui()
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.telegram_manager.set_message_listener(
            lambda *args: wx.CallAfter(self.on_telegram_event, *args)
        )
        self.load_dialogs()
        self.telegram_manager.load_folders(self.on_ui_thread(self.show_folders))

    def init_ui(self):
        self.panel = wx.Panel(self)
        hbox = wx.BoxSizer(wx.HORIZONTAL)

        dialogs_box = wx.BoxSizer(wx.VERTICAL)
        view_label = wx.StaticText(self.panel, label=self.i18n.get_string(VIEW_LABEL_KEY))
        dialogs_box.Add(view_label, flag=wx.BOTTOM, border=5)
        self.view_choice = wx.Choice(self.panel, choices=[view.label for view in self.views])
        self.view_choice.SetSelection(self.view_index)
        self.view_choice.Bind(wx.EVT_CHOICE, self.on_view_changed)
        dialogs_box.Add(self.view_choice, flag=wx.EXPAND|wx.BOTTOM, border=10)
        dialogs_label = wx.StaticText(self.panel, label=self.i18n.get_string(DIALOGS_LABEL_KEY))
        dialogs_box.Add(dialogs_label, flag=wx.BOTTOM, border=5)
        self.dialogs_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        self.dialogs_list.Bind(wx.EVT_LISTBOX, self.on_select_dialog)
        self.dialogs_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_open_dialog)
        self.dialogs_list.Bind(wx.EVT_CONTEXT_MENU, self.on_dialog_context_menu)
        # Enter never reaches the list as a key event inside a panel, so catch it here.
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        dialogs_box.Add(self.dialogs_list, proportion=1, flag=wx.EXPAND)
        hbox.Add(dialogs_box, proportion=1, flag=wx.EXPAND|wx.ALL, border=15)

        chat_box = wx.BoxSizer(wx.VERTICAL)
        messages_label = wx.StaticText(self.panel, label=self.i18n.get_string(MESSAGES_LABEL_KEY))
        chat_box.Add(messages_label, flag=wx.BOTTOM, border=5)
        self.messages_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        self.messages_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_activate_message)
        self.messages_list.Bind(wx.EVT_CONTEXT_MENU, self.on_message_context_menu)
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
        settings_item = file_menu.Append(wx.ID_PREFERENCES, self.i18n.get_string(MENU_SETTINGS_KEY))
        self.Bind(wx.EVT_MENU, self.on_settings_menu, settings_item)
        logout_item = file_menu.Append(wx.ID_ANY, self.i18n.get_string(MENU_LOGOUT_KEY))
        self.Bind(wx.EVT_MENU, self.on_logout_menu, logout_item)
        file_menu.AppendSeparator()
        exit_item = file_menu.Append(wx.ID_EXIT, self.i18n.get_string(MENU_EXIT_KEY))
        self.Bind(wx.EVT_MENU, lambda event: self.Close(), exit_item)

        message_menu = wx.Menu()
        for label_key, handler in (
            (MENU_REPLY_KEY, self.on_reply_menu),
            (MENU_EDIT_KEY, self.on_edit_menu),
            (MENU_DELETE_KEY, self.on_delete_menu),
            (MENU_SEND_FILE_KEY, self.on_send_file_menu),
            (MENU_PIN_KEY, self.on_pin_menu),
            (MENU_FORWARD_KEY, self.on_forward_menu),
            (MENU_RECORD_KEY, self.on_record_menu),
        ):
            item = message_menu.Append(wx.ID_ANY, self.i18n.get_string(label_key))
            self.Bind(wx.EVT_MENU, handler, item)

        search_menu = wx.Menu()
        for label_key, handler in (
            (MENU_FIND_KEY, self.on_find_menu),
            (MENU_FIND_NEXT_KEY, self.on_find_next_menu),
            (MENU_SEARCH_MESSAGES_KEY, self.on_search_messages_menu),
        ):
            item = search_menu.Append(wx.ID_ANY, self.i18n.get_string(label_key))
            self.Bind(wx.EVT_MENU, handler, item)

        chats_menu = wx.Menu()
        for label_key, handler in (
            (MENU_NEW_CHAT_KEY, self.on_new_chat_menu),
            (MENU_FIND_CHAT_KEY, self.on_find_chat_menu),
        ):
            item = chats_menu.Append(wx.ID_ANY, self.i18n.get_string(label_key))
            self.Bind(wx.EVT_MENU, handler, item)

        menu_bar = wx.MenuBar()
        menu_bar.Append(file_menu, self.i18n.get_string(MENU_FILE_KEY))
        menu_bar.Append(chats_menu, self.i18n.get_string(MENU_CHATS_KEY))
        menu_bar.Append(message_menu, self.i18n.get_string(MENU_MESSAGE_KEY))
        menu_bar.Append(search_menu, self.i18n.get_string(MENU_SEARCH_KEY))
        self.SetMenuBar(menu_bar)

    def on_settings_menu(self, event):
        with SettingsDialog(self, self.i18n, self.settings, self.telegram_manager) as settings_dialog:
            if settings_dialog.ShowModal() != wx.ID_OK:
                return
            settings_dialog.apply_app_settings()
            profile = settings_dialog.changed_profile()
            privacy = settings_dialog.changed_privacy()
        if privacy:
            self.telegram_manager.save_privacy(
                privacy, self.on_ui_thread(lambda result: self.notify(MSG_PRIVACY_SAVED_KEY))
            )
        if profile is None:
            if privacy:
                return
            self.notify(MSG_SETTINGS_SAVED_KEY)
        elif not profile["first_name"]:
            # Telegram rejects an empty first name; say so instead of a vague failure.
            self.show_error(ERR_FIRST_NAME_REQUIRED_KEY)
        else:
            self.telegram_manager.save_profile(
                profile, self.on_ui_thread(lambda result: self.notify(MSG_PROFILE_SAVED_KEY))
            )

    def select_item_under_mouse(self, list_box, event):
        """A right click does not select by itself; keyboard menu keys report no position."""
        position = event.GetPosition()
        if position != wx.DefaultPosition:
            index = list_box.HitTest(list_box.ScreenToClient(position))
            if index != wx.NOT_FOUND:
                list_box.SetSelection(index)

    def show_context_menu(self, entries):
        menu = wx.Menu()
        for label_key, handler in entries:
            item = menu.Append(wx.ID_ANY, self.i18n.get_string(label_key))
            # Bound to the menu, not the frame, so the handlers go away with it.
            menu.Bind(wx.EVT_MENU, handler, item)
        if entries:
            self.PopupMenu(menu)
        menu.Destroy()

    def selected_dialog(self):
        index = self.dialogs_list.GetSelection()
        if 0 <= index < len(self.dialogs):
            return self.dialogs[index]
        return None

    def on_dialog_context_menu(self, event):
        self.select_item_under_mouse(self.dialogs_list, event)
        dialog = self.selected_dialog()
        if dialog is None:
            return
        entries = [(CONTEXT_OPEN_KEY, self.on_open_dialog)]
        if dialog["unread"]:
            entries.append((CONTEXT_MARK_READ_KEY, lambda event: self.mark_dialog_read(dialog)))
        if dialog["muted"]:
            entries.append((CONTEXT_UNMUTE_KEY, lambda event: self.set_dialog_muted(dialog, False)))
        else:
            entries.append((CONTEXT_MUTE_KEY, lambda event: self.set_dialog_muted(dialog, True)))
        entries.append((CONTEXT_INFO_KEY, lambda event: self.show_chat_info(dialog)))
        self.show_context_menu(entries)

    def show_chat_info(self, dialog):
        with ChatInfoDialog(self, self.i18n, self.telegram_manager, dialog) as info_dialog:
            if info_dialog.ShowModal() != wx.ID_OK:
                return
            new_title = info_dialog.saved_title
        index = self.find_dialog_index(dialog["id"])
        if new_title and index != wx.NOT_FOUND:
            dialog["title"] = new_title
            self.dialogs_list.SetString(index, self.format_dialog(dialog))
        self.notify(MSG_CHAT_SAVED_KEY)

    def mark_dialog_read(self, dialog):
        self.telegram_manager.mark_read(dialog["id"])
        self.set_unread(dialog["id"], 0)
        self.notify(MSG_MARKED_READ_KEY)

    def set_dialog_muted(self, dialog, muted):
        self.telegram_manager.set_muted(
            dialog["id"], muted, self.on_ui_thread(self.on_dialog_muted, dialog, muted)
        )

    def on_dialog_muted(self, result, dialog, muted):
        dialog["muted"] = muted
        self.notify(MSG_MUTED_KEY if muted else MSG_UNMUTED_KEY)

    def on_message_context_menu(self, event):
        self.select_item_under_mouse(self.messages_list, event)
        message = self.selected_message()
        if message is None:
            return
        # Only offer what will actually work on this message.
        entries = [(CONTEXT_REPLY_KEY, self.on_reply_menu), (CONTEXT_FORWARD_KEY, self.on_forward_menu)]
        if message["outgoing"] and message["text"]:
            entries.append((CONTEXT_EDIT_KEY, self.on_edit_menu))
        if self.can_delete(message):
            entries.append((CONTEXT_DELETE_KEY, self.on_delete_menu))
        if self.current_dialog()["can_pin"]:
            pin_key = CONTEXT_UNPIN_KEY if message["pinned"] else CONTEXT_PIN_KEY
            entries.append((pin_key, self.on_pin_menu))
        if message["text"]:
            entries.append((CONTEXT_COPY_KEY, self.on_copy_message))
        if message["media"] in DOWNLOADABLE_MEDIA:
            entries.append((CONTEXT_OPEN_MEDIA_KEY, self.on_activate_message))
        self.show_context_menu(entries)

    def current_dialog(self):
        """The open chat; before any is open, a stand-in with no special rights."""
        return self.find_known_dialog(self.current_dialog_id) or {
            "can_delete_others": False, "can_pin": False, "is_channel": False,
        }

    def can_delete(self, message):
        return message["outgoing"] or self.current_dialog()["can_delete_others"]

    def on_pin_menu(self, event):
        message = self.selected_message()
        if message is None or self.is_busy:
            return
        if not self.current_dialog()["can_pin"]:
            self.notify(MSG_CANNOT_PIN_KEY)
            return
        pinned = not message["pinned"]
        self.is_busy = True
        dialog_id = self.current_dialog_id
        self.telegram_manager.set_pinned(
            dialog_id, message["id"], pinned,
            self.on_ui_thread(self.on_pin_changed, dialog_id, message, pinned)
        )

    def on_pin_changed(self, result, dialog_id, message, pinned):
        self.is_busy = False
        message["pinned"] = pinned
        if dialog_id == self.current_dialog_id and message in self.messages:
            self.render_messages(self.messages_list.GetSelection() - self.message_offset())
        self.notify(MSG_PINNED_KEY if pinned else MSG_UNPINNED_KEY)

    def on_copy_message(self, event):
        message = self.selected_message()
        if message is None or not message["text"] or not wx.TheClipboard.Open():
            return
        wx.TheClipboard.SetData(wx.TextDataObject(message["text"]))
        wx.TheClipboard.Close()
        self.notify(MSG_COPIED_KEY)

    def selected_message(self):
        index = self.messages_list.GetSelection() - self.message_offset()
        if 0 <= index < len(self.messages):
            return self.messages[index]
        return None

    def notify(self, key):
        """Short feedback that needs no dialog: shown in the status bar and spoken."""
        self.announce(self.i18n.get_string(key))

    def announce(self, text):
        self.SetStatusText(text)
        speak(text)

    def on_close(self, event):
        self.player.stop()
        self.recorder.cancel()
        event.Skip()

    def on_record_menu(self, event):
        if not audio.AVAILABLE:
            self.show_error(ERR_NO_AUDIO_SUPPORT_KEY)
        elif self.recorder.is_recording():
            self.finish_recording()
        elif self.current_dialog_id is not None and not self.is_busy:
            self.start_recording()

    def start_recording(self):
        self.stop_playback()
        try:
            self.recorder.start()
        except Exception:
            self.recorder.cancel()
            self.show_error(ERR_AUDIO_KEY)
            return
        # The recording goes to the chat it was started in, even if another is opened meanwhile.
        self.recording_dialog_id = self.current_dialog_id
        self.notify(MSG_RECORDING_KEY)

    def finish_recording(self):
        try:
            os.makedirs(os.path.dirname(VOICE_NOTE_FILE), exist_ok=True)
            seconds = self.recorder.finish(VOICE_NOTE_FILE)
        except Exception:
            self.recorder.cancel()
            self.show_error(ERR_AUDIO_KEY)
            return
        if seconds < MIN_VOICE_SECONDS:
            self.notify(MSG_RECORDING_TOO_SHORT_KEY)
            return
        self.is_busy = True
        self.notify(MSG_SENDING_VOICE_KEY)
        dialog_id = self.recording_dialog_id
        self.telegram_manager.send_file(
            dialog_id, VOICE_NOTE_FILE,
            self.on_ui_thread(self.on_file_sent, dialog_id, MSG_VOICE_SENT_KEY), voice_note=True
        )

    def cancel_recording(self):
        self.recorder.cancel()
        self.notify(MSG_RECORDING_CANCELLED_KEY)

    def play_voice(self, path):
        # Status bar only: speaking here would talk over the start of the recording.
        self.set_status(MSG_PLAYING_KEY)
        self.player.play(
            path, lambda completed, error: wx.CallAfter(self.on_playback_finished, completed, error)
        )

    def on_playback_finished(self, completed, error):
        if not self:
            return
        if error is not None:
            self.show_error(ERR_AUDIO_KEY)
        elif completed:
            self.set_status(STATUS_READY_KEY)

    def stop_playback(self):
        """Returns True if something was playing."""
        if not self.player.is_playing():
            return False
        self.player.stop()
        self.notify(MSG_PLAYBACK_STOPPED_KEY)
        return True

    def on_search_messages_menu(self, event):
        if self.current_dialog_id is None or self.is_busy:
            return
        with wx.TextEntryDialog(
            self, self.i18n.get_string(MSG_SEARCH_MESSAGES_PROMPT_KEY),
            self.i18n.get_string(APP_TITLE_KEY), self.search_query or ""
        ) as search_dialog:
            if search_dialog.ShowModal() != wx.ID_OK:
                return
            query = search_dialog.GetValue().strip()
        if not query:
            return
        self.is_busy = True
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        self.telegram_manager.search_messages(
            dialog_id, query, self.on_ui_thread(self.show_search_results, dialog_id, query)
        )

    def show_search_results(self, results, dialog_id, query):
        self.is_busy = False
        if dialog_id != self.current_dialog_id:
            return
        if not results:
            self.notify(MSG_SEARCH_NO_RESULTS_KEY)
            return
        self.search_query = query
        self.set_compose()
        self.messages = results
        self.has_older = False
        self.render_messages(len(results) - 1)
        self.messages_list.SetFocus()
        self.announce(
            self.i18n.get_string(MSG_SEARCH_RESULTS_FORMAT_KEY).format(count=len(results))
        )

    def close_search(self):
        self.notify(MSG_SEARCH_CLOSED_KEY)
        self.load_messages(focus_messages=True)

    def on_reply_menu(self, event):
        message = self.selected_message()
        if message is not None:
            self.set_compose(reply_to=message)

    def on_edit_menu(self, event):
        message = self.selected_message()
        if message is None:
            return
        if not message["outgoing"] or not message["text"]:
            self.notify(MSG_CANNOT_EDIT_KEY)
            return
        self.set_compose(editing=message)

    def set_compose(self, reply_to=None, editing=None):
        """Choose what the message field does next: reply, edit, or (no arguments) a normal message."""
        was_editing = self.editing is not None
        self.reply_to = reply_to
        self.editing = editing
        if reply_to is not None:
            label = self.i18n.get_string(REPLY_LABEL_FORMAT_KEY).format(
                sender=self.sender_name(reply_to), text=self.message_snippet(reply_to)
            )
        elif editing is not None:
            label = self.i18n.get_string(EDIT_LABEL_KEY)
        else:
            label = self.i18n.get_string(MESSAGE_INPUT_LABEL_KEY)
        # The field's label is what the screen reader reads when it gets focus.
        self.input_label.SetLabel(label)
        self.message_input.SetName(label)
        self.panel.Layout()

        if editing is not None:
            self.message_input.SetValue(editing["text"])
            self.message_input.SetInsertionPointEnd()
        elif was_editing:
            # Leaving edit mode: the field still holds the old message's text.
            self.message_input.Clear()
        if reply_to is not None or editing is not None:
            self.message_input.SetFocus()
            speak(label)

    def on_delete_menu(self, event):
        message = self.selected_message()
        if message is None or self.is_busy:
            return
        if not self.can_delete(message):
            self.notify(MSG_CANNOT_DELETE_KEY)
            return
        if message["outgoing"]:
            question = self.i18n.get_string(MSG_CONFIRM_DELETE_KEY).format(
                text=self.message_snippet(message)
            )
        else:
            # Removing someone else's message is a moderation act: name whose it is.
            question = self.i18n.get_string(MSG_CONFIRM_DELETE_OTHER_KEY).format(
                sender=self.sender_name(message), text=self.message_snippet(message)
            )
        answer = wx.MessageBox(
            question, self.i18n.get_string(APP_TITLE_KEY),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self
        )
        if answer != wx.YES:
            return
        self.is_busy = True
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        self.telegram_manager.delete_message(
            dialog_id, message["id"],
            self.on_ui_thread(self.on_message_deleted, dialog_id, message["id"])
        )

    def on_message_deleted(self, result, dialog_id, message_id):
        self.is_busy = False
        if dialog_id == self.current_dialog_id:
            self.remove_message(message_id)
        self.notify(MSG_DELETED_KEY)

    def remove_message(self, message_id):
        for index, message in enumerate(self.messages):
            if message["id"] == message_id:
                break
        else:
            return
        if self.reply_to is message or self.editing is message:
            self.set_compose()
        del self.messages[index]
        # Re-render rather than delete one row: replies quoting this message change too.
        self.render_messages(min(index, len(self.messages) - 1))

    def on_send_file_menu(self, event):
        if self.current_dialog_id is None or self.is_busy:
            return
        with wx.FileDialog(
            self, self.i18n.get_string(MSG_CHOOSE_FILE_KEY),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_OK:
                return
            path = file_dialog.GetPath()
        self.is_busy = True
        self.set_status(MSG_UPLOADING_KEY)
        dialog_id = self.current_dialog_id
        self.telegram_manager.send_file(
            dialog_id, path, self.on_ui_thread(self.on_file_sent, dialog_id)
        )

    def on_file_sent(self, result, dialog_id, message_key=MSG_FILE_SENT_KEY):
        self.is_busy = False
        self.notify(message_key)
        if dialog_id == self.current_dialog_id:
            self.load_messages()

    def on_find_menu(self, event):
        with wx.TextEntryDialog(
            self, self.i18n.get_string(MSG_FIND_PROMPT_KEY),
            self.i18n.get_string(APP_TITLE_KEY), self.find_text
        ) as find_dialog:
            if find_dialog.ShowModal() != wx.ID_OK:
                return
            self.find_text = find_dialog.GetValue().strip()
        # Start from the current chat itself so a first search can land on it.
        self.find_dialog(self.dialogs_list.GetSelection())

    def on_find_next_menu(self, event):
        if not self.find_text:
            self.on_find_menu(event)
        else:
            self.find_dialog(self.dialogs_list.GetSelection() + 1)

    def find_dialog(self, start):
        """Select the next loaded chat whose title contains the search text, wrapping around."""
        needle = self.find_text.casefold()
        count = len(self.dialogs)
        if not needle or not count:
            return
        for step in range(count):
            index = (max(start, 0) + step) % count
            if needle in self.dialogs[index]["title"].casefold():
                self.dialogs_list.SetSelection(index)
                self.dialogs_list.SetFocus()
                speak(self.format_dialog(self.dialogs[index]))
                return
        self.notify(MSG_NOT_FOUND_KEY)

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
        self.all_dialogs = dialogs
        # A full page means Telegram most likely has more chats after it.
        self.has_more_dialogs = len(dialogs) == self.dialogs_limit
        self.render_dialogs()
        self.set_status(STATUS_READY_KEY)

    def render_dialogs(self):
        """Refill the chat list with the chats of the current view, keeping the user's place."""
        selected = self.dialogs_list.GetSelection()
        was_on_load_more = self.has_more_dialogs and selected == len(self.dialogs)
        first_new_index = len(self.dialogs)
        selected_id = self.dialogs[selected]["id"] if 0 <= selected < len(self.dialogs) else None

        view = self.views[self.view_index]
        self.dialogs = [dialog for dialog in self.all_dialogs if view.matches(dialog)]
        items = [self.format_dialog(dialog) for dialog in self.dialogs]
        if self.has_more_dialogs:
            items.append(self.i18n.get_string(MSG_LOAD_MORE_DIALOGS_KEY))
        self.dialogs_list.Set(items)

        if was_on_load_more and first_new_index < len(self.dialogs):
            # Continue from the first chat that was just added.
            self.dialogs_list.SetSelection(first_new_index)
        elif self.find_dialog_index(selected_id) != wx.NOT_FOUND:
            self.dialogs_list.SetSelection(self.find_dialog_index(selected_id))
        elif items:
            self.dialogs_list.SetSelection(0)

    def show_folders(self, folders):
        self.views = build_views(self.i18n, folders)
        self.view_choice.Set([view.label for view in self.views])
        self.view_choice.SetSelection(self.view_index)

    def on_view_changed(self, event):
        self.view_index = self.view_choice.GetSelection()
        # A different view is a different list: start it from the top.
        self.dialogs_list.SetSelection(wx.NOT_FOUND)
        self.render_dialogs()
        self.announce(self.i18n.get_string(MSG_VIEW_COUNT_FORMAT_KEY).format(
            view=self.views[self.view_index].label, count=len(self.dialogs)
        ))

    def find_known_dialog(self, dialog_id):
        """A chat by id among all loaded chats, including those the current view hides."""
        for dialog in self.all_dialogs:
            if dialog["id"] == dialog_id:
                return dialog
        return None

    def open_chat(self, chat):
        """Show and open a chat that may not be in the list yet (a contact, a looked-up username)."""
        known = self.find_known_dialog(chat["id"])
        if known is None:
            known = chat
            self.all_dialogs.insert(sum(1 for other in self.all_dialogs if other["pinned"]), chat)
        if self.find_dialog_index(known["id"]) == wx.NOT_FOUND:
            if not self.views[self.view_index].matches(known):
                # The current view would hide it: fall back to the view that shows everything.
                self.view_index = 0
                self.view_choice.SetSelection(0)
            self.render_dialogs()
        index = self.find_dialog_index(known["id"])
        if index == wx.NOT_FOUND:
            # Archived chats are in no view but the archive.
            self.view_index = 2
            self.view_choice.SetSelection(2)
            self.render_dialogs()
            index = self.find_dialog_index(known["id"])
        self.dialogs_list.SetSelection(index)
        self.open_selected_dialog(True)

    def on_new_chat_menu(self, event):
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.load_contacts(self.on_ui_thread(self.choose_contact))

    def choose_contact(self, contacts):
        self.set_status(STATUS_READY_KEY)
        if not contacts:
            self.notify(MSG_NO_CONTACTS_KEY)
            return
        chat = self.choose_chat(MSG_CHOOSE_CONTACT_KEY, contacts)
        if chat is not None:
            self.open_chat(chat)

    def choose_chat(self, prompt_key, chats):
        """Let the user pick one chat from a list; None if they cancel."""
        with wx.SingleChoiceDialog(
            self, self.i18n.get_string(prompt_key), self.i18n.get_string(APP_TITLE_KEY),
            [chat["title"] for chat in chats]
        ) as choice_dialog:
            if choice_dialog.ShowModal() != wx.ID_OK:
                return None
            return chats[choice_dialog.GetSelection()]

    def on_find_chat_menu(self, event):
        with wx.TextEntryDialog(
            self, self.i18n.get_string(MSG_FIND_CHAT_PROMPT_KEY), self.i18n.get_string(APP_TITLE_KEY)
        ) as find_dialog:
            if find_dialog.ShowModal() != wx.ID_OK:
                return
            query = find_dialog.GetValue().strip()
        if query:
            self.set_status(MSG_LOADING_KEY)
            self.telegram_manager.find_chat(query, self.on_ui_thread(self.open_chat))

    def on_forward_menu(self, event):
        message = self.selected_message()
        if message is None or not self.all_dialogs:
            return
        target = self.choose_chat(MSG_FORWARD_TO_KEY, self.all_dialogs)
        if target is None:
            return
        self.telegram_manager.forward_message(
            self.current_dialog_id, message["id"], target["id"],
            self.on_ui_thread(lambda result: self.announce(
                self.i18n.get_string(MSG_FORWARDED_FORMAT_KEY).format(title=target["title"])
            ))
        )

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
        elif event.GetKeyCode() != wx.WXK_ESCAPE or not self.on_escape():
            event.Skip()

    def on_escape(self):
        """Back out of the most recent thing in progress; False if there was nothing to cancel."""
        if self.recorder.is_recording():
            self.cancel_recording()
        elif self.stop_playback():
            pass
        elif self.reply_to or self.editing:
            self.set_compose()
            self.notify(MSG_REPLY_CANCELLED_KEY)
        elif self.search_query is not None:
            self.close_search()
        else:
            return False
        return True

    def on_select_dialog(self, event):
        # Wait for the selection to settle so arrowing through the list
        # does not send a request per chat.
        if self.select_timer:
            self.select_timer.Stop()
        if self.settings.get(SETTING_OPEN_ON_SELECT):
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
        self.set_compose()
        self.messages = []
        self.has_older = False
        self.messages_list.Clear()
        self.enable_chat(False)
        self.load_messages(focus_messages)

    def load_messages(self, focus_messages=False):
        self.search_query = None
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        mark_read = self.settings.get(SETTING_MARK_READ_ON_OPEN)
        self.telegram_manager.load_messages(
            dialog_id, self.on_ui_thread(self.show_messages, dialog_id, focus_messages, mark_read),
            mark_read=mark_read
        )

    def show_messages(self, messages, dialog_id, focus_messages, marked_read):
        # The user may have opened another chat while this one was loading.
        if dialog_id != self.current_dialog_id:
            return
        self.messages = messages
        # A full page means Telegram most likely has more before it.
        self.has_older = len(messages) == MESSAGES_LIMIT
        self.render_messages(len(messages) - 1)
        if marked_read:
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
        # Enter while a voice note plays stops it, like a play/stop button.
        if self.stop_playback():
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
        cache_key = (self.current_dialog_id, message["id"])
        cached = self.downloaded.get(cache_key)
        if cached and os.path.exists(cached):
            self.open_media(cached, cache_key, message["media"])
            return
        self.is_busy = True
        self.set_status(MSG_DOWNLOADING_KEY)
        self.telegram_manager.download_media(
            self.current_dialog_id, message["id"],
            self.on_ui_thread(self.open_media, cache_key, message["media"])
        )

    def open_media(self, path, cache_key, media):
        self.is_busy = False
        self.downloaded[cache_key] = path
        self.set_status(STATUS_READY_KEY)
        if media == MEDIA_VOICE and audio.AVAILABLE:
            self.play_voice(path)
        # Only hand known media formats to their default app; anything else
        # could be a program, so just show the folder it was saved in.
        elif os.path.splitext(path)[1].lower() in SAFE_OPEN_EXTENSIONS:
            wx.LaunchDefaultApplication(path)
        else:
            wx.LaunchDefaultApplication(os.path.dirname(path))

    def find_dialog_index(self, dialog_id):
        for index, dialog in enumerate(self.dialogs):
            if dialog["id"] == dialog_id:
                return index
        return wx.NOT_FOUND

    def set_unread(self, dialog_id, count):
        dialog = self.find_known_dialog(dialog_id)
        if dialog is None or dialog["unread"] == count:
            return
        dialog["unread"] = count
        index = self.find_dialog_index(dialog_id)
        # It may be open while the current view does not list it.
        if index != wx.NOT_FOUND:
            self.dialogs_list.SetString(index, self.format_dialog(dialog))

    def on_telegram_event(self, event, *details):
        if not self:
            return
        handlers = {
            EVENT_NEW_MESSAGE: self.on_new_message,
            EVENT_MESSAGE_EDITED: self.on_message_edited,
            EVENT_MESSAGES_DELETED: self.on_messages_deleted,
        }
        handlers[event](*details)

    def on_message_edited(self, dialog_id, message):
        if dialog_id != self.current_dialog_id:
            return
        for index, shown in enumerate(self.messages):
            if shown["id"] == message["id"]:
                self.messages[index] = message
                # Re-render: replies quoting this message show its text too.
                self.render_messages(self.messages_list.GetSelection() - self.message_offset())
                return

    def on_messages_deleted(self, dialog_id, message_ids):
        if dialog_id is None:
            # Telegram does not say which chat. Outside channels message ids are
            # unique across chats, so matching by id is safe there, but only there.
            if self.current_dialog_id is None or self.current_dialog()["is_channel"]:
                return
        elif dialog_id != self.current_dialog_id:
            return
        for message_id in message_ids:
            self.remove_message(message_id)

    def on_new_message(self, chat, message):
        dialog_id = chat["id"]
        index = self.find_dialog_index(dialog_id)
        # Prefer the chat as already loaded: it knows its unread count and mute state.
        dialog = self.find_known_dialog(dialog_id) or chat

        is_current = dialog_id == self.current_dialog_id
        if not message["outgoing"] and not dialog["muted"]:
            if self.settings.get(SETTING_PLAY_SOUND) and not (is_current and self.IsActive()):
                wx.Bell()
            if self.settings.get(SETTING_ANNOUNCE_MESSAGES):
                # In the open chat the sender is what matters; elsewhere, which chat it came from.
                speak(self.i18n.get_string(ANNOUNCE_FORMAT_KEY).format(
                    source=message["sender"] if is_current else dialog["title"],
                    text=self.message_snippet(message)
                ))

        reads_it = is_current and self.settings.get(SETTING_MARK_READ_ON_OPEN)
        if is_current:
            self.append_message(message)
        if not message["outgoing"]:
            if reads_it:
                self.telegram_manager.mark_read(dialog_id)
            else:
                dialog["unread"] += 1
        self.move_dialog_to_top(index, dialog)

    def append_message(self, message):
        # Search results are a fixed list; the message shows up once the search is closed.
        if self.search_query is not None:
            return
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
        # First in the full list, which also holds the chats the current view hides.
        if not dialog["pinned"]:
            if dialog in self.all_dialogs:
                self.all_dialogs.remove(dialog)
            self.all_dialogs.insert(sum(1 for other in self.all_dialogs if other["pinned"]), dialog)
        if not self.views[self.view_index].matches(dialog):
            if index != wx.NOT_FOUND:
                # E.g. it was just read while the "unread" view is showing: leave it in place.
                self.dialogs_list.SetString(index, self.format_dialog(dialog))
            return
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
        if message["pinned"]:
            text = self.i18n.get_string(PINNED_FORMAT_KEY).format(text=text)
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
        on_result = self.on_ui_thread(self.on_message_sent, dialog_id)
        if self.editing is not None:
            self.telegram_manager.edit_message(dialog_id, self.editing["id"], text, on_result)
        else:
            self.telegram_manager.send_message(
                dialog_id, text, on_result,
                reply_to=self.reply_to["id"] if self.reply_to else None
            )

    def on_message_sent(self, result, dialog_id):
        if dialog_id != self.current_dialog_id:
            return
        self.set_compose()
        # Re-enable before focusing: a disabled field cannot take focus.
        self.enable_chat(True)
        self.message_input.Clear()
        self.load_messages()
        self.message_input.SetFocus()
