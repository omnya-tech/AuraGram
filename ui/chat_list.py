import wx
from core.speech import speak
from ui.chat_info_dialog import ChatInfoDialog
from core.chat_views import build_views
from core.constants import (
    CATEGORY_GROUPS, CATEGORY_BROADCASTS, CONTEXT_LEAVE_KEY, CONTEXT_DELETE_CHAT_KEY,
    MSG_CONFIRM_LEAVE_KEY, MSG_CONFIRM_DELETE_CHAT_KEY, MSG_LEFT_KEY, MSG_VIEW_COUNT_FORMAT_KEY,
    MSG_CHOOSE_CONTACT_KEY, MSG_NO_CONTACTS_KEY, MSG_FIND_CHAT_PROMPT_KEY, CONTEXT_INFO_KEY,
    MSG_CHAT_SAVED_KEY, CONTEXT_OPEN_KEY, CONTEXT_MARK_READ_KEY, CONTEXT_MUTE_KEY,
    CONTEXT_UNMUTE_KEY, MSG_MARKED_READ_KEY, MSG_MUTED_KEY, MSG_UNMUTED_KEY, DIALOGS_LIMIT,
    MSG_LOAD_MORE_DIALOGS_KEY, MSG_FIND_PROMPT_KEY, MSG_NOT_FOUND_KEY, APP_TITLE_KEY,
    MSG_LOADING_KEY, STATUS_READY_KEY, SENDER_YOU_KEY, MUTE_DURATIONS,
    CONTEXT_MARK_UNREAD_KEY, CONTEXT_PIN_CHAT_KEY, CONTEXT_UNPIN_CHAT_KEY, CONTEXT_ARCHIVE_KEY,
    CONTEXT_UNARCHIVE_KEY, CONTEXT_CLEAR_HISTORY_KEY, CONTEXT_COPY_INVITE_KEY, MSG_MARKED_UNREAD_KEY, MSG_CHAT_PINNED_KEY,
    MSG_CHAT_UNPINNED_KEY, MSG_ARCHIVED_KEY, MSG_UNARCHIVED_KEY, MSG_CONFIRM_CLEAR_HISTORY_KEY,
    MSG_HISTORY_CLEARED_KEY, DIALOG_FORMAT_KEY, DIALOG_PINNED_KEY, DIALOG_MARKED_UNREAD_KEY,
    DIALOG_UNREAD_COUNT_FORMAT_KEY, PREVIEW_SENDER_FORMAT_KEY,
    MSG_NEW_CHAT_NAME_PROMPT_KEY, MSG_NEW_CHAT_ABOUT_PROMPT_KEY, MSG_CHAT_CREATED_FORMAT_KEY,
    MSG_NO_CHAT_SELECTED_KEY, MSG_NO_UNREAD_KEY, MSG_CHOOSE_MUTE_KEY,
    CATEGORY_CONTACTS, CATEGORY_NON_CONTACTS, CONTEXT_ADD_CONTACT_KEY, CONTEXT_DELETE_CONTACT_KEY,
    CONTEXT_BLOCK_KEY, CONTEXT_JOIN_KEY, MSG_CONTACT_PHONE_PROMPT_KEY, MSG_CONTACT_NAME_PROMPT_KEY,
    MSG_CONTACT_ADDED_FORMAT_KEY, MSG_CONTACT_DELETED_FORMAT_KEY, MSG_CONFIRM_DELETE_CONTACT_FORMAT_KEY,
    MSG_CONFIRM_BLOCK_FORMAT_KEY, MSG_CONFIRM_UNBLOCK_FORMAT_KEY, MSG_BLOCKED_FORMAT_KEY,
    MSG_UNBLOCKED_FORMAT_KEY, MSG_NO_BLOCKED_KEY, MSG_CHOOSE_BLOCKED_KEY, MSG_NOT_A_PERSON_KEY,
    MSG_GLOBAL_SEARCH_PROMPT_KEY, MSG_GLOBAL_SEARCH_RESULTS_KEY, MSG_GLOBAL_SEARCH_EMPTY_KEY,
    MSG_CONFIRM_JOIN_FORMAT_KEY, MSG_JOINED_FORMAT_KEY, MSG_ALREADY_JOINED_KEY, MSG_MANAGE_FOLDERS_KEY,
    FOLDER_NEW_KEY, MSG_FOLDER_ACTION_FORMAT_KEY, FOLDER_EDIT_KEY, FOLDER_DELETE_KEY,
    MSG_FOLDER_NAME_PROMPT_KEY, MSG_FOLDER_RULES_PROMPT_KEY, FOLDER_RULE_KEY_PREFIX, FOLDER_EXCLUSIONS,
    MSG_FOLDER_CHATS_PROMPT_KEY, ERR_FOLDER_EMPTY_KEY, MSG_CONFIRM_DELETE_FOLDER_FORMAT_KEY,
    MSG_FOLDERS_SAVED_KEY, FIRST_FOLDER_ID, FOLDER_CATEGORIES, MSG_CONFIRM_MARK_ALL_READ_FORMAT_KEY,
    MSG_ALL_READ_KEY, MSG_NOTHING_UNREAD_KEY, MSG_INVITE_COPIED_KEY
)

class ChatListMixin:
    """The chat list: loading, views and folders, opening chats, and per-chat actions.

    Mixed into MainFrame, which owns the widgets and the shared state.
    """

    def load_dialogs(self):
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.load_dialogs(self.on_ui_thread(self.show_dialogs), self.dialogs_limit)

    def show_dialogs(self, dialogs):
        self.all_dialogs = dialogs
        for dialog in dialogs:
            # Written on another device, or here before the app was last closed.
            if dialog["draft"]:
                self.drafts.setdefault(dialog["id"], dialog["draft"])
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
        # A folder may have been deleted from under the view that was showing it.
        self.view_index = min(self.view_index, len(self.views) - 1)
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

    def load_more_dialogs(self):
        self.dialogs_limit += DIALOGS_LIMIT
        self.load_dialogs()

    def format_dialog(self, dialog):
        """One row of the chat list: name, state, then the latest message whether read or not."""
        details = []
        if dialog["unread"]:
            details.append(self.i18n.get_string(DIALOG_UNREAD_COUNT_FORMAT_KEY).format(count=dialog["unread"]))
        elif dialog["marked_unread"]:
            details.append(self.i18n.get_string(DIALOG_MARKED_UNREAD_KEY))
        if dialog["pinned"]:
            details.append(self.i18n.get_string(DIALOG_PINNED_KEY))
        preview = self.dialog_preview(dialog)
        return self.i18n.get_string(DIALOG_FORMAT_KEY).format(
            title=dialog["title"],
            details="".join("، " + detail for detail in details),
            preview=". " + preview if preview else ""
        )

    def dialog_preview(self, dialog):
        message = dialog["last_message"]
        if message is None:
            return ""
        text = self.message_snippet(message)
        if message["outgoing"]:
            sender = self.i18n.get_string(SENDER_YOU_KEY)
        elif dialog["category"] == CATEGORY_GROUPS:
            # In a group the name of the chat does not say who wrote.
            sender = message["sender"]
        else:
            sender = ""
        if not sender:
            return text
        return self.i18n.get_string(PREVIEW_SENDER_FORMAT_KEY).format(sender=sender, text=text)

    def refresh_dialog_row(self, dialog):
        index = self.find_dialog_index(dialog["id"])
        # It may be hidden by the current view.
        if index != wx.NOT_FOUND:
            self.dialogs_list.SetString(index, self.format_dialog(dialog))

    def find_dialog_index(self, dialog_id):
        for index, dialog in enumerate(self.dialogs):
            if dialog["id"] == dialog_id:
                return index
        return wx.NOT_FOUND

    def find_known_dialog(self, dialog_id):
        """A chat by id among all loaded chats, including those the current view hides."""
        for dialog in self.all_dialogs:
            if dialog["id"] == dialog_id:
                return dialog
        return None

    def selected_dialog(self):
        index = self.dialogs_list.GetSelection()
        if 0 <= index < len(self.dialogs):
            return self.dialogs[index]
        return None

    def current_dialog(self):
        """The open chat; before any is open, a stand-in with no special rights."""
        return self.find_known_dialog(self.current_dialog_id) or {
            "can_delete_others": False, "can_pin": False, "is_channel": False,
            "can_send": False, "has_links": False,
        }

    def set_unread(self, dialog_id, count):
        dialog = self.find_known_dialog(dialog_id)
        if dialog is None or dialog["unread"] == count:
            return
        dialog["unread"] = count
        index = self.find_dialog_index(dialog_id)
        # It may be open while the current view does not list it.
        if index != wx.NOT_FOUND:
            self.dialogs_list.SetString(index, self.format_dialog(dialog))

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

    def on_open_dialog(self, event):
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
        self.keep_draft()
        self.unread_on_open = self.dialogs[index]["unread"]
        self.current_dialog_id = dialog_id
        # From here on the window is this chat and nothing else, until it is left.
        self.show_chat_screen(True)
        self.show_chat_name(self.dialogs[index])
        self.set_compose()
        self.message_input.SetValue(self.drafts.get(dialog_id, ""))
        self.messages = []
        self.has_older = False
        self.messages_list.Clear()
        self.preview_text.ChangeValue("")
        self.enable_chat(False)
        self.load_messages(focus_messages)

    def keep_draft(self):
        """Remember what is typed for the chat being left, so it is there on coming back."""
        # While editing, the field holds an old message's text, not something new to keep.
        if self.current_dialog_id is None or self.editing is not None:
            return
        text = self.message_input.GetValue()
        before = self.drafts.get(self.current_dialog_id, "")
        if text.strip():
            self.drafts[self.current_dialog_id] = text
        else:
            text = ""
            self.drafts.pop(self.current_dialog_id, None)
        if text != before:
            self.telegram_manager.save_draft(self.current_dialog_id, text)

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

    def on_saved_messages_menu(self, event):
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.open_saved_messages(self.on_ui_thread(self.open_chat))

    def on_find_chat_menu(self, event):
        with wx.TextEntryDialog(
            self, self.i18n.get_string(MSG_FIND_CHAT_PROMPT_KEY), self.i18n.get_string(APP_TITLE_KEY)
        ) as find_dialog:
            if find_dialog.ShowModal() != wx.ID_OK:
                return
            query = find_dialog.GetValue().strip()
        if query:
            self.open_link(query)

    def open_link(self, text):
        """Open what a username, phone number, t.me address or invitation link leads to."""
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.resolve_link(text, self.on_ui_thread(self.on_link_resolved))

    def on_link_resolved(self, result):
        self.set_status(STATUS_READY_KEY)
        if result["chat"] is not None:
            self.open_chat(result["chat"])
            return
        # An invitation: opening it means joining, so ask first.
        invite_hash, title = result["invite"]
        if self.confirm(self.i18n.get_string(MSG_CONFIRM_JOIN_FORMAT_KEY).format(title=title)):
            self.telegram_manager.join_invite(invite_hash, self.on_ui_thread(self.on_joined))

    def on_joined(self, chat, dialog=None):
        if dialog is not None:
            # Already in the list: keep its row, with what joining has changed.
            dialog.update(joined=chat["joined"], can_send=chat["can_send"])
            if dialog["id"] == self.current_dialog_id:
                self.enable_chat(True)
        else:
            self.open_chat(chat)
        self.announce(self.i18n.get_string(MSG_JOINED_FORMAT_KEY).format(title=chat["title"]))

    def join_dialog(self, dialog):
        if dialog["joined"]:
            self.notify(MSG_ALREADY_JOINED_KEY)
        else:
            self.telegram_manager.join_chat(dialog["id"], self.on_ui_thread(self.on_joined, dialog))

    def pick(self, prompt, choices):
        """Index picked from a list; None if the user backs out."""
        with wx.SingleChoiceDialog(self, prompt, self.i18n.get_string(APP_TITLE_KEY), choices) as choice_dialog:
            if choice_dialog.ShowModal() != wx.ID_OK:
                return None
            return choice_dialog.GetSelection()

    def pick_many(self, prompt, choices, selected):
        """Indexes ticked in a list that starts with `selected` ticked; None if the user backs out."""
        with wx.MultiChoiceDialog(self, prompt, self.i18n.get_string(APP_TITLE_KEY), choices) as choice_dialog:
            choice_dialog.SetSelections(selected)
            if choice_dialog.ShowModal() != wx.ID_OK:
                return None
            return list(choice_dialog.GetSelections())

    def on_folders_menu(self, event):
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.load_folders(self.on_ui_thread(self.manage_folders))

    def manage_folders(self, folders):
        self.set_status(STATUS_READY_KEY)
        text = self.i18n.get_string
        index = self.pick(text(MSG_MANAGE_FOLDERS_KEY), [text(FOLDER_NEW_KEY)] + [folder["title"] for folder in folders])
        if index is None:
            return
        if index == 0:
            # Numbered after the last one there is.
            new_id = max([folder["id"] for folder in folders] + [FIRST_FOLDER_ID - 1]) + 1
            self.edit_folder({
                "id": new_id, "title": "", "categories": set(), "include_ids": set(),
                **{flag: False for flag in FOLDER_EXCLUSIONS},
            })
            return
        folder = folders[index - 1]
        action = self.pick(
            text(MSG_FOLDER_ACTION_FORMAT_KEY).format(title=folder["title"]), [text(FOLDER_EDIT_KEY), text(FOLDER_DELETE_KEY)]
        )
        if action == 0:
            self.edit_folder(folder)
        elif action == 1 and self.confirm(text(MSG_CONFIRM_DELETE_FOLDER_FORMAT_KEY).format(title=folder["title"])):
            self.telegram_manager.delete_folder(folder["id"], self.on_ui_thread(self.on_folders_changed))

    def edit_folder(self, folder):
        """Ask for a folder's name, its rules and its hand-picked chats, then save it."""
        text = self.i18n.get_string
        title = self.ask_text(MSG_FOLDER_NAME_PROMPT_KEY, folder["title"])
        if title is None:
            return
        rules = list(FOLDER_CATEGORIES) + list(FOLDER_EXCLUSIONS)
        ticked = self.pick_many(
            text(MSG_FOLDER_RULES_PROMPT_KEY), [text(FOLDER_RULE_KEY_PREFIX + rule) for rule in rules],
            [i for i, rule in enumerate(rules) if rule in folder["categories"] or folder.get(rule)]
        )
        if ticked is None:
            return
        chosen_rules = {rules[index] for index in ticked}
        chats = self.all_dialogs
        included = self.pick_many(
            text(MSG_FOLDER_CHATS_PROMPT_KEY), [chat["title"] for chat in chats],
            [i for i, chat in enumerate(chats) if chat["id"] in folder["include_ids"]]
        )
        if included is None:
            return
        categories = chosen_rules & set(FOLDER_CATEGORIES)
        if not title or not (categories or included):
            # Telegram refuses a folder nothing can ever be in.
            self.show_error(ERR_FOLDER_EMPTY_KEY)
            return
        self.telegram_manager.save_folder(
            {
                "id": folder["id"], "title": title, "categories": categories,
                "include_ids": {chats[index]["id"] for index in included},
                **{flag: flag in chosen_rules for flag in FOLDER_EXCLUSIONS},
            },
            {chat["id"] for chat in chats}, self.on_ui_thread(self.on_folders_changed)
        )

    def on_folders_changed(self, result):
        self.notify(MSG_FOLDERS_SAVED_KEY)
        # The views are made from the folders: read them back as Telegram now has them.
        self.telegram_manager.load_folders(self.on_ui_thread(self.show_folders))

    def on_mark_all_read_menu(self, event):
        unread = [dialog for dialog in self.all_dialogs if dialog["unread"] or dialog["marked_unread"]]
        if not unread:
            self.notify(MSG_NOTHING_UNREAD_KEY)
            return
        if not self.confirm(self.i18n.get_string(MSG_CONFIRM_MARK_ALL_READ_FORMAT_KEY).format(count=len(unread))):
            return
        self.telegram_manager.mark_all_read([dialog["id"] for dialog in unread])
        for dialog in unread:
            if dialog["marked_unread"]:
                # The hand-set flag is separate from the messages and has to be cleared too.
                self.telegram_manager.set_marked_unread(dialog["id"], False, lambda result, error_key: None)
            dialog["unread"], dialog["marked_unread"] = 0, False
        # Some views hold only unread chats: the list itself may be shorter now.
        self.render_dialogs()
        self.notify(MSG_ALL_READ_KEY)

    def on_global_search_menu(self, event):
        query = self.ask_text(MSG_GLOBAL_SEARCH_PROMPT_KEY)
        if query:
            self.set_status(MSG_LOADING_KEY)
            self.telegram_manager.search_public(query, self.on_ui_thread(self.show_global_results))

    def show_global_results(self, chats):
        self.set_status(STATUS_READY_KEY)
        if not chats:
            self.notify(MSG_GLOBAL_SEARCH_EMPTY_KEY)
            return
        chat = self.choose_chat(MSG_GLOBAL_SEARCH_RESULTS_KEY, chats)
        if chat is not None:
            self.open_chat(chat)

    def confirm(self, question):
        answer = wx.MessageBox(
            question, self.i18n.get_string(APP_TITLE_KEY), wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self
        )
        return answer == wx.YES

    def is_person(self, dialog):
        return dialog["category"] in (CATEGORY_CONTACTS, CATEGORY_NON_CONTACTS)

    def on_add_contact_menu(self, event):
        phone = self.ask_text(MSG_CONTACT_PHONE_PROMPT_KEY)
        name = self.ask_text(MSG_CONTACT_NAME_PROMPT_KEY) if phone else None
        if name:
            self.set_status(MSG_LOADING_KEY)
            self.telegram_manager.add_contact_by_phone(phone, name, self.on_ui_thread(self.on_contact_imported))

    def on_contact_imported(self, chat):
        self.set_status(STATUS_READY_KEY)
        self.open_chat(chat)
        self.announce(self.i18n.get_string(MSG_CONTACT_ADDED_FORMAT_KEY).format(name=chat["title"]))

    def toggle_contact(self, dialog):
        if not self.is_person(dialog):
            self.notify(MSG_NOT_A_PERSON_KEY)
        elif dialog["category"] == CATEGORY_CONTACTS:
            if self.confirm(self.i18n.get_string(MSG_CONFIRM_DELETE_CONTACT_FORMAT_KEY).format(name=dialog["title"])):
                self.telegram_manager.delete_contact(dialog["id"], self.on_ui_thread(
                    self.on_contact_changed, dialog, CATEGORY_NON_CONTACTS, MSG_CONTACT_DELETED_FORMAT_KEY
                ))
        else:
            # Offered as Telegram shows them; the user may prefer their own name for the person.
            name = self.ask_text(MSG_CONTACT_NAME_PROMPT_KEY, dialog["title"])
            if name:
                self.telegram_manager.add_contact(dialog["id"], name, self.on_ui_thread(
                    self.on_contact_changed, dialog, CATEGORY_CONTACTS, MSG_CONTACT_ADDED_FORMAT_KEY
                ))

    def on_contact_changed(self, result, dialog, category, message_key):
        dialog["category"] = category
        self.announce(self.i18n.get_string(message_key).format(name=dialog["title"]))

    def toggle_blocked(self, dialog):
        if not self.is_private_chat(dialog):
            self.notify(MSG_NOT_A_PERSON_KEY)
            return
        # The chat list does not know who is blocked, so ask before offering the opposite.
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.load_blocked_state(dialog["id"], self.on_ui_thread(self.on_blocked_state, dialog))

    def on_blocked_state(self, blocked, dialog):
        self.set_status(STATUS_READY_KEY)
        key = MSG_CONFIRM_UNBLOCK_FORMAT_KEY if blocked else MSG_CONFIRM_BLOCK_FORMAT_KEY
        if self.confirm(self.i18n.get_string(key).format(name=dialog["title"])):
            self.set_blocked(dialog, not blocked)

    def set_blocked(self, chat, blocked):
        message_key = MSG_BLOCKED_FORMAT_KEY if blocked else MSG_UNBLOCKED_FORMAT_KEY
        self.telegram_manager.set_blocked(chat["id"], blocked, self.on_ui_thread(
            lambda result: self.announce(self.i18n.get_string(message_key).format(name=chat["title"]))
        ))

    def on_blocked_menu(self, event):
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.load_blocked(self.on_ui_thread(self.show_blocked))

    def show_blocked(self, chats):
        self.set_status(STATUS_READY_KEY)
        if not chats:
            self.notify(MSG_NO_BLOCKED_KEY)
            return
        chat = self.choose_chat(MSG_CHOOSE_BLOCKED_KEY, chats)
        if chat is not None:
            self.set_blocked(chat, False)

    def ask_text(self, prompt_key, value=""):
        """One line of text from the user, starting from `value`; None if they cancel."""
        with wx.TextEntryDialog(
            self, self.i18n.get_string(prompt_key), self.i18n.get_string(APP_TITLE_KEY), value=value
        ) as text_dialog:
            if text_dialog.ShowModal() != wx.ID_OK:
                return None
            return text_dialog.GetValue().strip()

    def create_chat(self, is_channel):
        title = self.ask_text(MSG_NEW_CHAT_NAME_PROMPT_KEY)
        if not title:
            return
        about = self.ask_text(MSG_NEW_CHAT_ABOUT_PROMPT_KEY)
        # Cancelling the description cancels the whole thing; leaving it empty does not.
        if about is None:
            return
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.create_chat(title, about, is_channel, self.on_ui_thread(self.on_chat_created))

    def on_chat_created(self, chat):
        self.open_chat(chat)
        self.announce(self.i18n.get_string(MSG_CHAT_CREATED_FORMAT_KEY).format(title=chat["title"]))

    def on_find_menu(self, event):
        # Looking for a chat is done in the list of chats.
        self.back_to_list()
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
            self.back_to_list()
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

    def on_dialog_context_menu(self, event):
        self.select_item_under_mouse(self.dialogs_list, event)
        dialog = self.selected_dialog()
        if dialog is None:
            return
        entries = [(CONTEXT_OPEN_KEY, self.on_open_dialog)]
        # Each entry names the change it makes, so the menu also tells the chat's current state.
        if dialog["unread"] or dialog["marked_unread"]:
            entries.append((CONTEXT_MARK_READ_KEY, lambda event: self.mark_dialog_read(dialog)))
        else:
            entries.append((CONTEXT_MARK_UNREAD_KEY, lambda event: self.mark_dialog_unread(dialog)))
        pin_key = CONTEXT_UNPIN_CHAT_KEY if dialog["pinned"] else CONTEXT_PIN_CHAT_KEY
        entries.append((pin_key, lambda event: self.set_chat_pinned(dialog, not dialog["pinned"])))
        if dialog["muted"]:
            entries.append((CONTEXT_UNMUTE_KEY, lambda event: self.set_dialog_muted(dialog, 0)))
        else:
            entries.append((CONTEXT_MUTE_KEY, [
                (label_key, lambda event, seconds=seconds: self.set_dialog_muted(dialog, seconds))
                for seconds, label_key in MUTE_DURATIONS
            ]))
        archive_key = CONTEXT_UNARCHIVE_KEY if dialog["archived"] else CONTEXT_ARCHIVE_KEY
        entries.append((archive_key, lambda event: self.set_chat_archived(dialog, not dialog["archived"])))
        entries.append((CONTEXT_INFO_KEY, lambda event: self.show_chat_info(dialog)))
        if not self.is_private_chat(dialog):
            entries.append((CONTEXT_COPY_INVITE_KEY, lambda event: self.copy_invite_link(dialog)))
        if not dialog["joined"]:
            entries.append((CONTEXT_JOIN_KEY, lambda event: self.join_dialog(dialog)))
        if self.is_person(dialog):
            is_contact = dialog["category"] == CATEGORY_CONTACTS
            contact_key = CONTEXT_DELETE_CONTACT_KEY if is_contact else CONTEXT_ADD_CONTACT_KEY
            entries.append((contact_key, lambda event: self.toggle_contact(dialog)))
        if self.is_private_chat(dialog):
            entries.append((CONTEXT_BLOCK_KEY, lambda event: self.toggle_blocked(dialog)))
        entries.append((CONTEXT_CLEAR_HISTORY_KEY, lambda event: self.clear_history(dialog)))
        # Last, away from the everyday entries: it cannot be undone.
        is_private = self.is_private_chat(dialog)
        leave_key = CONTEXT_DELETE_CHAT_KEY if is_private else CONTEXT_LEAVE_KEY
        entries.append((leave_key, lambda event: self.leave_chat(dialog, is_private)))
        self.show_context_menu(entries)

    def copy_invite_link(self, dialog):
        """Put the chat's public or main invite link on the clipboard, to paste or share anywhere."""
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.load_invite_link(dialog["id"], self.on_ui_thread(self.on_invite_link))

    def on_invite_link(self, link):
        self.set_status(STATUS_READY_KEY)
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(link))
            wx.TheClipboard.Close()
            self.announce(self.i18n.get_string(MSG_INVITE_COPIED_KEY))

    def is_private_chat(self, dialog):
        return dialog["category"] not in (CATEGORY_GROUPS, CATEGORY_BROADCASTS)

    def on_chat_menu(self, action):
        """Run one of the menu bar's entries for the selected chat; `action` is given that chat."""
        dialog = self.selected_dialog()
        if dialog is None:
            self.notify(MSG_NO_CHAT_SELECTED_KEY)
        else:
            action(dialog)

    def toggle_dialog_read(self, dialog):
        if dialog["unread"] or dialog["marked_unread"]:
            self.mark_dialog_read(dialog)
        else:
            self.mark_dialog_unread(dialog)

    def toggle_dialog_muted(self, dialog):
        if dialog["muted"]:
            self.set_dialog_muted(dialog, 0)
            return
        with wx.SingleChoiceDialog(
            self, self.i18n.get_string(MSG_CHOOSE_MUTE_KEY), self.i18n.get_string(APP_TITLE_KEY),
            [self.i18n.get_string(label_key) for seconds, label_key in MUTE_DURATIONS]
        ) as choice_dialog:
            if choice_dialog.ShowModal() == wx.ID_OK:
                self.set_dialog_muted(dialog, MUTE_DURATIONS[choice_dialog.GetSelection()][0])

    def cycle_view(self, step):
        """Move to the next or previous chat view, wrapping around: what the view box does, from the keyboard."""
        self.back_to_list()
        self.view_choice.SetSelection((self.view_index + step) % len(self.views))
        self.on_view_changed(None)

    def on_next_unread_menu(self, event):
        start = self.dialogs_list.GetSelection()
        for offset in range(1, len(self.dialogs) + 1):
            index = (start + offset) % len(self.dialogs)
            if self.dialogs[index]["unread"] or self.dialogs[index]["marked_unread"]:
                self.dialogs_list.SetSelection(index)
                self.on_open_dialog(event)
                return
        self.notify(MSG_NO_UNREAD_KEY)

    def show_chat_info(self, dialog):
        with ChatInfoDialog(self, self.i18n, self.telegram_manager, dialog) as info_dialog:
            info_dialog.ShowModal()
            deleted, new_title = info_dialog.deleted, info_dialog.saved_title
        if deleted:
            self.on_chat_left(None, dialog)
            return
        # Nothing to do unless management (opened from the info window) actually renamed the chat.
        if not new_title:
            return
        index = self.find_dialog_index(dialog["id"])
        if index != wx.NOT_FOUND:
            dialog["title"] = new_title
            self.dialogs_list.SetString(index, self.format_dialog(dialog))
            if dialog["id"] == self.current_dialog_id:
                self.show_chat_name(dialog)
        self.notify(MSG_CHAT_SAVED_KEY)

    def mark_dialog_read(self, dialog):
        self.telegram_manager.mark_read(dialog["id"])
        if dialog["marked_unread"]:
            # The hand-set flag is separate from the messages and has to be cleared too.
            self.telegram_manager.set_marked_unread(dialog["id"], False, lambda result, error_key: None)
            dialog["marked_unread"] = False
        dialog["unread"] = 0
        self.refresh_dialog_row(dialog)
        self.notify(MSG_MARKED_READ_KEY)

    def mark_dialog_unread(self, dialog):
        self.telegram_manager.set_marked_unread(
            dialog["id"], True, self.on_ui_thread(self.on_dialog_changed, dialog, "marked_unread", True, MSG_MARKED_UNREAD_KEY)
        )

    def on_dialog_changed(self, result, dialog, field, value, message_key):
        """Telegram accepted a change to one of the chat's flags: show it."""
        dialog[field] = value
        self.refresh_dialog_row(dialog)
        self.notify(message_key)

    def set_dialog_muted(self, dialog, seconds):
        self.telegram_manager.set_muted(
            dialog["id"], seconds, self.on_ui_thread(
                self.on_dialog_changed, dialog, "muted", bool(seconds),
                MSG_MUTED_KEY if seconds else MSG_UNMUTED_KEY
            )
        )

    def set_chat_pinned(self, dialog, pinned):
        self.telegram_manager.set_chat_pinned(
            dialog["id"], pinned, self.on_ui_thread(self.on_chat_pinned, dialog, pinned)
        )

    def on_chat_pinned(self, result, dialog, pinned):
        dialog["pinned"] = pinned
        # Pinned chats lead the list; one just unpinned drops to right below them.
        self.all_dialogs.remove(dialog)
        position = 0 if pinned else sum(1 for other in self.all_dialogs if other["pinned"])
        self.all_dialogs.insert(position, dialog)
        self.render_dialogs()
        self.notify(MSG_CHAT_PINNED_KEY if pinned else MSG_CHAT_UNPINNED_KEY)

    def set_chat_archived(self, dialog, archived):
        self.telegram_manager.set_archived(
            dialog["id"], archived, self.on_ui_thread(self.on_chat_archived, dialog, archived)
        )

    def on_chat_archived(self, result, dialog, archived):
        index = self.find_dialog_index(dialog["id"])
        dialog["archived"] = archived
        self.render_dialogs()
        # It usually leaves the current view; stay where it was instead of jumping to the top.
        if self.find_dialog_index(dialog["id"]) == wx.NOT_FOUND and self.dialogs:
            self.dialogs_list.SetSelection(min(max(index, 0), len(self.dialogs) - 1))
        self.notify(MSG_ARCHIVED_KEY if archived else MSG_UNARCHIVED_KEY)

    def clear_history(self, dialog):
        answer = wx.MessageBox(
            self.i18n.get_string(MSG_CONFIRM_CLEAR_HISTORY_KEY).format(title=dialog["title"]),
            self.i18n.get_string(APP_TITLE_KEY),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self
        )
        if answer == wx.YES:
            self.telegram_manager.clear_history(dialog["id"], self.on_ui_thread(self.on_history_cleared, dialog))

    def on_history_cleared(self, result, dialog):
        dialog["last_message"] = None
        dialog["unread"] = 0
        self.refresh_dialog_row(dialog)
        if dialog["id"] == self.current_dialog_id:
            self.messages = []
            self.has_older = False
            self.marked = set()
            self.messages_list.Clear()
            self.preview_text.ChangeValue("")
        self.notify(MSG_HISTORY_CLEARED_KEY)

    def leave_chat(self, dialog, is_private):
        confirm_key = MSG_CONFIRM_DELETE_CHAT_KEY if is_private else MSG_CONFIRM_LEAVE_KEY
        answer = wx.MessageBox(
            self.i18n.get_string(confirm_key).format(title=dialog["title"]),
            self.i18n.get_string(APP_TITLE_KEY),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self
        )
        if answer == wx.YES:
            self.telegram_manager.leave_chat(dialog["id"], self.on_ui_thread(self.on_chat_left, dialog))

    def on_chat_left(self, result, dialog):
        if dialog in self.all_dialogs:
            self.all_dialogs.remove(dialog)
        index = self.find_dialog_index(dialog["id"])
        if index != wx.NOT_FOUND:
            del self.dialogs[index]
            self.dialogs_list.Delete(index)
            if self.dialogs:
                self.dialogs_list.SetSelection(min(index, len(self.dialogs) - 1))
        if dialog["id"] == self.current_dialog_id:
            # Its messages are gone with it.
            self.forget_open_chat()
        self.announce(self.i18n.get_string(MSG_LEFT_KEY).format(title=dialog["title"]))
