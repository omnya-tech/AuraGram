import wx
from core import shortcuts
from ui.layout import OptionalButton
from core.constants import (
    BTN_NEW_CHAT_KEY, BTN_GLOBAL_SEARCH_KEY, BTN_DOWNLOAD_FILES_KEY, BTN_CHAT_INFO_KEY, MENU_SETTINGS_KEY,
    BTN_MORE_ACTIONS_KEY, CONTEXT_REPLY_KEY, CONTEXT_FORWARD_KEY, CONTEXT_REACT_KEY, BTN_PLAY_KEY, BTN_OPEN_KEY,
    BTN_COMMENTS_KEY, BTN_STATS_KEY, BTN_REMIND_KEY, MSG_NOTHING_TO_PLAY_KEY, TOOLTIP_COMMAND_FORMAT_KEY,
    MENU_NEW_CHAT_KEY, MENU_GLOBAL_SEARCH_KEY, MENU_DOWNLOAD_FILES_KEY, MENU_CHAT_INFO_KEY, MENU_REPLY_KEY,
    MENU_FORWARD_KEY, MENU_REACT_KEY, MENU_OPEN_MEDIA_KEY, MENU_COMMENTS_KEY, MENU_MESSAGE_STATS_KEY, MENU_REMIND_KEY
)

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
            (BTN_MORE_ACTIONS_KEY, lambda event: self.on_message_context_menu(self.no_position(self.messages_list)), None),
        )

    def build_mouse_bar(self, entries, first=()):
        """A row that wraps onto more lines when the window is narrow; `first` are buttons made elsewhere."""
        # Without the default stretch of the last button on each line to the window's edge.
        bar = wx.WrapSizer(wx.HORIZONTAL, 0)
        for button in first:
            bar.Add(button, flag=wx.RIGHT|wx.BOTTOM, border=6)
        for label_key, handler, command in entries:
            button = OptionalButton(self.panel, label=self.i18n.get_string(label_key))
            button.Bind(wx.EVT_BUTTON, handler)
            button.command = command
            bar.Add(button, flag=wx.RIGHT|wx.BOTTOM, border=6)
            self.mouse_buttons.append(button)
        return bar

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

    def no_position(self, list_box):
        """A context-menu request as the Menu key makes it: on the selected item, wherever the mouse is."""
        return wx.ContextMenuEvent(wx.wxEVT_CONTEXT_MENU, list_box.GetId(), wx.DefaultPosition)

    def on_play_button(self, event):
        if not self.listen():
            self.notify(MSG_NOTHING_TO_PLAY_KEY)
