import os
import threading
import wx
from core import audio, diagnostics, updates
from core.speech import speak
from core.settings import (
    SETTING_KEEP_IN_BACKGROUND, SETTING_LARGE_TEXT, SETTING_THEME, SETTING_SPEAK_FEEDBACK,
    SETTING_SIMPLE_TAB, SETTING_SHOW_PREVIEW, SETTING_CHECK_UPDATES, SETTING_LANGUAGE, SETTING_ENTER_SENDS
)
from ui.themes import apply_theme, set_theme
from ui.layout import OptionalButton, OptionalChoice, ReadOnlyText, is_on_a_screen, prepare_window, reading_font
from ui.settings_dialog import SettingsDialog
from core.chat_views import build_views
from ui.text_dialog import TextDialog
from core.constants import (
    MENU_READ_MESSAGE_KEY, MENU_HELP_KEY, MENU_SHORTCUTS_KEY, SHORTCUTS_TITLE_KEY, SHORTCUTS_TEXT_KEY,
    MENU_MARK_KEY, MENU_UNMARK_ALL_KEY, MENU_NEW_GROUP_KEY, MENU_NEW_CHANNEL_KEY, MESSAGE_VIEWS,
    MENU_CHAT_VIEWS_KEY, MENU_NEW_POLL_KEY, MENU_REACT_KEY, MENU_SCHEDULE_KEY,
    MSG_IN_BACKGROUND_FORMAT_KEY, SHOW_HOTKEY_TEXT, BTN_RECORD_KEY, MAIN_WINDOW_SIZE,
    MAIN_WINDOW_MIN_SIZE, PREVIEW_HEIGHT, PREVIEW_LABEL_KEY, MAIN_TITLE_CHAT_FORMAT_KEY,
    MESSAGES_OF_LABEL_FORMAT_KEY, TOOLTIP_SEND_KEY, TOOLTIP_RECORD_KEY, TOOLTIP_VIEW_KEY,
    BTN_CANCEL_RECORDING_KEY, MSG_CANNOT_WRITE_KEY, MENU_ABOUT_KEY, ABOUT_FORMAT_KEY,
    APP_NAME, APP_VERSION, DEVELOPER_NAME_KEY,
    VIEW_LABEL_KEY, MSG_PRIVACY_SAVED_KEY, MENU_CHATS_KEY, MENU_NEW_CHAT_KEY, MENU_FIND_CHAT_KEY,
    MENU_FORWARD_KEY, MENU_PIN_KEY, MENU_SETTINGS_KEY, MSG_SETTINGS_SAVED_KEY,
    MSG_PROFILE_SAVED_KEY, ERR_FIRST_NAME_REQUIRED_KEY, MENU_RECORD_KEY, MENU_SEARCH_MESSAGES_KEY,
    DIALOGS_LIMIT, MENU_MESSAGE_KEY, MENU_REPLY_KEY, MSG_REPLY_CANCELLED_KEY, MENU_EDIT_KEY,
    MENU_DELETE_KEY, MENU_SEND_FILE_KEY, MENU_SEARCH_KEY, MENU_FIND_KEY, MENU_FIND_NEXT_KEY,
    APP_TITLE_KEY, MAIN_TITLE_KEY, DIALOGS_LABEL_KEY, MESSAGES_LABEL_KEY, MESSAGE_INPUT_LABEL_KEY,
    BTN_SEND_MESSAGE_KEY, STATUS_READY_KEY, MENU_FILE_KEY, MENU_LOGOUT_KEY, MENU_EXIT_KEY,
    MSG_CONFIRM_LOGOUT_KEY, MSG_LANGUAGE_RESTART_KEY, MENU_SEND_KEY, MENU_GO_KEY, MENU_GO_CHATS_KEY, MENU_GO_MESSAGES_KEY,
    MENU_GO_INPUT_KEY, MENU_NEXT_UNREAD_KEY, MENU_NEXT_VIEW_KEY, MENU_PREVIOUS_VIEW_KEY,
    MENU_CHAT_INFO_KEY, MENU_CHAT_READ_KEY, MENU_CHAT_PIN_KEY, MENU_CHAT_MUTE_KEY, MENU_CHAT_ARCHIVE_KEY,
    MENU_CHAT_CLEAR_KEY, MENU_CHAT_LEAVE_KEY, MENU_COPY_KEY, MENU_COPY_LINK_KEY, MENU_OPEN_MEDIA_KEY,
    MENU_SAVE_AS_KEY, MENU_OPEN_DOWNLOADS_KEY, MENU_CONNECTION_KEY, DOWNLOADS_DIR,
    TRAY_STATUS_FORMAT_KEY, CONNECTION_STATE_KEYS, CONNECTION_CONNECTING, MENU_BUTTONS_KEY, MENU_SAVED_KEY,
    MESSAGES_OF_LABEL_STATUS_FORMAT_KEY, STATUS_LAST_SEEN_FORMAT_KEY, DATE_TIME_FORMAT,
    MENU_ADD_CONTACT_KEY, MENU_BLOCKED_KEY, MENU_CHAT_CONTACT_KEY, MENU_CHAT_BLOCK_KEY, MENU_CHAT_JOIN_KEY,
    MENU_GLOBAL_SEARCH_KEY, MENU_OPEN_LINK_KEY, MENU_SEND_STICKER_KEY, MENU_SEND_CONTACT_KEY,
    MENU_SEND_LOCATION_KEY, MENU_MENTION_KEY, MENU_COMMENTS_KEY, MENU_TOPICS_KEY, MENU_AUDIENCE_KEY,
    MESSAGE_VIEW_COMMENTS, MENU_TRANSLATE_KEY, MENU_STORIES_KEY, BTN_ATTACH_KEY, TOOLTIP_ATTACH_KEY,
    PROGRESS_LABEL_KEY, MSG_CHAT_CLOSED_KEY, MENU_SEND_AS_KEY, MENU_POST_STORY_KEY, MESSAGE_VIEW_TOPIC,
    GENERAL_TOPIC_ID, BTN_SEARCH_KEY, TOOLTIP_SEARCH_CHATS_KEY, TOOLTIP_SEARCH_MESSAGES_KEY, BTN_BACK_KEY,
    TOOLTIP_BACK_KEY, MENU_GO_TO_REPLY_KEY, MENU_GO_TO_DATE_KEY, MENU_SEARCH_ALL_KEY, MENU_SEND_SILENT_KEY,
    MENU_FOLDERS_KEY, MENU_MARK_ALL_READ_KEY, MENU_VOICE_SPEED_KEY, MENU_REPORT_KEY, MENU_COPY_INVITE_KEY,
    MENU_DESCRIBE_IMAGE_KEY, MENU_CHECK_UPDATES_KEY, MENU_PROBLEM_REPORT_KEY, MSG_UPDATE_AVAILABLE_FORMAT_KEY,
    MSG_UP_TO_DATE_FORMAT_KEY, ERR_UPDATE_CHECK_KEY, MSG_PROBLEM_REPORT_PROMPT_KEY,
    MSG_PROBLEM_REPORT_SAVED_FORMAT_KEY, ERR_PROBLEM_REPORT_KEY, REPORT_LANGUAGE_FORMAT, MENU_MESSAGE_SENDER_KEY,
    MESSAGE_INPUT_HEIGHT
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
        super().__init__(None, title=i18n.get_string(MAIN_TITLE_KEY), size=MAIN_WINDOW_SIZE)
        prepare_window(self, i18n)
        self.SetMinSize(MAIN_WINDOW_MIN_SIZE)
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
        # True while older messages or a media file are being fetched.
        self.is_busy = False
        # (dialog id, message id) -> what Gemini said of that picture, so asking twice costs once.
        self.descriptions = {}
        # Whether this run has already looked for a newer release by itself.
        self.updates_checked = False
        self.init_ui()
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.telegram_manager.set_message_listener(
            lambda *args: wx.CallAfter(self.on_telegram_event, *args)
        )
        self.load_dialogs()
        self.telegram_manager.load_folders(self.on_ui_thread(self.show_folders))

    def init_ui(self):
        self.panel = wx.Panel(self)
        # Two screens share the window, one at a time: the list of chats, and the chat that was entered.
        hbox = self.screens = wx.BoxSizer(wx.HORIZONTAL)

        dialogs_box = self.dialogs_box = wx.BoxSizer(wx.VERTICAL)
        view_label = wx.StaticText(self.panel, label=self.i18n.get_string(VIEW_LABEL_KEY))
        dialogs_box.Add(view_label, flag=wx.BOTTOM, border=5)
        self.view_choice = OptionalChoice(self.panel, choices=[view.label for view in self.views])
        self.view_choice.SetSelection(self.view_index)
        self.view_choice.Bind(wx.EVT_CHOICE, self.on_view_changed)
        dialogs_box.Add(self.view_choice, flag=wx.EXPAND|wx.BOTTOM, border=10)
        dialogs_label = wx.StaticText(self.panel, label=self.i18n.get_string(DIALOGS_LABEL_KEY))
        dialogs_box.Add(dialogs_label, flag=wx.BOTTOM, border=5)
        self.dialogs_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        self.dialogs_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_open_dialog)
        self.dialogs_list.Bind(wx.EVT_CONTEXT_MENU, self.on_dialog_context_menu)
        # Enter never reaches the list as a key event inside a panel, so catch it here.
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        dialogs_box.Add(self.dialogs_list, proportion=1, flag=wx.EXPAND)
        self.list_search_btn = wx.Button(self.panel, label=self.i18n.get_string(BTN_SEARCH_KEY))
        self.list_search_btn.Bind(wx.EVT_BUTTON, self.on_search_chats)
        self.list_search_btn.SetToolTip(self.i18n.get_string(TOOLTIP_SEARCH_CHATS_KEY))
        dialogs_box.Add(self.list_search_btn, flag=wx.TOP, border=10)
        hbox.Add(dialogs_box, proportion=1, flag=wx.EXPAND|wx.ALL, border=15)

        chat_box = self.chat_box = wx.BoxSizer(wx.VERTICAL)
        self.messages_label = wx.StaticText(self.panel, label=self.i18n.get_string(MESSAGES_LABEL_KEY))
        chat_box.Add(self.messages_label, flag=wx.BOTTOM, border=5)
        self.messages_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
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

        self.input_label = wx.StaticText(self.panel, label=self.i18n.get_string(MESSAGE_INPUT_LABEL_KEY))
        chat_box.Add(self.input_label, flag=wx.BOTTOM, border=5)
        input_box = wx.BoxSizer(wx.HORIZONTAL)
        # Several lines, so a message can have line breaks; which key sends is decided in on_char_hook.
        self.message_input = wx.TextCtrl(self.panel, style=wx.TE_MULTILINE, size=(-1, MESSAGE_INPUT_HEIGHT))
        self.message_input.Bind(wx.EVT_TEXT, self.on_input_changed)
        input_box.Add(self.message_input, proportion=1, flag=wx.EXPAND|wx.RIGHT, border=10)
        self.send_btn = OptionalButton(self.panel, label=self.i18n.get_string(BTN_SEND_MESSAGE_KEY))
        self.send_btn.Bind(wx.EVT_BUTTON, self.on_send_message)
        input_box.Add(self.send_btn, flag=wx.RIGHT, border=10)
        # Everything that can go with a message besides its text, in one menu.
        self.attach_btn = wx.Button(self.panel, label=self.i18n.get_string(BTN_ATTACH_KEY))
        self.attach_btn.Bind(wx.EVT_BUTTON, self.on_attach)
        input_box.Add(self.attach_btn, flag=wx.RIGHT, border=10)
        # One button starts the recording and, renamed while it runs, stops and sends it.
        self.record_btn = wx.Button(self.panel, label=self.i18n.get_string(BTN_RECORD_KEY))
        self.record_btn.Bind(wx.EVT_BUTTON, self.on_record_menu)
        input_box.Add(self.record_btn)
        self.cancel_record_btn = wx.Button(self.panel, label=self.i18n.get_string(BTN_CANCEL_RECORDING_KEY))
        self.cancel_record_btn.Bind(wx.EVT_BUTTON, lambda event: self.cancel_recording())
        self.cancel_record_btn.Hide()
        input_box.Add(self.cancel_record_btn, flag=wx.LEFT, border=10)
        self.search_btn = wx.Button(self.panel, label=self.i18n.get_string(BTN_SEARCH_KEY))
        self.search_btn.Bind(wx.EVT_BUTTON, self.on_search_messages_menu)
        self.search_btn.SetToolTip(self.i18n.get_string(TOOLTIP_SEARCH_MESSAGES_KEY))
        input_box.Add(self.search_btn, flag=wx.LEFT, border=10)
        # For the mouse: the keyboard has Escape, so Tab need not stop here.
        self.back_btn = OptionalButton(self.panel, label=self.i18n.get_string(BTN_BACK_KEY))
        self.back_btn.Bind(wx.EVT_BUTTON, lambda event: self.close_chat())
        self.back_btn.SetToolTip(self.i18n.get_string(TOOLTIP_BACK_KEY))
        input_box.Add(self.back_btn, flag=wx.LEFT, border=10)
        chat_box.Add(input_box, flag=wx.EXPAND)
        # Seen only while a file goes up or comes down. A real progress bar, so a screen
        # reader reports it the way it reports any other, with no extra talk from the app.
        self.progress_gauge = wx.Gauge(self.panel, range=100)
        self.progress_gauge.SetName(self.i18n.get_string(PROGRESS_LABEL_KEY))
        self.progress_gauge.Hide()
        chat_box.Add(self.progress_gauge, flag=wx.EXPAND|wx.TOP, border=10)
        hbox.Add(chat_box, proportion=1, flag=wx.EXPAND|wx.ALL, border=15)

        self.view_choice.SetToolTip(self.i18n.get_string(TOOLTIP_VIEW_KEY))
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
        for control in (self.view_choice, self.send_btn, self.back_btn):
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

    def on_attach(self, event):
        self.show_context_menu([
            (MENU_SEND_FILE_KEY, self.on_send_file_menu),
            (MENU_SEND_STICKER_KEY, self.on_send_sticker_menu),
            (MENU_SEND_CONTACT_KEY, self.on_send_contact_menu),
            (MENU_SEND_LOCATION_KEY, self.on_send_location_menu),
            (MENU_NEW_POLL_KEY, self.on_new_poll_menu),
        ])

    def progress_reporter(self, format_key):
        """What to hand a transfer so that its progress shows here; called from the Telegram thread."""
        return lambda percent: wx.CallAfter(self.show_progress, format_key, percent)

    def show_progress(self, format_key, percent):
        # A late report must not bring the bar back after the transfer has ended.
        if not self or not self.is_busy:
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
        self.current_dialog_id = None
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
        """Leave the open chat for the chat list, as Escape does in Telegram's own apps."""
        # What was being written stays with the chat.
        self.keep_draft()
        self.forget_open_chat()
        self.dialogs_list.SetFocus()
        self.notify(MSG_CHAT_CLOSED_KEY)

    def status_text(self, chat):
        """"Online", "last seen ..." for a person's chat; empty for groups, channels, bots and hidden statuses."""
        if not chat["status"]:
            return ""
        key, time = chat["status"]
        text = self.i18n.get_string(key)
        if key == STATUS_LAST_SEEN_FORMAT_KEY:
            text = text.format(time=self.time_text(time, True))
        return text

    def init_menu(self):
        """The menu bar holds every command the app has, so nothing depends on finding a button or a context menu."""
        on_chat = self.on_chat_menu
        menu_bar = wx.MenuBar()
        for title_key, entries in (
            (MENU_FILE_KEY, (
                (MENU_SETTINGS_KEY, self.on_settings_menu, wx.ID_PREFERENCES),
                (MENU_OPEN_DOWNLOADS_KEY, self.on_open_downloads_menu),
                (MENU_LOGOUT_KEY, self.on_logout_menu),
                None,
                (MENU_EXIT_KEY, self.on_exit_menu, wx.ID_EXIT),
            )),
            (MENU_CHATS_KEY, (
                (MENU_NEW_CHAT_KEY, self.on_new_chat_menu),
                (MENU_FIND_CHAT_KEY, self.on_find_chat_menu),
                (MENU_SAVED_KEY, self.on_saved_messages_menu),
                (MENU_NEW_GROUP_KEY, lambda event: self.create_chat(is_channel=False)),
                (MENU_NEW_CHANNEL_KEY, lambda event: self.create_chat(is_channel=True)),
                (MENU_ADD_CONTACT_KEY, self.on_add_contact_menu),
                (MENU_BLOCKED_KEY, self.on_blocked_menu),
                (MENU_FOLDERS_KEY, self.on_folders_menu),
                (MENU_MARK_ALL_READ_KEY, self.on_mark_all_read_menu),
                None,
                (MENU_CHAT_INFO_KEY, lambda event: on_chat(self.show_chat_info)),
                (MENU_COPY_INVITE_KEY, lambda event: on_chat(self.copy_invite_link)),
                (MENU_CHAT_READ_KEY, lambda event: on_chat(self.toggle_dialog_read)),
                (MENU_CHAT_PIN_KEY, lambda event: on_chat(lambda chat: self.set_chat_pinned(chat, not chat["pinned"]))),
                (MENU_CHAT_MUTE_KEY, lambda event: on_chat(self.toggle_dialog_muted)),
                (MENU_CHAT_ARCHIVE_KEY, lambda event: on_chat(lambda chat: self.set_chat_archived(chat, not chat["archived"]))),
                (MENU_CHAT_JOIN_KEY, lambda event: on_chat(self.join_dialog)),
                (MENU_CHAT_CONTACT_KEY, lambda event: on_chat(self.toggle_contact)),
                (MENU_CHAT_BLOCK_KEY, lambda event: on_chat(self.toggle_blocked)),
                None,
                # Last, away from the everyday entries: these cannot be undone.
                (MENU_CHAT_CLEAR_KEY, lambda event: on_chat(self.clear_history)),
                (MENU_CHAT_LEAVE_KEY, lambda event: on_chat(lambda chat: self.leave_chat(chat, self.is_private_chat(chat)))),
            )),
            (MENU_CHAT_VIEWS_KEY, (
                (MENU_NEXT_VIEW_KEY, lambda event: self.cycle_view(1)),
                (MENU_PREVIOUS_VIEW_KEY, lambda event: self.cycle_view(-1)),
                None,
                (MENU_TOPICS_KEY, self.on_topics_menu),
                (MENU_STORIES_KEY, self.on_stories_menu),
                (MENU_POST_STORY_KEY, self.on_post_story_menu),
            ) + tuple(
                (view, lambda event, view=view: self.open_message_view(view)) for view in MESSAGE_VIEWS
            )),
            (MENU_GO_KEY, (
                (MENU_GO_CHATS_KEY, lambda event: self.close_chat() if self.in_chat else self.dialogs_list.SetFocus()),
                (MENU_GO_MESSAGES_KEY, lambda event: self.messages_list.SetFocus()),
                (MENU_GO_INPUT_KEY, lambda event: self.message_input.SetFocus()),
                None,
                (MENU_NEXT_UNREAD_KEY, self.on_next_unread_menu),
                None,
                (MENU_GO_TO_DATE_KEY, self.on_go_to_date_menu),
                (MENU_GO_TO_REPLY_KEY, self.on_go_to_reply_menu),
            )),
            (MENU_MESSAGE_KEY, (
                (MENU_REPLY_KEY, self.on_reply_menu),
                (MENU_EDIT_KEY, self.on_edit_menu),
                (MENU_FORWARD_KEY, self.on_forward_menu),
                (MENU_MESSAGE_SENDER_KEY, self.on_message_sender_menu),
                (MENU_REACT_KEY, self.on_react_menu),
                (MENU_PIN_KEY, self.on_pin_menu),
                (MENU_DELETE_KEY, self.on_delete_menu),
                None,
                (MENU_READ_MESSAGE_KEY, self.on_read_message_menu),
                (MENU_TRANSLATE_KEY, self.on_translate_menu),
                (MENU_DESCRIBE_IMAGE_KEY, self.on_describe_image_menu),
                (MENU_COPY_KEY, self.on_copy_message),
                (MENU_COPY_LINK_KEY, self.on_copy_link_menu),
                (MENU_OPEN_MEDIA_KEY, self.on_activate_message),
                (MENU_SAVE_AS_KEY, self.on_save_as_menu),
                (MENU_BUTTONS_KEY, self.on_buttons_menu),
                (MENU_OPEN_LINK_KEY, self.on_open_link_menu),
                (MENU_COMMENTS_KEY, self.on_comments_menu),
                (MENU_AUDIENCE_KEY, self.on_audience_menu),
                (MENU_VOICE_SPEED_KEY, self.on_voice_speed_menu),
                (MENU_REPORT_KEY, self.on_report_menu),
                None,
                (MENU_MARK_KEY, self.on_mark_menu),
                (MENU_UNMARK_ALL_KEY, self.on_unmark_all_menu),
            )),
            (MENU_SEND_KEY, (
                (MENU_SEND_FILE_KEY, self.on_send_file_menu),
                (MENU_RECORD_KEY, self.on_record_menu),
                (MENU_SEND_STICKER_KEY, self.on_send_sticker_menu),
                (MENU_SEND_CONTACT_KEY, self.on_send_contact_menu),
                (MENU_SEND_LOCATION_KEY, self.on_send_location_menu),
                (MENU_NEW_POLL_KEY, self.on_new_poll_menu),
                (MENU_SEND_SILENT_KEY, lambda event: self.on_send_message(event, silent=True)),
                (MENU_SCHEDULE_KEY, self.on_schedule_menu),
                None,
                (MENU_MENTION_KEY, self.on_mention_menu),
                (MENU_SEND_AS_KEY, self.on_send_as_menu),
            )),
            (MENU_SEARCH_KEY, (
                (MENU_FIND_KEY, self.on_find_menu),
                (MENU_FIND_NEXT_KEY, self.on_find_next_menu),
                (MENU_SEARCH_MESSAGES_KEY, self.on_search_messages_menu),
                (MENU_SEARCH_ALL_KEY, self.on_search_all_menu),
                (MENU_GLOBAL_SEARCH_KEY, self.on_global_search_menu),
            )),
            (MENU_HELP_KEY, (
                (MENU_SHORTCUTS_KEY, self.on_shortcuts_menu, wx.ID_HELP),
                (MENU_CONNECTION_KEY, self.on_connection_menu),
                (MENU_CHECK_UPDATES_KEY, lambda event: self.check_for_updates(quiet=False)),
                (MENU_PROBLEM_REPORT_KEY, self.on_problem_report_menu),
                (MENU_ABOUT_KEY, self.on_about_menu, wx.ID_ABOUT),
            )),
        ):
            menu = wx.Menu()
            for entry in entries:
                if entry is None:
                    menu.AppendSeparator()
                    continue
                label_key, handler, *item_id = entry
                item = menu.Append(item_id[0] if item_id else wx.ID_ANY, self.i18n.get_string(label_key))
                self.Bind(wx.EVT_MENU, handler, item)
            menu_bar.Append(menu, self.i18n.get_string(title_key))
        self.SetMenuBar(menu_bar)

    def on_open_downloads_menu(self, event):
        # Nothing has been downloaded yet on a fresh install.
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        os.startfile(DOWNLOADS_DIR)

    def on_connection_menu(self, event):
        state = self.telegram_manager.connection_state or CONNECTION_CONNECTING
        text = self.i18n.get_string(TRAY_STATUS_FORMAT_KEY).format(
            app=APP_NAME, status=self.i18n.get_string(CONNECTION_STATE_KEYS[state])
        )
        self.SetStatusText(text)
        # Asked for by name, so it is spoken whatever the setting for passing remarks says.
        speak(text)

    def check_updates_once(self):
        """Look for a newer release, by itself and at most once a run, the first time the window is seen."""
        if self.updates_checked or not self.settings.get(SETTING_CHECK_UPDATES) or not updates.is_configured():
            return
        self.updates_checked = True
        self.check_for_updates(quiet=True)

    def check_for_updates(self, quiet):
        """Ask whether a newer release is out. `quiet` says nothing unless there is one."""
        language = self.settings.get(SETTING_LANGUAGE)

        def work():
            release = updates.fetch_release(language)
            wx.CallAfter(self.on_update_checked, release, quiet)
        threading.Thread(target=work, daemon=True).start()

    def on_update_checked(self, release, quiet):
        if not self:
            return
        if release is None or not updates.is_newer(release["version"]):
            if not quiet:
                self.announce(
                    self.i18n.get_string(ERR_UPDATE_CHECK_KEY) if release is None
                    else self.i18n.get_string(MSG_UP_TO_DATE_FORMAT_KEY).format(current=APP_VERSION)
                )
            return
        question = self.i18n.get_string(MSG_UPDATE_AVAILABLE_FORMAT_KEY).format(
            version=release["version"], current=APP_VERSION, notes=release["notes"]
        )
        # Opened in the browser for the user to fetch: the program runs nothing it downloaded itself.
        if self.confirm(question):
            wx.LaunchDefaultBrowser(release["url"])

    def on_problem_report_menu(self, event):
        description = self.ask_text(MSG_PROBLEM_REPORT_PROMPT_KEY)
        if description is None:
            return
        try:
            path = diagnostics.write_report(DOWNLOADS_DIR, description, [
                REPORT_LANGUAGE_FORMAT.format(language=self.settings.get(SETTING_LANGUAGE))
            ])
        except OSError:
            self.show_error(ERR_PROBLEM_REPORT_KEY)
            return
        wx.MessageBox(
            self.i18n.get_string(MSG_PROBLEM_REPORT_SAVED_FORMAT_KEY).format(path=path),
            self.i18n.get_string(APP_TITLE_KEY), wx.OK | wx.ICON_INFORMATION, self
        )
        os.startfile(os.path.dirname(path))

    def on_settings_menu(self, event):
        with SettingsDialog(self, self.i18n, self.settings, self.telegram_manager) as settings_dialog:
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
            language_changed = settings_dialog.language_changed
            profile = settings_dialog.changed_profile()
            privacy = settings_dialog.changed_privacy()
            notify = settings_dialog.changed_notify()
        if notify:
            # Reloaded after: which chats are silent may have just changed for a whole kind of them.
            self.telegram_manager.save_notify(notify, self.on_ui_thread(lambda result: self.load_dialogs()))
        if privacy:
            self.telegram_manager.save_privacy(
                privacy, self.on_ui_thread(lambda result: self.notify(MSG_PRIVACY_SAVED_KEY))
            )
        if language_changed:
            wx.MessageBox(
                self.i18n.get_string(MSG_LANGUAGE_RESTART_KEY), self.i18n.get_string(APP_TITLE_KEY),
                wx.OK | wx.ICON_INFORMATION, self
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
        if self.settings.get(SETTING_SPEAK_FEEDBACK):
            speak(text)

    def on_close(self, event):
        # Closing the window only hides it, so messages keep arriving; a real
        # exit (the Exit menu, logging out, Windows shutting down) cannot be vetoed.
        if event.CanVeto() and not self.is_quitting and self.settings.get(SETTING_KEEP_IN_BACKGROUND):
            event.Veto()
            self.recorder.cancel()
            self.update_record_buttons()
            self.save_placement()
            self.Hide()
            speak(self.i18n.get_string(MSG_IN_BACKGROUND_FORMAT_KEY).format(hotkey=SHOW_HOTKEY_TEXT))
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
        self.check_updates_once()

    def on_logout_menu(self, event):
        answer = wx.MessageBox(
            self.i18n.get_string(MSG_CONFIRM_LOGOUT_KEY), self.i18n.get_string(APP_TITLE_KEY),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self
        )
        if answer == wx.YES:
            self.on_logout()

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
        self.hide_progress()
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
        sideways = event.GetKeyCode() in (wx.WXK_LEFT, wx.WXK_RIGHT, wx.WXK_NUMPAD_LEFT, wx.WXK_NUMPAD_RIGHT)
        if sideways and focused in (self.dialogs_list, self.messages_list) and not event.HasAnyModifiers():
            # In the lists only up and down move. Windows would make left and right do the
            # same; they are kept free here for what they may be given to do later.
            pass
        elif is_enter and focused is self.dialogs_list:
            self.on_open_dialog(event)
        elif is_enter and focused is self.messages_list:
            self.on_activate_message(event)
        elif is_enter and focused is self.message_input and not event.AltDown() \
                and not (event.ControlDown() and event.ShiftDown()):
            # With Alt, or with Ctrl and Shift together, it is one of the menu's own ways of sending.
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
