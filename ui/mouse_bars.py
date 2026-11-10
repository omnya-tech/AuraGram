import wx
from core import shortcuts
from ui import icons
from ui.layout import OptionalButton
from core.constants import (
    BTN_NEW_CHAT_KEY, BTN_GLOBAL_SEARCH_KEY, BTN_DOWNLOAD_FILES_KEY, BTN_CHAT_INFO_KEY, MENU_SETTINGS_KEY,
    BTN_MORE_ACTIONS_KEY, CONTEXT_REPLY_KEY, CONTEXT_FORWARD_KEY, CONTEXT_REACT_KEY, BTN_PLAY_KEY, BTN_OPEN_KEY,
    BTN_COMMENTS_KEY, BTN_STATS_KEY, BTN_REMIND_KEY, MSG_NOTHING_TO_PLAY_KEY, TOOLTIP_COMMAND_FORMAT_KEY,
    MENU_NEW_CHAT_KEY, MENU_GLOBAL_SEARCH_KEY, MENU_DOWNLOAD_FILES_KEY, MENU_CHAT_INFO_KEY, MENU_REPLY_KEY,
    MENU_FORWARD_KEY, MENU_REACT_KEY, MENU_OPEN_MEDIA_KEY, MENU_COMMENTS_KEY, MENU_MESSAGE_STATS_KEY, MENU_REMIND_KEY,
    TOOLTIP_SEARCH_MESSAGES_KEY, MENU_SEARCH_MESSAGES_KEY, TOOLTIP_RECORD_KEY, MENU_RECORD_KEY, TOOLTIP_SEND_KEY,
    CONTEXT_DELETE_KEY, MENU_DELETE_KEY, BTN_DELETE_CHAT_SHORT_KEY, MENU_CHAT_LEAVE_KEY,
    PLAYABLE_MEDIA, DOWNLOADABLE_MEDIA,
)

# The buttons below a chat that act on the selected message (the attachment's keeps BTN_OPEN_KEY as its key).
MESSAGE_BAR_KEYS = (
    CONTEXT_REPLY_KEY, CONTEXT_FORWARD_KEY, CONTEXT_REACT_KEY, BTN_PLAY_KEY, BTN_OPEN_KEY, BTN_COMMENTS_KEY,
    BTN_STATS_KEY, BTN_REMIND_KEY, CONTEXT_DELETE_KEY, BTN_MORE_ACTIONS_KEY,
)
from core.settings import SETTING_ENTER_SENDS

# The picture beside each button's words (see ui.icons).
BAR_ICONS = {
    BTN_NEW_CHAT_KEY: "add", BTN_GLOBAL_SEARCH_KEY: "globe", BTN_DOWNLOAD_FILES_KEY: "download",
    BTN_CHAT_INFO_KEY: "info", MENU_SETTINGS_KEY: "settings", BTN_MORE_ACTIONS_KEY: "more",
    CONTEXT_REPLY_KEY: "reply", CONTEXT_FORWARD_KEY: "forward", CONTEXT_REACT_KEY: "react", BTN_PLAY_KEY: "play",
    BTN_OPEN_KEY: "open", BTN_COMMENTS_KEY: "comments", BTN_STATS_KEY: "stats", BTN_REMIND_KEY: "remind",
    CONTEXT_DELETE_KEY: "delete", BTN_DELETE_CHAT_SHORT_KEY: "delete",
}

class MouseBarsMixin:
    """Rows of buttons for the mouse: the commands used most, in sight, on each of the two screens.

    The keyboard is not made to pay for them: like the Send button, Tab passes them by under the
    short way round (the default), and every one of them is a menu command with its own shortcut.
    Each button's tooltip names that shortcut, so a mouse user learns it along the way.
    """

    def list_bar_entries(self):
        return (
            (BTN_NEW_CHAT_KEY, self.on_new_chat_menu, MENU_NEW_CHAT_KEY),
            (BTN_GLOBAL_SEARCH_KEY, self.on_global_search_menu, MENU_GLOBAL_SEARCH_KEY),
            (BTN_DOWNLOAD_FILES_KEY, self.on_download_files_menu, MENU_DOWNLOAD_FILES_KEY),
            (BTN_CHAT_INFO_KEY, lambda event: self.on_chat_menu(self.show_chat_info), MENU_CHAT_INFO_KEY),
            (MENU_SETTINGS_KEY, self.on_settings_menu, MENU_SETTINGS_KEY),
            (BTN_DELETE_CHAT_SHORT_KEY, lambda event: self.on_chat_menu(self.delete_chat), MENU_CHAT_LEAVE_KEY),
            (BTN_MORE_ACTIONS_KEY, lambda event: self.on_dialog_context_menu(self.no_position(self.dialogs_list)), None),
        )

    def chat_bar_entries(self):
        return (
            (CONTEXT_REPLY_KEY, self.on_reply_menu, MENU_REPLY_KEY),
            (CONTEXT_FORWARD_KEY, self.on_forward_menu, MENU_FORWARD_KEY),
            (CONTEXT_REACT_KEY, self.on_react_menu, MENU_REACT_KEY),
            (BTN_PLAY_KEY, self.on_play_button, None),
            (BTN_OPEN_KEY, self.on_activate_message, MENU_OPEN_MEDIA_KEY),
            (BTN_COMMENTS_KEY, self.on_comments_menu, MENU_COMMENTS_KEY),
            (BTN_STATS_KEY, self.on_message_stats_menu, MENU_MESSAGE_STATS_KEY),
            (BTN_REMIND_KEY, self.on_remind_menu, MENU_REMIND_KEY),
            (CONTEXT_DELETE_KEY, self.on_delete_menu, MENU_DELETE_KEY),
            (BTN_MORE_ACTIONS_KEY, lambda event: self.on_message_context_menu(self.no_position(self.messages_list)), None),
        )

    def build_mouse_bar(self, entries, first=(), on_message=False):
        """A row that wraps onto more lines when the window is narrow; `first` are buttons made elsewhere."""
        # Without the default stretch of the last button on each line to the window's edge.
        bar = wx.WrapSizer(wx.HORIZONTAL, 0)
        for button in first:
            bar.Add(button, flag=wx.RIGHT|wx.BOTTOM, border=6)
        for label_key, handler, command in entries:
            button = OptionalButton(self.panel, label=self.i18n.get_string(label_key))
            icons.put_on(button, BAR_ICONS.get(label_key))
            button.Bind(wx.EVT_BUTTON, handler)
            button.command = command
            button.label_key = label_key
            # The chat's row of buttons, which act on the message selected.
            button.on_message = on_message
            bar.Add(button, flag=wx.RIGHT|wx.BOTTOM, border=6)
            self.mouse_buttons.append(button)
        return bar

    def update_message_bar(self, message):
        """Grey out what does nothing on the selected message, as Telegram's apps offer only what works on it:
        no reply where one cannot write, no playing without sound, no comments where there are none."""
        if message is None:
            usable = set()
        else:
            chat = self.shown_chat() if self.current_dialog_id is not None else {}
            usable = {CONTEXT_FORWARD_KEY, CONTEXT_REACT_KEY, BTN_REMIND_KEY, BTN_MORE_ACTIONS_KEY}
            if chat.get("can_send", True) or self.in_comments():
                usable.add(CONTEXT_REPLY_KEY)
            if message["media"] in PLAYABLE_MEDIA:
                usable.add(BTN_PLAY_KEY)
            if message["media"] in DOWNLOADABLE_MEDIA:
                usable.add(BTN_OPEN_KEY)
            if message["comments"] is not None:
                usable.add(BTN_COMMENTS_KEY)
            if self.message_stats(message):
                usable.add(BTN_STATS_KEY)
            if self.can_delete(message):
                usable.add(CONTEXT_DELETE_KEY)
        # Whatever is selected, the button stops what is playing.
        player = getattr(self, "player", None)
        if player is not None and player.is_playing():
            usable.add(BTN_PLAY_KEY)
        for button in getattr(self, "mouse_buttons", ()):
            if getattr(button, "label_key", None) in MESSAGE_BAR_KEYS and getattr(button, "on_message", False):
                button.Enable(button.label_key in usable)

    def update_mouse_tooltips(self):
        """Each button's tooltip: its command, with the shortcut it has now."""
        table = shortcuts.current(self.settings)
        for button in getattr(self, "mouse_buttons", ()):
            if button.command is None:
                continue
            command = self.i18n.get_string(button.command)
            shortcut = table.get(button.command)
            button.SetToolTip(
                self.i18n.get_string(TOOLTIP_COMMAND_FORMAT_KEY).format(command=command, shortcut=shortcut)
                if shortcut else command
            )
        # The buttons beside the writing field, likewise; Send goes with Enter or Ctrl+Enter, as set.
        send_key = "Enter" if self.settings.get(SETTING_ENTER_SENDS) else "Ctrl+Enter"
        for name, text_key, shortcut in (
            ("search_btn", TOOLTIP_SEARCH_MESSAGES_KEY, table.get(MENU_SEARCH_MESSAGES_KEY)),
            ("record_btn", TOOLTIP_RECORD_KEY, table.get(MENU_RECORD_KEY)),
            ("send_btn", TOOLTIP_SEND_KEY, send_key),
        ):
            button = getattr(self, name, None)
            if button is not None:
                text = self.i18n.get_string(text_key)
                button.SetToolTip(
                    self.i18n.get_string(TOOLTIP_COMMAND_FORMAT_KEY).format(command=text, shortcut=shortcut)
                    if shortcut else text
                )

    def no_position(self, list_box):
        """A context-menu request as the Menu key makes it: on the selected item, wherever the mouse is."""
        return wx.ContextMenuEvent(wx.wxEVT_CONTEXT_MENU, list_box.GetId(), wx.DefaultPosition)

    def on_play_button(self, event):
        if not self.listen():
            self.notify(MSG_NOTHING_TO_PLAY_KEY)
