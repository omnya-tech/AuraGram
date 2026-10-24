"""The menus: the menu bar, which follows where the user is, a message's and the writing field's
menus, context menus, and every command's shortcut wherever its menu is.

Part of MainFrame (ui.main_frame), whose state and helpers its methods use."""
import wx
from core import key_conflicts, shortcuts
from core.settings import SHORTCUT_CONFLICTS_TOLD
from core.constants import (
    MENU_OPEN_CHAT_KEY, CATEGORY_GROUPS, MESSAGE_VIEW_MENTIONS, CATEGORY_BOTS, MENU_USER_GUIDE_KEY,
    MENU_ACCOUNTS_KEY, MENU_EXPORT_SETTINGS_KEY, MENU_IMPORT_SETTINGS_KEY, MENU_READ_MESSAGE_KEY,
    MENU_HELP_KEY, MENU_SHORTCUTS_KEY, MENU_MARK_KEY, MENU_UNMARK_ALL_KEY, MENU_NEW_GROUP_KEY,
    MENU_NEW_CHANNEL_KEY, MESSAGE_VIEWS, MENU_CHAT_VIEWS_KEY, MENU_NEW_POLL_KEY, MENU_REACT_KEY,
    MENU_SCHEDULE_KEY, SHORTCUT_SHOW_WINDOW, MSG_SHORTCUT_CONFLICTS_STARTUP_FORMAT_KEY, MENU_ABOUT_KEY,
    MENU_CHATS_KEY, MENU_NEW_CHAT_KEY, MENU_FIND_CHAT_KEY, MENU_FORWARD_KEY, MENU_PIN_KEY, MENU_SETTINGS_KEY,
    MENU_RECORD_KEY, MENU_SEARCH_MESSAGES_KEY, MENU_REPLY_KEY, MENU_EDIT_KEY, MENU_DELETE_KEY,
    MENU_SEND_FILE_KEY, MENU_SEARCH_KEY, MENU_FIND_KEY, MENU_FIND_NEXT_KEY, MENU_FILE_KEY, MENU_LOGOUT_KEY,
    MENU_EXIT_KEY, CONTEXT_CUT_KEY, CONTEXT_PASTE_KEY, CONTEXT_COPY_KEY, BTN_SELECT_ALL_KEY,
    MENU_BOT_START_KEY, MENU_BOT_COMMANDS_KEY, MENU_BOT_KEYBOARD_KEY, ATTACH_COMMANDS, MENU_GO_KEY,
    MENU_GO_CHATS_KEY, MENU_GO_MESSAGES_KEY, MENU_GO_INPUT_KEY, MENU_NEXT_UNREAD_KEY, MENU_NEXT_VIEW_KEY,
    MENU_PREVIOUS_VIEW_KEY, MENU_CHAT_INFO_KEY, MENU_CHAT_MANAGE_KEY, MENU_CHAT_READ_KEY,
    MENU_CHAT_FAVORITE_KEY, MENU_CHAT_PIN_KEY, MENU_CHAT_MUTE_KEY, MENU_CHAT_ARCHIVE_KEY, MENU_CHAT_CLEAR_KEY,
    MENU_CHAT_LEAVE_KEY, MENU_COPY_KEY, MENU_COPY_LINK_KEY, MENU_OPEN_MEDIA_KEY, MENU_SHOW_IN_FOLDER_KEY,
    MENU_SAVE_AS_KEY, MENU_OPEN_DOWNLOADS_KEY, MENU_CONNECTION_KEY, MENU_BUTTONS_KEY, MENU_SAVED_KEY,
    MENU_ADD_CONTACT_KEY, MENU_BLOCKED_KEY, MENU_CHAT_CONTACT_KEY, MENU_CHAT_BLOCK_KEY, MENU_CHAT_JOIN_KEY,
    MENU_GLOBAL_SEARCH_KEY, MENU_OPEN_LINK_KEY, MENU_SEND_STICKER_KEY, MENU_SEND_CONTACT_KEY,
    MENU_SEND_LOCATION_KEY, MENU_MENTION_KEY, MENU_COMMENTS_KEY, MENU_TOPICS_KEY, MENU_AUDIENCE_KEY,
    MENU_MESSAGE_STATS_KEY, MENU_TRANSLATE_KEY, MENU_STORIES_KEY, MENU_SEND_AS_KEY, MENU_POST_STORY_KEY,
    MENU_GO_TO_REPLY_KEY, MENU_GO_TO_DATE_KEY, MENU_SEARCH_ALL_KEY, MENU_SEND_SILENT_KEY, MENU_FOLDERS_KEY,
    MENU_MARK_ALL_READ_KEY, MENU_VOICE_SPEED_KEY, MENU_PLAYBACK_POSITION_KEY, MENU_POLL_VOTERS_KEY, MENU_CLOSE_POLL_KEY, MENU_REPORT_KEY, MENU_COPY_INVITE_KEY,
    MENU_DESCRIBE_IMAGE_KEY, MENU_CHECK_UPDATES_KEY, MENU_PROBLEM_REPORT_KEY, MENU_MESSAGE_SENDER_KEY,
    MENU_LICENSE_KEY, MENU_DOWNLOAD_FILES_KEY, MENU_DOWNLOAD_STATUS_KEY, MENU_CANCEL_DOWNLOADS_KEY,
    MENU_EXPORT_CHAT_KEY, MENU_CHAT_TONE_KEY, MENU_REMIND_KEY, MENU_REMINDERS_KEY, MENU_CANCEL_UPLOAD_KEY,
    MENU_EXPORT_SHORTCUTS_KEY,
)

# Stands for a chat that has every kind of entry, to gather every command the menus can hold.
EVERY_CHAT = object()


class MenuBarMixin:
    def message_entries(self):
        """The commands for the selected message, which its own menu offers (the Applications key on it)
        and which answer their shortcuts from anywhere in the window. None draws a line between groups."""
        return (
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
            (MENU_SHOW_IN_FOLDER_KEY, self.on_show_in_folder_menu),
            (MENU_BUTTONS_KEY, self.on_buttons_menu),
            (MENU_OPEN_LINK_KEY, self.on_open_link_menu),
            (MENU_COMMENTS_KEY, self.on_comments_menu),
            (MENU_AUDIENCE_KEY, self.on_audience_menu),
            (MENU_MESSAGE_STATS_KEY, self.on_message_stats_menu),
            (MENU_VOICE_SPEED_KEY, self.on_voice_speed_menu),
            (MENU_PLAYBACK_POSITION_KEY, self.on_playback_position_menu),
            (MENU_POLL_VOTERS_KEY, self.on_poll_voters_menu),
            (MENU_CLOSE_POLL_KEY, self.on_close_poll_menu),
            (MENU_REPORT_KEY, self.on_report_menu),
            None,
            (MENU_MARK_KEY, self.on_mark_menu),
            (MENU_UNMARK_ALL_KEY, self.on_unmark_all_menu),
            None,
            (MENU_REMIND_KEY, self.on_remind_menu),
        )

    def send_entries(self):
        """What can go with a message, or how it goes: the menu of the writing field, and of the
        Attach button. None draws a line between groups of entries."""
        return (
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
            None,
            (MENU_BOT_START_KEY, self.on_bot_start_menu),
            (MENU_BOT_COMMANDS_KEY, self.on_bot_commands_menu),
            (MENU_BOT_KEYBOARD_KEY, self.on_bot_keyboard_menu),
            None,
            (MENU_CANCEL_UPLOAD_KEY, self.on_cancel_upload_menu),
        )

    def on_attach(self, event):
        # Only what is attached to a message: the button is named for that.
        self.show_send_menu(only=ATTACH_COMMANDS)

    def on_input_context_menu(self, event):
        self.show_send_menu(with_editing=True)

    def show_send_menu(self, with_editing=False, only=None):
        """The send commands, each with its shortcut; in the writing field, the usual editing ones after them,
        since this menu takes the place of the one Windows gives a text field."""
        table = shortcuts.current(self.settings)
        menu = wx.Menu()
        entries = [entry for entry in self.send_entries() if only is None or (entry is not None and entry[0] in only)]
        # Only what the open chat's kind has: someone to mention or a name to send as in a group, bots in a bot's chat or a group.
        category = self.current_dialog().get("category") if self.current_dialog_id is not None else None
        missing = set()
        if category != CATEGORY_GROUPS:
            missing |= {MENU_MENTION_KEY, MENU_SEND_AS_KEY}
        if category not in (CATEGORY_GROUPS, CATEGORY_BOTS):
            missing |= {MENU_BOT_START_KEY, MENU_BOT_COMMANDS_KEY, MENU_BOT_KEYBOARD_KEY}
        entries = [entry for entry in entries if entry is None or entry[0] not in missing]
        if with_editing:
            entries += [None] + [
                (CONTEXT_CUT_KEY, lambda event: self.message_input.Cut()),
                (CONTEXT_COPY_KEY, lambda event: self.message_input.Copy()),
                (CONTEXT_PASTE_KEY, lambda event: self.paste_files() or self.message_input.Paste()),
                (BTN_SELECT_ALL_KEY, lambda event: self.message_input.SelectAll()),
            ]
        separator_due = False
        for entry in entries:
            if entry is None:
                # One line between groups, never two in a row nor one at an end.
                separator_due = menu.GetMenuItemCount() > 0
                continue
            if separator_due:
                menu.AppendSeparator()
                separator_due = False
            label_key, handler = entry
            label = self.i18n.get_string(label_key)
            shortcut = table.get(label_key)
            item = menu.Append(wx.ID_ANY, label + "\t" + shortcut if shortcut else label)
            menu.Bind(wx.EVT_MENU, handler, item)
        self.PopupMenu(menu)
        menu.Destroy()

    def init_menu(self):
        """The menu bar: what can be done from where the user is. On the list of chats, the commands
        for chats; inside a chat, those for that chat, and only those its kind has. Every command keeps
        its shortcut wherever the user is (apply_shortcuts), and the shortcuts guide lists them all."""
        self.refresh_menu_bar()

    def menu_layout(self, chat):
        """[(menu title, [(command, handler) or None, ...]), ...] for the list of chats (`chat` None),
        inside `chat`, or, for EVERY_CHAT, with every entry any chat could have."""
        every = chat is EVERY_CHAT
        # Whether `chat` has something, asked of a function so EVERY_CHAT, which has everything, is never looked into.
        has = lambda condition: every or bool(condition())
        on_chat = self.on_chat_menu
        file_menu = (MENU_FILE_KEY, (
            (MENU_SETTINGS_KEY, self.on_settings_menu, wx.ID_PREFERENCES),
            (MENU_OPEN_DOWNLOADS_KEY, self.on_open_downloads_menu),
            (MENU_DOWNLOAD_STATUS_KEY, self.on_download_status_menu),
            (MENU_CANCEL_DOWNLOADS_KEY, self.on_cancel_downloads_menu),
            None,
            (MENU_ACCOUNTS_KEY, self.on_accounts_menu),
            (MENU_EXPORT_SETTINGS_KEY, self.on_export_settings_menu),
            (MENU_IMPORT_SETTINGS_KEY, self.on_import_settings_menu),
            (MENU_LOGOUT_KEY, self.on_logout_menu),
            None,
            (MENU_EXIT_KEY, self.on_exit_menu, wx.ID_EXIT),
        ))
        help_menu = (MENU_HELP_KEY, (
            (MENU_USER_GUIDE_KEY, self.on_user_guide_menu, wx.ID_HELP),
            (MENU_SHORTCUTS_KEY, self.on_shortcuts_menu),
            (MENU_EXPORT_SHORTCUTS_KEY, self.on_export_shortcuts_menu),
            (MENU_CONNECTION_KEY, self.on_connection_menu),
            (MENU_CHECK_UPDATES_KEY, lambda event: self.check_for_updates(quiet=False)),
            (MENU_PROBLEM_REPORT_KEY, self.on_problem_report_menu),
            (MENU_ABOUT_KEY, self.on_about_menu, wx.ID_ABOUT),
            (MENU_LICENSE_KEY, self.on_license_menu),
        ))
        # What can be done to one chat: the one selected in the list, or the one open.
        chat_entries = (
            (MENU_CHAT_INFO_KEY, lambda event: on_chat(self.show_chat_info)),
            (MENU_CHAT_MANAGE_KEY, lambda event: on_chat(self.manage_chat)) if chat is None or has(lambda: chat.get("is_admin")) else None,
            (MENU_COPY_INVITE_KEY, lambda event: on_chat(self.copy_invite_link)) if chat is None or has(lambda: not self.is_private_chat(chat)) else None,
            (MENU_CHAT_JOIN_KEY, lambda event: on_chat(self.join_dialog)) if chat is None or has(lambda: not chat.get("joined", True)) else None,
            None,
            (MENU_CHAT_READ_KEY, lambda event: on_chat(self.toggle_dialog_read)),
            (MENU_CHAT_PIN_KEY, lambda event: on_chat(lambda dialog: self.set_chat_pinned(dialog, not dialog["pinned"]))),
            (MENU_CHAT_FAVORITE_KEY, lambda event: on_chat(self.toggle_favorite)),
            (MENU_CHAT_MUTE_KEY, lambda event: on_chat(self.toggle_dialog_muted)),
            (MENU_CHAT_TONE_KEY, lambda event: on_chat(self.on_chat_tone)),
            (MENU_CHAT_ARCHIVE_KEY, lambda event: on_chat(lambda dialog: self.set_chat_archived(dialog, not dialog["archived"]))),
            (MENU_EXPORT_CHAT_KEY, lambda event: on_chat(self.on_export_chat)),
            (MENU_DOWNLOAD_FILES_KEY, self.on_download_files_menu),
            (MENU_CHAT_CONTACT_KEY, lambda event: on_chat(self.toggle_contact)) if chat is None or has(lambda: self.is_person(chat)) else None,
            (MENU_CHAT_BLOCK_KEY, lambda event: on_chat(self.toggle_blocked)) if chat is None or has(lambda: self.is_private_chat(chat)) else None,
            None,
            # Last, away from the everyday entries: these cannot be undone.
            (MENU_CHAT_CLEAR_KEY, lambda event: on_chat(self.clear_history)),
            (MENU_CHAT_LEAVE_KEY, lambda event: on_chat(lambda dialog: self.leave_chat(dialog, self.is_private_chat(dialog)))),
        )
        if chat is None:
            return [
                file_menu,
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
                    (MENU_REMINDERS_KEY, self.on_reminders_menu),
                    (MENU_NEXT_UNREAD_KEY, self.on_next_unread_menu),
                    None,
                ) + chat_entries),
                (MENU_CHAT_VIEWS_KEY, (
                    (MENU_NEXT_VIEW_KEY, lambda event: self.cycle_view(1)),
                    (MENU_PREVIOUS_VIEW_KEY, lambda event: self.cycle_view(-1)),
                    None,
                    (MENU_STORIES_KEY, self.on_stories_menu),
                    (MENU_POST_STORY_KEY, self.on_post_story_menu),
                )),
                (MENU_SEARCH_KEY, (
                    (MENU_FIND_KEY, self.on_find_menu),
                    (MENU_FIND_NEXT_KEY, self.on_find_next_menu),
                    (MENU_SEARCH_ALL_KEY, self.on_search_all_menu),
                    (MENU_GLOBAL_SEARCH_KEY, self.on_global_search_menu),
                )),
                help_menu,
            ]
        is_group = has(lambda: chat.get("category") == CATEGORY_GROUPS)
        views = tuple(
            (view, lambda event, view=view: self.open_message_view(view)) for view in MESSAGE_VIEWS
            # Only a group has others in it to mention this account.
            if view != MESSAGE_VIEW_MENTIONS or is_group
        )
        return [
            file_menu,
            (MENU_OPEN_CHAT_KEY, chat_entries),
            (MENU_CHAT_VIEWS_KEY, views + (
                (None, (MENU_TOPICS_KEY, self.on_topics_menu)) if has(lambda: chat.get("is_forum")) else ()
            )),
            (MENU_GO_KEY, (
                (MENU_GO_CHATS_KEY, lambda event: self.close_chat() if self.in_chat else self.dialogs_list.SetFocus()),
                (MENU_GO_MESSAGES_KEY, lambda event: self.messages_list.SetFocus()),
                (MENU_GO_INPUT_KEY, lambda event: self.message_input.SetFocus()),
                None,
                (MENU_GO_TO_DATE_KEY, self.on_go_to_date_menu),
                (MENU_GO_TO_REPLY_KEY, self.on_go_to_reply_menu),
                (MENU_NEXT_UNREAD_KEY, self.on_next_unread_menu),
            )),
            (MENU_SEARCH_KEY, (
                (MENU_FIND_KEY, self.on_find_menu),
                (MENU_FIND_NEXT_KEY, self.on_find_next_menu),
                (MENU_SEARCH_MESSAGES_KEY, self.on_search_messages_menu),
                (MENU_SEARCH_ALL_KEY, self.on_search_all_menu),
                (MENU_GLOBAL_SEARCH_KEY, self.on_global_search_menu),
            )),
            help_menu,
        ]

    def all_commands(self):
        """Every command with its handler, wherever it is offered: in the menu bar on either screen,
        in a message's menu, or in the writing field's."""
        commands = {}
        for layout in (self.menu_layout(None), self.menu_layout(EVERY_CHAT)):
            for title, entries in layout:
                for entry in entries:
                    if entry is not None:
                        commands.setdefault(entry[0], entry[1])
        for entry in self.message_entries() + self.send_entries():
            if entry is not None:
                commands.setdefault(entry[0], entry[1])
        return commands

    def refresh_menu_bar_if_alive(self):
        if self:
            self.refresh_menu_bar()

    def refresh_menu_bar(self):
        """Put up the menu bar for where the user is now: the list of chats, or the chat open, as it is now."""
        chat = self.current_dialog() if self.in_chat and self.current_dialog_id is not None else None
        self.menu_items = {}
        menu_bar = wx.MenuBar()
        for title_key, entries in self.menu_layout(chat):
            menu = wx.Menu()
            separator_due = False
            for entry in entries:
                if entry is None:
                    # One line between groups, never two in a row nor one at an end.
                    separator_due = menu.GetMenuItemCount() > 0
                    continue
                if separator_due:
                    menu.AppendSeparator()
                    separator_due = False
                label_key, handler, *item_id = entry
                item = menu.Append(item_id[0] if item_id else wx.ID_ANY, self.i18n.get_string(label_key))
                self.Bind(wx.EVT_MENU, handler, item)
                self.menu_items[label_key] = item
            menu_bar.Append(menu, self.i18n.get_string(title_key))
        old = self.GetMenuBar()
        self.SetMenuBar(menu_bar)
        if old is not None:
            old.Destroy()
        self.apply_shortcuts()

    def apply_shortcuts(self):
        """Give every menu entry the shortcut the user has for it; wx reads it from after the tab in the label."""
        table = shortcuts.current(self.settings)
        for command, item in self.menu_items.items():
            label = self.i18n.get_string(command)
            item.SetItemLabel(label + "\t" + table[command] if table[command] else label)
        # Commands not in the menu bar where the user is now still answer their shortcuts, from anywhere.
        self.menu_less_shortcuts = {
            table[command]: handler for command, handler in self.all_commands().items()
            if command not in self.menu_items and table.get(command)
        }
        self.menu_shortcuts = ({table[command] for command in self.menu_items} | set(self.menu_less_shortcuts)) - {""}
        self.update_mouse_tooltips()

    def show_window_shortcut(self):
        return shortcuts.current(self.settings)[SHORTCUT_SHOW_WINDOW]

    def check_shortcuts_once(self):
        """Look, at most once a run, for shortcuts that other programs on this computer hold, and offer
        to change them. The same finding is not brought up again at the next start."""
        if not self or self.shortcuts_checked:
            return
        self.shortcuts_checked = True
        table = shortcuts.current(self.settings)
        conflicts = key_conflicts.find(table.values())
        if sorted(conflicts) == self.settings.get(SHORTCUT_CONFLICTS_TOLD):
            return
        self.settings.set(SHORTCUT_CONFLICTS_TOLD, sorted(conflicts))
        self.settings.save()
        if conflicts and self.confirm(self.i18n.get_string(MSG_SHORTCUT_CONFLICTS_STARTUP_FORMAT_KEY).format(
            conflicts=shortcuts.conflict_lines(self.i18n, table, conflicts)
        )):
            self.open_settings(on_shortcuts=True)

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
