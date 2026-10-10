import wx
from core import audio
from core.speech import speak
from core.settings import SETTING_KEEP_IN_BACKGROUND
from ui.settings_dialog import SettingsDialog
from core.chat_views import build_views
from ui.text_dialog import TextDialog
from core.constants import (
    MENU_READ_MESSAGE_KEY, MENU_HELP_KEY, MENU_SHORTCUTS_KEY, SHORTCUTS_TITLE_KEY, SHORTCUTS_TEXT_KEY,
    MENU_MARK_KEY, MENU_UNMARK_ALL_KEY, MENU_NEW_GROUP_KEY, MENU_NEW_CHANNEL_KEY, MESSAGE_VIEWS,
    MENU_CHAT_VIEWS_KEY, MENU_NEW_POLL_KEY, MENU_REACT_KEY, MENU_SCHEDULE_KEY,
    MSG_IN_BACKGROUND_FORMAT_KEY, SHOW_HOTKEY_TEXT, ICON_FILE, BTN_RECORD_KEY,
    BTN_CANCEL_RECORDING_KEY, MSG_CANNOT_WRITE_KEY, MENU_ABOUT_KEY, ABOUT_FORMAT_KEY,
    APP_NAME, APP_VERSION, DEVELOPER_NAME_KEY,
    VIEW_LABEL_KEY, MSG_PRIVACY_SAVED_KEY, MENU_CHATS_KEY, MENU_NEW_CHAT_KEY, MENU_FIND_CHAT_KEY,
    MENU_FORWARD_KEY, MENU_PIN_KEY, MENU_SETTINGS_KEY, MSG_SETTINGS_SAVED_KEY,
    MSG_PROFILE_SAVED_KEY, ERR_FIRST_NAME_REQUIRED_KEY, MENU_RECORD_KEY, MENU_SEARCH_MESSAGES_KEY,
    DIALOGS_LIMIT, MENU_MESSAGE_KEY, MENU_REPLY_KEY, MSG_REPLY_CANCELLED_KEY, MENU_EDIT_KEY,
    MENU_DELETE_KEY, MENU_SEND_FILE_KEY, MENU_SEARCH_KEY, MENU_FIND_KEY, MENU_FIND_NEXT_KEY,
    APP_TITLE_KEY, MAIN_TITLE_KEY, DIALOGS_LABEL_KEY, MESSAGES_LABEL_KEY, MESSAGE_INPUT_LABEL_KEY,
    BTN_SEND_MESSAGE_KEY, STATUS_READY_KEY, MENU_FILE_KEY, MENU_LOGOUT_KEY, MENU_EXIT_KEY,
    MSG_CONFIRM_LOGOUT_KEY
)
from ui.chat_list import ChatListMixin
from ui.message_list import MessageListMixin
from ui.composer import ComposerMixin
from ui.message_actions import MessageActionsMixin
from ui.voice import VoiceMixin
from ui.live_updates import LiveUpdatesMixin

class MainFrame(
    ChatListMixin, MessageListMixin, ComposerMixin, MessageActionsMixin,
    VoiceMixin, LiveUpdatesMixin, wx.Frame
):
    """The main window: builds the widgets and menus, holds the state every part
    shares, and offers the helpers the mixins rely on (status, errors, results)."""

    def __init__(self, i18n, telegram_manager, settings, on_logout, on_quit=None):
        super().__init__(None, title=i18n.get_string(MAIN_TITLE_KEY), size=(900, 600))
        self.SetIcon(wx.Icon(ICON_FILE))
        self.i18n = i18n
        self.telegram_manager = telegram_manager
        self.settings = settings
        self.on_logout = on_logout
        # Called to end the whole program; without it, closing this window is all there is.
        self.on_quit = on_quit
        self.is_quitting = False
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
        # chat id -> text typed there but not sent; kept only while the app is open.
        self.drafts = {}
        self.find_text = ""
        # Set while the message list shows search results instead of the conversation.
        self.search_query = None
        # None for the conversation itself, otherwise which MESSAGE_VIEW_* list is showing.
        self.message_view = None
        self.player = audio.Player()
        self.recorder = audio.Recorder()
        self.recording_dialog_id = None
        # (dialog id, message id) -> path, so replaying a voice note does not download it again.
        self.downloaded = {}
        self.messages = []
        # Ids of the messages marked for a group action (delete, forward, copy).
        self.marked = set()
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
        input_box.Add(self.send_btn, flag=wx.RIGHT, border=10)
        # One button starts the recording and, renamed while it runs, stops and sends it.
        self.record_btn = wx.Button(self.panel, label=self.i18n.get_string(BTN_RECORD_KEY))
        self.record_btn.Bind(wx.EVT_BUTTON, self.on_record_menu)
        input_box.Add(self.record_btn)
        self.cancel_record_btn = wx.Button(self.panel, label=self.i18n.get_string(BTN_CANCEL_RECORDING_KEY))
        self.cancel_record_btn.Bind(wx.EVT_BUTTON, lambda event: self.cancel_recording())
        self.cancel_record_btn.Hide()
        input_box.Add(self.cancel_record_btn, flag=wx.LEFT, border=10)
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
        self.Bind(wx.EVT_MENU, self.on_exit_menu, exit_item)

        message_menu = wx.Menu()
        for label_key, handler in (
            (MENU_REPLY_KEY, self.on_reply_menu),
            (MENU_EDIT_KEY, self.on_edit_menu),
            (MENU_DELETE_KEY, self.on_delete_menu),
            (MENU_SEND_FILE_KEY, self.on_send_file_menu),
            (MENU_PIN_KEY, self.on_pin_menu),
            (MENU_FORWARD_KEY, self.on_forward_menu),
            (MENU_READ_MESSAGE_KEY, self.on_read_message_menu),
            (MENU_MARK_KEY, self.on_mark_menu),
            (MENU_UNMARK_ALL_KEY, self.on_unmark_all_menu),
            (MENU_REACT_KEY, self.on_react_menu),
            (MENU_SCHEDULE_KEY, self.on_schedule_menu),
            (MENU_NEW_POLL_KEY, self.on_new_poll_menu),
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
            (MENU_NEW_GROUP_KEY, lambda event: self.create_chat(is_channel=False)),
            (MENU_NEW_CHANNEL_KEY, lambda event: self.create_chat(is_channel=True)),
        ):
            item = chats_menu.Append(wx.ID_ANY, self.i18n.get_string(label_key))
            self.Bind(wx.EVT_MENU, handler, item)

        views_menu = wx.Menu()
        for view in MESSAGE_VIEWS:
            item = views_menu.Append(wx.ID_ANY, self.i18n.get_string(view))
            self.Bind(wx.EVT_MENU, lambda event, view=view: self.open_message_view(view), item)

        menu_bar = wx.MenuBar()
        menu_bar.Append(file_menu, self.i18n.get_string(MENU_FILE_KEY))
        menu_bar.Append(chats_menu, self.i18n.get_string(MENU_CHATS_KEY))
        menu_bar.Append(views_menu, self.i18n.get_string(MENU_CHAT_VIEWS_KEY))
        menu_bar.Append(message_menu, self.i18n.get_string(MENU_MESSAGE_KEY))
        menu_bar.Append(search_menu, self.i18n.get_string(MENU_SEARCH_KEY))
        help_menu = wx.Menu()
        shortcuts_item = help_menu.Append(wx.ID_HELP, self.i18n.get_string(MENU_SHORTCUTS_KEY))
        self.Bind(wx.EVT_MENU, self.on_shortcuts_menu, shortcuts_item)
        about_item = help_menu.Append(wx.ID_ABOUT, self.i18n.get_string(MENU_ABOUT_KEY))
        self.Bind(wx.EVT_MENU, self.on_about_menu, about_item)
        menu_bar.Append(help_menu, self.i18n.get_string(MENU_HELP_KEY))
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

    def show_text(self, title_key, text):
        with TextDialog(self, self.i18n, self.i18n.get_string(title_key), text) as text_dialog:
            text_dialog.ShowModal()

    def on_shortcuts_menu(self, event):
        self.show_text(SHORTCUTS_TITLE_KEY, self.i18n.get_string(SHORTCUTS_TEXT_KEY))

    def on_about_menu(self, event):
        wx.MessageBox(
            self.i18n.get_string(ABOUT_FORMAT_KEY).format(
                name=APP_NAME, version=APP_VERSION, developer=self.i18n.get_string(DEVELOPER_NAME_KEY)
            ),
            self.i18n.get_string(APP_TITLE_KEY), wx.OK | wx.ICON_INFORMATION, self
        )

    def select_item_under_mouse(self, list_box, event):
        """A right click does not select by itself; keyboard menu keys report no position."""
        position = event.GetPosition()
        if position != wx.DefaultPosition:
            index = list_box.HitTest(list_box.ScreenToClient(position))
            if index != wx.NOT_FOUND:
                list_box.SetSelection(index)

    def build_menu(self, entries):
        """A menu from (label key, handler) pairs; a list in place of the handler makes a submenu."""
        menu = wx.Menu()
        for label_key, handler in entries:
            label = self.i18n.get_string(label_key)
            if isinstance(handler, list):
                menu.AppendSubMenu(self.build_menu(handler), label)
            else:
                item = menu.Append(wx.ID_ANY, label)
                # Bound to the menu, not the frame, so the handlers go away with it.
                menu.Bind(wx.EVT_MENU, handler, item)
        return menu

    def show_context_menu(self, entries):
        menu = self.build_menu(entries)
        if entries:
            self.PopupMenu(menu)
        menu.Destroy()

    def notify(self, key):
        """Short feedback that needs no dialog: shown in the status bar and spoken."""
        self.announce(self.i18n.get_string(key))

    def announce(self, text):
        self.SetStatusText(text)
        speak(text)

    def on_close(self, event):
        # Closing the window only hides it, so messages keep arriving; a real
        # exit (the Exit menu, logging out, Windows shutting down) cannot be vetoed.
        if event.CanVeto() and not self.is_quitting and self.settings.get(SETTING_KEEP_IN_BACKGROUND):
            event.Veto()
            self.recorder.cancel()
            self.update_record_buttons()
            self.Hide()
            speak(self.i18n.get_string(MSG_IN_BACKGROUND_FORMAT_KEY).format(hotkey=SHOW_HOTKEY_TEXT))
            return
        self.player.stop()
        self.recorder.cancel()
        event.Skip()
        # With the last window gone nothing would end the hidden background part.
        if not self.is_quitting and self.on_quit is not None:
            wx.CallAfter(self.on_quit)

    def quit(self):
        """Close for real, whatever the background setting says."""
        self.is_quitting = True
        self.Close()

    def on_exit_menu(self, event):
        if self.on_quit is not None:
            self.on_quit()
        else:
            self.quit()

    def bring_forward(self):
        """Show the window again after it was hidden or minimized."""
        self.Show()
        self.Iconize(False)
        self.Raise()
        self.on_brought_forward()

    def on_logout_menu(self, event):
        answer = wx.MessageBox(
            self.i18n.get_string(MSG_CONFIRM_LOGOUT_KEY), self.i18n.get_string(APP_TITLE_KEY),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self
        )
        if answer == wx.YES:
            self.on_logout()

    def enable_chat(self, enabled):
        """Unlock the writing controls, as far as the open chat lets this account write."""
        can_send = self.current_dialog().get("can_send", True)
        usable = enabled and can_send
        self.message_input.Enable(usable)
        self.send_btn.Enable(usable)
        self.record_btn.Enable(usable and audio.AVAILABLE)
        if not self.reply_to and not self.editing:
            # In a channel that only its admins post to, say why the field is locked.
            read_only = self.current_dialog_id is not None and not can_send
            label = self.i18n.get_string(MSG_CANNOT_WRITE_KEY if read_only else MESSAGE_INPUT_LABEL_KEY)
            self.input_label.SetLabel(label)
            self.message_input.SetName(label)

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
        elif self.clear_marks():
            pass
        elif self.message_view is not None:
            self.close_search()
        else:
            return False
        return True
