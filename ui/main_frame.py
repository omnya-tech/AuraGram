import wx
from core import audio, shortcuts, sounds, speech
from core.speech import speak
from core.settings import (
    FEEDBACK_SETTINGS, SETTING_FAVORITES, SETTING_KEEP_IN_BACKGROUND, SETTING_LARGE_TEXT, SETTING_THEME,
    SETTING_SPEAK_FEEDBACK, SETTING_SIMPLE_TAB, SETTING_SHOW_PREVIEW, SETTING_ENTER_SENDS,
    SETTING_SOUND_VOLUME,
)
from ui.themes import apply_theme, set_theme
from ui.layout import OptionalButton, ReadOnlyText, ViewTabs, is_on_a_screen, prepare_window, reading_font
from ui.type_ahead import TypeAhead
from ui.settings_dialog import SettingsDialog
from core.chat_views import build_views
from ui.text_dialog import TextDialog
from core.constants import (
    FEEDBACK_CONFIRM, MSG_IN_BACKGROUND_FORMAT_KEY, MSG_IN_BACKGROUND_KEY, BTN_RECORD_KEY, MAIN_WINDOW_SIZE,
    ERR_HOTKEY_TAKEN_FORMAT_KEY, MAIN_WINDOW_MIN_SIZE, PREVIEW_HEIGHT, PREVIEW_LABEL_KEY,
    MAIN_TITLE_CHAT_FORMAT_KEY, MESSAGES_OF_LABEL_FORMAT_KEY, TOOLTIP_SEND_KEY, TOOLTIP_RECORD_KEY,
    TOOLTIP_VIEW_KEY, BTN_CANCEL_RECORDING_KEY, MSG_CANNOT_WRITE_KEY, VIEW_LABEL_KEY, MSG_PRIVACY_SAVED_KEY,
    MENU_FIND_CHAT_KEY, MSG_SETTINGS_SAVED_KEY, MSG_PROFILE_SAVED_KEY, ERR_FIRST_NAME_REQUIRED_KEY,
    DIALOGS_LIMIT, MSG_REPLY_CANCELLED_KEY, MENU_FIND_KEY, APP_TITLE_KEY, MAIN_TITLE_KEY, DIALOGS_LABEL_KEY,
    MESSAGES_LABEL_KEY, MESSAGE_INPUT_LABEL_KEY, BTN_SEND_MESSAGE_KEY, STATUS_READY_KEY,
    MESSAGES_OF_LABEL_STATUS_FORMAT_KEY, STATUS_LAST_SEEN_FORMAT_KEY, MENU_GLOBAL_SEARCH_KEY,
    MESSAGE_VIEW_COMMENTS, BTN_ATTACH_KEY, TOOLTIP_ATTACH_KEY, PROGRESS_LABEL_KEY, MSG_CHAT_CLOSED_KEY,
    MESSAGE_VIEW_TOPIC, GENERAL_TOPIC_ID, BTN_SEARCH_KEY, TOOLTIP_SEARCH_CHATS_KEY,
    TOOLTIP_SEARCH_MESSAGES_KEY, BTN_BACK_KEY, TOOLTIP_BACK_KEY, MENU_SEARCH_ALL_KEY, MESSAGE_INPUT_HEIGHT,
    SOUND_VOLUMES,
)
from ui.chat_list import ChatListMixin
from ui.message_list import MessageListMixin
from ui.composer import ComposerMixin
from ui.message_actions import MessageActionsMixin
from ui.voice import VoiceMixin
from ui.live_updates import LiveUpdatesMixin
from ui.downloads import DownloadsMixin
from ui.chat_extras import ChatExtrasMixin
from ui.reminders import RemindersMixin
from ui.mouse_bars import MouseBarsMixin
from ui.menu_bar import MenuBarMixin
from ui.help_menu import HelpMenuMixin
from ui.file_menu import FileMenuMixin


class MainFrame(
    ChatListMixin, MessageListMixin, ComposerMixin, MessageActionsMixin,
    VoiceMixin, LiveUpdatesMixin, DownloadsMixin, ChatExtrasMixin, RemindersMixin,
    MouseBarsMixin, MenuBarMixin, HelpMenuMixin, FileMenuMixin, wx.Frame
):
    """The main window: builds the widgets and menus, holds the state every part
    shares, and offers the helpers the mixins rely on (status, errors, results)."""

    def __init__(self, i18n, telegram_manager, settings, on_logout, on_quit=None, on_hotkey_changed=None,
                 on_switch_account=None):
        super().__init__(None, title=i18n.get_string(MAIN_TITLE_KEY), size=MAIN_WINDOW_SIZE)
        prepare_window(self, i18n)
        self.SetMinSize(MAIN_WINDOW_MIN_SIZE)
        self.i18n = i18n
        self.telegram_manager = telegram_manager
        self.settings = settings
        self.on_logout = on_logout
        # Called to end the whole program; without it, closing this window is all there is.
        self.on_quit = on_quit
        # Called with the shortcut that brings the window back from any program, when the user
        # changes it; answers whether Windows gave it. Without it, nothing listens for that shortcut.
        self.on_hotkey_changed = on_hotkey_changed
        # Called with an account's id, or None for a new one, to go to it; without it there is one account.
        self.on_switch_account = on_switch_account
        self.is_quitting = False
        # Menu command -> its entry in the menu bar, and every shortcut those entries answer to.
        self.menu_items = {}
        self.menu_shortcuts = set()
        # Shortcut -> handler, for the commands of the message's and the writing field's menus, which have
        # no place in the menu bar.
        self.menu_less_shortcuts = {}
        # Set once "@name words" turned out to be no inline bot, so Enter sends it as typed.
        self.inline_checked = False
        # Bot chat id -> what a start link said to start it with, until it is started.
        self.bot_start_params = {}
        # Files from outside the app, waiting for the chat list to load before asking where they go.
        self.shared_paths = []
        # Whether this run has already looked for shortcuts that other programs hold.
        self.shortcuts_checked = False
        # Every loaded chat, and the subset the current view shows in the list.
        self.all_dialogs = []
        self.dialogs = []
        # The ids of the chats put among the favourites; the same set the Favourites view looks into.
        self.favorites = set(settings.get(SETTING_FAVORITES))
        self.views = build_views(i18n, [], self.favorites)
        # Every remark of the app, here or in its windows, asks the settings first.
        speech.set_feedback_rule(self.feedback_wanted)
        # The account's contacts, as last loaded for the view that lists them.
        self.contacts = []
        self.view_index = 0
        self.current_dialog_id = None
        # Whether the window shows the one chat that was entered, rather than the list of chats.
        self.in_chat = False
        # How many unread messages the chat being entered had, and the first of them once loaded.
        self.unread_on_open = 0
        self.first_unread_id = None
        # A message to go to once the chat being opened has loaded.
        self.pending_jump = None
        self.typing_timer = None
        # Every "typing", "recording" text shown so far, to tell them from other news on the status bar.
        self.typing_texts = set()
        self.dialogs_limit = DIALOGS_LIMIT
        self.has_more_dialogs = False
        # While more of the chat list is being fetched: how many chats there were before; None otherwise.
        self.loading_more_from = None
        self.reply_to = None
        self.editing = None
        # chat id -> text typed there but not sent; kept only while the app is open.
        self.drafts = {}
        self.find_text = ""
        # Set while the message list shows search results instead of the conversation.
        self.search_query = None
        # None for the conversation itself, otherwise which MESSAGE_VIEW_* list is showing.
        self.message_view = None
        # Set while the message area shows comments or a topic: {"view", "id", "title"}.
        self.thread = None
        self.player = audio.Player()
        self.recorder = audio.Recorder()
        self.recording_dialog_id = None
        self.recording_target = (None, None)
        # (dialog id, message id) -> path, so replaying a voice note does not download it again.
        self.downloaded = {}
        self.messages = []
        # Ids of the messages marked for a group action (delete, forward, copy).
        self.marked = set()
        self.has_older = False
        # True while older messages, a search or a sound are being fetched: what the list waits for.
        self.is_busy = False
        # Files coming down beside everything else, which hold nothing up while they come, and
        # (chat, message) of each, so the same one is not asked for twice at once.
        self.transfers = 0
        self.downloading = set()
        # (dialog id, message id) -> what Gemini said of that picture, so asking twice costs once.
        self.descriptions = {}
        # Whether this run has already looked for a newer release by itself.
        self.updates_checked = False
        # True while a newer release is coming down, and how far it has come.
        self.update_downloading = False
        self.update_percent = None
        # Files going up to a chat: {"dialog_id", "names", "text"}; None while nothing is.
        self.upload = None
        sounds.set_volume(SOUND_VOLUMES[settings.get(SETTING_SOUND_VOLUME)])
        self.init_downloads()
        # The request handing a sound to the player as it arrives, to cancel when the listening stops.
        self.stream_request = None
        # chat id -> what someone there is doing ("typing", "recording"), shown on its row for a while.
        self.typing_in = {}
        # The search window while its results are being looked through, and the result opened from it.
        self.global_search = None
        self.search_result_id = None
        self.typing_row_timers = {}
        self.init_ui()
        self.init_reminders()
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.telegram_manager.set_message_listener(
            lambda *args: wx.CallAfter(self.on_telegram_event, *args)
        )
        self.load_dialogs()
        self.telegram_manager.load_folders(self.on_ui_thread(self.show_folders))

    def init_ui(self):
        self.panel = wx.Panel(self)
        # The buttons of the rows for the mouse, on both screens.
        self.mouse_buttons = []
        # Two screens share the window, one at a time: the list of chats, and the chat that was entered.
        hbox = self.screens = wx.BoxSizer(wx.HORIZONTAL)

        dialogs_box = self.dialogs_box = wx.BoxSizer(wx.VERTICAL)
        view_label = wx.StaticText(self.panel, label=self.i18n.get_string(VIEW_LABEL_KEY))
        dialogs_box.Add(view_label, flag=wx.BOTTOM, border=5)
        # Every view in sight, as tabs: a drop-down would show only the one that is on.
        self.view_tabs = ViewTabs(
            self.panel, [view.label for view in self.views], lambda: self.on_view_changed(None),
            self.i18n.get_string(TOOLTIP_VIEW_KEY)
        )
        self.view_tabs.SetName(self.i18n.get_string(VIEW_LABEL_KEY))
        dialogs_box.Add(self.view_tabs, flag=wx.EXPAND|wx.BOTTOM, border=6)
        dialogs_label = wx.StaticText(self.panel, label=self.i18n.get_string(DIALOGS_LABEL_KEY))
        dialogs_box.Add(dialogs_label, flag=wx.BOTTOM, border=5)
        self.dialogs_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        # A chat is found by its name, whatever its row says before it.
        self.dialogs_type_ahead = TypeAhead(self.dialogs_list, lambda index: self.dialogs[index]["title"])
        self.dialogs_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_open_dialog)
        self.dialogs_list.Bind(wx.EVT_CONTEXT_MENU, self.on_dialog_context_menu)
        # Enter never reaches the list as a key event inside a panel, so catch it here.
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        dialogs_box.Add(self.dialogs_list, proportion=1, flag=wx.EXPAND)
        self.list_search_btn = wx.Button(self.panel, label=self.i18n.get_string(BTN_SEARCH_KEY))
        self.list_search_btn.Bind(wx.EVT_BUTTON, self.on_search_chats)
        self.list_search_btn.SetToolTip(self.i18n.get_string(TOOLTIP_SEARCH_CHATS_KEY))
        dialogs_box.Add(
            self.build_mouse_bar(self.list_bar_entries(), first=(self.list_search_btn,)), flag=wx.EXPAND|wx.TOP, border=10
        )
        hbox.Add(dialogs_box, proportion=1, flag=wx.EXPAND|wx.ALL, border=15)

        chat_box = self.chat_box = wx.BoxSizer(wx.VERTICAL)
        self.messages_label = wx.StaticText(self.panel, label=self.i18n.get_string(MESSAGES_LABEL_KEY))
        chat_box.Add(self.messages_label, flag=wx.BOTTOM, border=5)
        self.messages_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        self.messages_type_ahead = TypeAhead(self.messages_list)
        self.messages_list.Bind(wx.EVT_LISTBOX, lambda event: self.update_preview())
        self.messages_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_activate_message)
        self.messages_list.Bind(wx.EVT_CONTEXT_MENU, self.on_message_context_menu)
        chat_box.Add(self.messages_list, proportion=1, flag=wx.EXPAND|wx.BOTTOM, border=10)

        # A list row is one line, so a long message is cut off on screen. This shows
        # the selected message whole, with its line breaks, for reading by eye.
        self.preview_label = wx.StaticText(self.panel, label=self.i18n.get_string(PREVIEW_LABEL_KEY))
        chat_box.Add(self.preview_label, flag=wx.BOTTOM, border=5)
        self.preview_text = ReadOnlyText(self.panel, size=(-1, PREVIEW_HEIGHT))
        chat_box.Add(self.preview_text, flag=wx.EXPAND|wx.BOTTOM, border=15)
        chat_box.Add(self.build_mouse_bar(self.chat_bar_entries()), flag=wx.EXPAND|wx.BOTTOM, border=9)

        self.input_label = wx.StaticText(self.panel, label=self.i18n.get_string(MESSAGE_INPUT_LABEL_KEY))
        chat_box.Add(self.input_label, flag=wx.BOTTOM, border=5)
        input_box = wx.BoxSizer(wx.HORIZONTAL)
        # Several lines, so a message can have line breaks; which key sends is decided in on_char_hook.
        self.message_input = wx.TextCtrl(self.panel, style=wx.TE_MULTILINE, size=(-1, MESSAGE_INPUT_HEIGHT))
        self.message_input.Bind(wx.EVT_TEXT, self.on_input_changed)
        # The Applications key or a right click: what can be sent, in place of Windows' own editing menu.
        self.message_input.Bind(wx.EVT_CONTEXT_MENU, self.on_input_context_menu)
        input_box.Add(self.message_input, proportion=1, flag=wx.EXPAND|wx.RIGHT, border=10)
        self.send_btn = OptionalButton(self.panel, label=self.i18n.get_string(BTN_SEND_MESSAGE_KEY))
        self.send_btn.Bind(wx.EVT_BUTTON, self.on_send_message)
        input_box.Add(self.send_btn, flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        # Everything that can go with a message besides its text, in one menu.
        self.attach_btn = wx.Button(self.panel, label=self.i18n.get_string(BTN_ATTACH_KEY))
        self.attach_btn.Bind(wx.EVT_BUTTON, self.on_attach)
        input_box.Add(self.attach_btn, flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        # One button starts the recording and, renamed while it runs, stops and sends it.
        self.record_btn = wx.Button(self.panel, label=self.i18n.get_string(BTN_RECORD_KEY))
        self.record_btn.Bind(wx.EVT_BUTTON, self.on_record_menu)
        input_box.Add(self.record_btn, flag=wx.ALIGN_CENTER_VERTICAL)
        self.cancel_record_btn = wx.Button(self.panel, label=self.i18n.get_string(BTN_CANCEL_RECORDING_KEY))
        self.cancel_record_btn.Bind(wx.EVT_BUTTON, lambda event: self.cancel_recording())
        self.cancel_record_btn.Hide()
        input_box.Add(self.cancel_record_btn, flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        self.search_btn = wx.Button(self.panel, label=self.i18n.get_string(BTN_SEARCH_KEY))
        self.search_btn.Bind(wx.EVT_BUTTON, self.on_search_messages_menu)
        self.search_btn.SetToolTip(self.i18n.get_string(TOOLTIP_SEARCH_MESSAGES_KEY))
        input_box.Add(self.search_btn, flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        # For the mouse: the keyboard has Escape, so Tab need not stop here.
        self.back_btn = OptionalButton(self.panel, label=self.i18n.get_string(BTN_BACK_KEY))
        self.back_btn.Bind(wx.EVT_BUTTON, lambda event: self.close_chat())
        self.back_btn.SetToolTip(self.i18n.get_string(TOOLTIP_BACK_KEY))
        input_box.Add(self.back_btn, flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        chat_box.Add(input_box, flag=wx.EXPAND)
        # Seen only while a file goes up or comes down. A real progress bar, so a screen
        # reader reports it the way it reports any other, with no extra talk from the app.
        self.progress_gauge = wx.Gauge(self.panel, range=100)
        self.progress_gauge.SetName(self.i18n.get_string(PROGRESS_LABEL_KEY))
        self.progress_gauge.Hide()
        chat_box.Add(self.progress_gauge, flag=wx.EXPAND|wx.TOP, border=10)
        hbox.Add(chat_box, proportion=1, flag=wx.EXPAND|wx.ALL, border=15)

        self.send_btn.SetToolTip(self.i18n.get_string(TOOLTIP_SEND_KEY))
        self.record_btn.SetToolTip(self.i18n.get_string(TOOLTIP_RECORD_KEY))
        self.attach_btn.SetToolTip(self.i18n.get_string(TOOLTIP_ATTACH_KEY))

        self.panel.SetSizer(hbox)
        self.init_menu()
        self.CreateStatusBar()
        self.enable_chat(False)
        self.show_chat_screen(False)
        self.apply_text_size()
        self.apply_colours()
        self.restore_placement()
        wx.CallAfter(self.dialogs_list.SetFocus)

    def apply_text_size(self):
        """Use the normal or the larger font, per the setting, wherever text is read at length."""
        font = reading_font(self.settings.get(SETTING_LARGE_TEXT))
        for control in (self.dialogs_list, self.messages_list, self.preview_text, self.message_input):
            control.SetFont(font)
        self.panel.Layout()

    def apply_simplicity(self):
        """Keep the window as plain as the settings ask: fewer stops for Tab, and the preview only if wanted."""
        skipped = self.settings.get(SETTING_SIMPLE_TAB)
        # Each of these is one key away anyway: the view on the menu bar, sending on Enter.
        # So are the buttons for the mouse: each is a menu command with its own shortcut.
        for control in (self.view_tabs, self.send_btn, self.back_btn, *self.mouse_buttons):
            control.skipped_by_tab = skipped
        # Part of the chat screen, so never there while the list of chats is.
        shown = self.in_chat and self.settings.get(SETTING_SHOW_PREVIEW)
        self.preview_label.Show(shown)
        self.preview_text.Show(shown)
        self.panel.Layout()

    def show_chat_screen(self, in_chat):
        """Put the entered chat on screen in place of the list of chats, or the list back.

        What is not on screen cannot take the focus either, so inside a chat Tab moves
        between its own controls only, and nothing of another chat is in the way.
        """
        self.in_chat = in_chat
        # Its menus, once the key or command that got here is done with the menu bar there was.
        wx.CallAfter(self.refresh_menu_bar_if_alive)
        # A transfer under way is shown on either screen.
        progress_shown = self.progress_gauge.IsShown()
        self.screens.Show(self.dialogs_box, not in_chat, recursive=True)
        self.screens.Show(self.chat_box, in_chat, recursive=True)
        # Shown or hidden along with the rest just now, though each has its own reason to be there.
        self.cancel_record_btn.Show(in_chat and self.recorder.is_recording())
        self.progress_gauge.Show(progress_shown)
        self.apply_simplicity()

    def back_to_list(self):
        """Go back to the list of chats if a chat is open; what is done next belongs there."""
        if self.current_dialog_id is not None:
            self.close_chat()

    def on_search_chats(self, event):
        self.show_context_menu([
            (MENU_FIND_KEY, self.on_find_menu),
            (MENU_SEARCH_ALL_KEY, self.on_search_all_menu),
            (MENU_GLOBAL_SEARCH_KEY, self.on_global_search_menu),
            (MENU_FIND_CHAT_KEY, self.on_find_chat_menu),
        ])

    def apply_colours(self):
        """Switch the whole app to the theme chosen in the settings."""
        set_theme(self.settings.get(SETTING_THEME))
        apply_theme(self)
        # Painted over with the rest just now: mark the current view's tab again.
        self.view_tabs.SetSelection(self.view_tabs.GetSelection())

    def restore_placement(self):
        """Open where the window was last left, if that spot still exists."""
        placement = self.settings.get_window_placement()
        if placement is None:
            self.Center()
            return
        x, y, width, height, maximized = placement
        rectangle = wx.Rect(x, y, width, height)
        # A monitor may have been unplugged since; never open off-screen.
        if is_on_a_screen(rectangle):
            self.SetSize(rectangle)
        else:
            self.Center()
        if maximized:
            self.Maximize()

    def save_placement(self):
        maximized = self.IsMaximized()
        if maximized or self.IsIconized():
            # Keep the size it had before, so un-maximizing later gives a sensible window.
            previous = self.settings.get_window_placement()
            x, y, width, height = previous[:4] if previous else (*self.GetPosition(), *MAIN_WINDOW_SIZE)
        else:
            x, y, width, height = self.GetRect()
        self.settings.set_window_placement(x, y, width, height, maximized)
        self.settings.save()

    def show_chat_name(self, chat):
        """Name the open chat in the title bar and above its messages; None for no chat."""
        if chat is None:
            title = self.i18n.get_string(MAIN_TITLE_KEY)
            label = self.i18n.get_string(MESSAGES_LABEL_KEY)
        else:
            title = self.i18n.get_string(MAIN_TITLE_CHAT_FORMAT_KEY).format(chat=chat["title"])
            status = self.status_text(chat)
            if status:
                label = self.i18n.get_string(MESSAGES_OF_LABEL_STATUS_FORMAT_KEY).format(chat=chat["title"], status=status)
            else:
                label = self.i18n.get_string(MESSAGES_OF_LABEL_FORMAT_KEY).format(chat=chat["title"])
        self.SetTitle(title)
        # Also what a screen reader says when the message list takes focus.
        self.messages_label.SetLabel(label)
        self.messages_list.SetName(label)

    def progress_reporter(self, format_key):
        """What to hand a transfer so that its progress shows here; called from the Telegram thread."""
        return lambda percent: wx.CallAfter(self.show_progress, format_key, percent)

    def show_progress(self, format_key, percent):
        # A late report must not bring the bar back after the transfer has ended.
        if not self or not (self.is_busy or self.transfers or self.upload is not None):
            return
        if not self.progress_gauge.IsShown():
            self.progress_gauge.Show()
            self.panel.Layout()
        self.progress_gauge.SetValue(percent)
        self.SetStatusText(self.i18n.get_string(format_key).format(percent=percent))

    def hide_progress(self):
        if self.progress_gauge.IsShown():
            self.progress_gauge.Hide()
            self.progress_gauge.SetValue(0)
            self.panel.Layout()

    def in_comments(self):
        return self.thread is not None and self.thread["view"] == MESSAGE_VIEW_COMMENTS

    def peer(self, dialog_id):
        """The chat the messages on screen live in. That is the open chat itself, except
        under a channel post: its comments belong to the channel's discussion group."""
        if self.thread is not None and dialog_id == self.current_dialog_id:
            return self.thread.get("peer", dialog_id)
        return dialog_id

    def thread_root(self):
        """What a new message must answer to land in the open topic or under the open post; None outside them."""
        if self.thread is None:
            return None
        if self.thread["view"] == MESSAGE_VIEW_TOPIC and self.thread["id"] == GENERAL_TOPIC_ID:
            # The first topic of a forum group takes messages that answer nothing.
            return None
        return self.thread.get("root", self.thread["id"])

    def belongs_to_thread(self, message):
        return self.thread is not None and message["thread_id"] == self.thread_root()

    def shown_chat(self):
        """The open chat as far as rights over the shown messages go. In a discussion group
        entered through a post, this account is a guest: it writes, and manages only its own."""
        if self.in_comments():
            return {"can_send": True, "can_pin": False, "has_links": True, "can_delete_others": False, "is_channel": True}
        return self.current_dialog()

    def forget_open_chat(self):
        """Empty the message area: no chat is open any more."""
        previous = self.current_dialog_id
        self.current_dialog_id = None
        self.drop_preview(previous)
        self.thread = None
        self.message_view = None
        self.show_chat_name(None)
        self.preview_text.ChangeValue("")
        self.set_compose()
        self.message_input.ChangeValue("")
        self.messages = []
        self.has_older = False
        self.marked = set()
        self.messages_list.Clear()
        self.enable_chat(False)
        self.show_chat_screen(False)

    def close_chat(self):
        """Leave the open chat for the chat list, as Escape does in Telegram's own apps; or, for a chat
        opened from the search window, for that window again, with its results as they were."""
        from_search = self.global_search is not None and self.current_dialog_id == self.search_result_id
        # What was being written stays with the chat.
        self.keep_draft()
        self.forget_open_chat()
        self.dialogs_list.SetFocus()
        self.notify(MSG_CHAT_CLOSED_KEY)
        if from_search:
            self.search_result_id = None
            # After this key press is over: a window shown from inside it would take its Escape too.
            wx.CallAfter(self.show_global_search)

    def status_text(self, chat):
        """"Online", "last seen ..." for a person's chat; empty for groups, channels, bots and hidden statuses."""
        if not chat["status"]:
            return ""
        key, time = chat["status"]
        text = self.i18n.get_string(key)
        if key == STATUS_LAST_SEEN_FORMAT_KEY:
            text = text.format(time=self.time_text(time, True))
        return text

    def open_settings(self, on_shortcuts=False):
        hotkey = self.show_window_shortcut()
        with SettingsDialog(self, self.i18n, self.settings, self.telegram_manager) as settings_dialog:
            if on_shortcuts:
                settings_dialog.show_shortcuts_page()
            if settings_dialog.ShowModal() != wx.ID_OK and not settings_dialog.account_deleted:
                return
            if settings_dialog.account_deleted:
                # Nothing is left to show or to sign out of. After this dialog is gone, not from inside it.
                wx.CallAfter(self.on_exit_menu, None)
                return
            settings_dialog.apply_app_settings()
            # What a row says, and in what order, may be among what was changed.
            self.render_dialogs()
            if self.messages:
                self.render_messages(self.messages_list.GetSelection() - self.message_offset())
            self.apply_simplicity()
            self.apply_text_size()
            self.apply_colours()
            self.apply_shortcuts()
            language_changed = settings_dialog.language_changed
            profile = settings_dialog.changed_profile()
            privacy = settings_dialog.changed_privacy()
            notify = settings_dialog.changed_notify()
        new_hotkey = self.show_window_shortcut()
        if new_hotkey != hotkey and self.on_hotkey_changed is not None and not self.on_hotkey_changed(new_hotkey):
            wx.MessageBox(
                self.i18n.get_string(ERR_HOTKEY_TAKEN_FORMAT_KEY).format(hotkey=new_hotkey),
                self.i18n.get_string(APP_TITLE_KEY), wx.OK | wx.ICON_WARNING, self
            )
        if notify:
            # Reloaded after: which chats are silent may have just changed for a whole kind of them.
            self.telegram_manager.save_notify(notify, self.on_ui_thread(lambda result: self.load_dialogs()))
        if privacy:
            self.telegram_manager.save_privacy(
                privacy, self.on_ui_thread(lambda result: self.notify(MSG_PRIVACY_SAVED_KEY))
            )
        if language_changed:
            # After the settings dialog is gone: a restart from inside it would leave it half closed.
            wx.CallAfter(self.offer_restart)
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

    def show_text(self, title_key, text, on_export=None):
        kwargs = {} if on_export is None else {"on_export": on_export}
        with TextDialog(self, self.i18n, self.i18n.get_string(title_key), text, **kwargs) as text_dialog:
            text_dialog.ShowModal()

    def notify(self, key, kind=None):
        """Short feedback that needs no dialog: shown in the status bar, and spoken if that kind is wanted."""
        self.announce(self.i18n.get_string(key), kind or speech.kind_of(key))

    def announce(self, text, kind=FEEDBACK_CONFIRM):
        self.SetStatusText(text)
        speech.say(text, kind)

    def feedback_wanted(self, kind):
        """What the settings say of a kind of remark; the switch for all of them comes first."""
        return self.settings.get(SETTING_SPEAK_FEEDBACK) and self.settings.get(FEEDBACK_SETTINGS[kind])

    def on_close(self, event):
        # Closing the window only hides it, so messages keep arriving; a real
        # exit (the Exit menu, logging out, Windows shutting down) cannot be vetoed.
        if event.CanVeto() and not self.is_quitting and self.settings.get(SETTING_KEEP_IN_BACKGROUND):
            event.Veto()
            self.recorder.cancel()
            self.update_record_buttons()
            self.save_placement()
            self.Hide()
            hotkey = self.show_window_shortcut()
            speak(
                self.i18n.get_string(MSG_IN_BACKGROUND_FORMAT_KEY).format(hotkey=hotkey) if hotkey
                else self.i18n.get_string(MSG_IN_BACKGROUND_KEY)
            )
            return
        self.player.stop()
        self.recorder.cancel()
        self.save_placement()
        event.Skip()
        # With the last window gone nothing would end the hidden background part.
        if not self.is_quitting and self.on_quit is not None:
            wx.CallAfter(self.on_quit)

    def quit(self):
        """Close for real, whatever the background setting says."""
        self.is_quitting = True
        self.Close()

    def bring_forward(self):
        """Show the window again after it was hidden or minimized."""
        self.Show()
        self.Iconize(False)
        self.Raise()
        self.on_brought_forward()
        self.check_updates_once()

    def enable_chat(self, enabled):
        """Unlock the writing controls, as far as the open chat lets this account write."""
        # Under a post, subscribers may write even where only admins may post.
        can_send = self.current_dialog().get("can_send", True) or self.in_comments()
        usable = enabled and can_send
        self.message_input.Enable(usable)
        self.send_btn.Enable(usable)
        self.attach_btn.Enable(usable)
        self.record_btn.Enable(usable and audio.AVAILABLE)
        if not self.reply_to and not self.editing:
            # In a channel that only its admins post to, say why the field is locked;
            # in one only looked at, how to join it.
            read_only = self.current_dialog_id is not None and not can_send
            chat = self.current_dialog()
            if read_only and chat.get("preview"):
                label = self.join_hint(chat)
            else:
                label = self.i18n.get_string(MSG_CANNOT_WRITE_KEY if read_only else MESSAGE_INPUT_LABEL_KEY)
            self.input_label.SetLabel(label)
            self.message_input.SetName(label)

    def set_status(self, key):
        self.SetStatusText(self.i18n.get_string(key))

    def show_error(self, error_key):
        self.set_status(STATUS_READY_KEY)
        self.is_busy = False
        if self.loading_more_from is not None:
            # The page that was asked for never came: ask again from where the list stands.
            self.loading_more_from = None
            self.dialogs_limit -= DIALOGS_LIMIT
        self.hide_progress()
        self.end_upload()
        self.enable_chat(self.current_dialog_id is not None)
        wx.MessageBox(
            self.i18n.get_string(error_key), self.i18n.get_string(APP_TITLE_KEY),
            wx.OK | wx.ICON_ERROR, self
        )

    def on_transfer_done(self, handler, *args, cleanup=None):
        """Like on_ui_thread, for a file coming down beside everything else: the window is never held
        up for it, and the progress bar goes once the last of them is over. `cleanup` runs either way."""
        self.transfers += 1
        def deliver(result, error_key):
            wx.CallAfter(self.finish_transfer, handler, result, error_key, cleanup, *args)
        return deliver

    def finish_transfer(self, handler, result, error_key, cleanup, *args):
        if not self:
            return
        self.transfers -= 1
        if cleanup is not None:
            cleanup()
        if not self.transfers and self.upload is None:
            self.hide_progress()
        self.handle_result(handler, result, error_key, *args)

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
        menu_less_command = self.menu_less_shortcuts.get(shortcuts.from_key_event(event))
        if menu_less_command is not None:
            # Not in the menu bar, so its shortcut is answered here, wherever the focus is in the window.
            menu_less_command(event)
            return
        sideways = event.GetKeyCode() in (wx.WXK_LEFT, wx.WXK_RIGHT, wx.WXK_NUMPAD_LEFT, wx.WXK_NUMPAD_RIGHT)
        if sideways and focused is self.dialogs_list and not event.HasAnyModifiers():
            # Up and down move through the chats; left and right go to the tab beside the current one,
            # without leaving the list.
            self.cycle_view(self.view_tabs.sideways_step(event.GetKeyCode()))
        elif event.GetKeyCode() == wx.WXK_SPACE and focused is self.messages_list and not event.HasAnyModifiers() \
                and not self.messages_type_ahead.is_typing() and self.listen():
            # A voice message or a song played, or stopped, straight from Telegram.
            pass
        elif sideways and focused is self.messages_list and not event.HasAnyModifiers():
            # Up and down move through the messages. Forward (left, in a right-to-left window) goes
            # into the post's comments; back says its numbers.
            if self.view_tabs.sideways_step(event.GetKeyCode()) > 0:
                self.on_comments_menu(event)
            else:
                self.on_message_stats_menu(event)
        elif self.view_tabs.handle_key(event, focused):
            # An arrow on one of the view tabs went to its neighbour.
            pass
        elif is_enter and focused is self.dialogs_list:
            self.on_open_dialog(event)
        elif is_enter and focused is self.messages_list and shortcuts.from_key_event(event) == "Shift+Enter":
            # Shift with Enter: the attachment, fetched if need be, shown in its folder instead of opened.
            self.on_show_in_folder_menu(event)
        elif is_enter and focused is self.messages_list:
            self.on_activate_message(event)
        elif is_enter and focused is self.message_input \
                and shortcuts.from_key_event(event) not in self.menu_shortcuts:
            # Where Enter with other keys is the shortcut of a menu entry, it is the menu's to act on.
            if self.enter_sends(event):
                self.on_send_message(event)
            else:
                self.message_input.WriteText("\n")
        elif event.ControlDown() and event.GetKeyCode() == ord("V") and focused is self.message_input \
                and self.paste_files():
            # The clipboard held files or a picture, and they are on their way.
            pass
        elif event.GetKeyCode() != wx.WXK_ESCAPE or not self.on_escape():
            event.Skip()

    def enter_sends(self, event):
        """Whether this press of Enter in the message field sends the message, rather than breaking the line."""
        if self.settings.get(SETTING_ENTER_SENDS):
            return not event.ShiftDown() and not event.ControlDown()
        return event.ControlDown()

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
        elif self.current_dialog_id is not None:
            self.close_chat()
        else:
            return False
        return True
