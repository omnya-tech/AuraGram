import wx
from core.speech import speak
from core.settings import SETTING_OPEN_ON_SELECT
from ui.chat_info_dialog import ChatInfoDialog
from core.chat_views import build_views
from core.constants import (
    CATEGORY_GROUPS, CATEGORY_BROADCASTS, CONTEXT_LEAVE_KEY, CONTEXT_DELETE_CHAT_KEY,
    MSG_CONFIRM_LEAVE_KEY, MSG_CONFIRM_DELETE_CHAT_KEY, MSG_LEFT_KEY, MSG_VIEW_COUNT_FORMAT_KEY,
    MSG_CHOOSE_CONTACT_KEY, MSG_NO_CONTACTS_KEY, MSG_FIND_CHAT_PROMPT_KEY, CONTEXT_INFO_KEY,
    MSG_CHAT_SAVED_KEY, CONTEXT_OPEN_KEY, CONTEXT_MARK_READ_KEY, CONTEXT_MUTE_KEY,
    CONTEXT_UNMUTE_KEY, MSG_MARKED_READ_KEY, MSG_MUTED_KEY, MSG_UNMUTED_KEY, DIALOGS_LIMIT,
    MSG_LOAD_MORE_DIALOGS_KEY, MSG_FIND_PROMPT_KEY, MSG_NOT_FOUND_KEY, APP_TITLE_KEY,
    MSG_LOADING_KEY, STATUS_READY_KEY, SELECT_DELAY_MS, SENDER_YOU_KEY, MUTE_DURATIONS,
    CONTEXT_MARK_UNREAD_KEY, CONTEXT_PIN_CHAT_KEY, CONTEXT_UNPIN_CHAT_KEY, CONTEXT_ARCHIVE_KEY,
    CONTEXT_UNARCHIVE_KEY, CONTEXT_CLEAR_HISTORY_KEY, MSG_MARKED_UNREAD_KEY, MSG_CHAT_PINNED_KEY,
    MSG_CHAT_UNPINNED_KEY, MSG_ARCHIVED_KEY, MSG_UNARCHIVED_KEY, MSG_CONFIRM_CLEAR_HISTORY_KEY,
    MSG_HISTORY_CLEARED_KEY, DIALOG_FORMAT_KEY, DIALOG_PINNED_KEY, DIALOG_MARKED_UNREAD_KEY,
    DIALOG_UNREAD_COUNT_FORMAT_KEY, PREVIEW_SENDER_FORMAT_KEY,
    MSG_NEW_CHAT_NAME_PROMPT_KEY, MSG_NEW_CHAT_ABOUT_PROMPT_KEY, MSG_CHAT_CREATED_FORMAT_KEY
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
        self.keep_draft()
        self.current_dialog_id = dialog_id
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
        if text.strip():
            self.drafts[self.current_dialog_id] = text
        else:
            self.drafts.pop(self.current_dialog_id, None)

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

    def ask_text(self, prompt_key):
        """One line of text from the user; None if they cancel."""
        with wx.TextEntryDialog(
            self, self.i18n.get_string(prompt_key), self.i18n.get_string(APP_TITLE_KEY)
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
        entries.append((CONTEXT_CLEAR_HISTORY_KEY, lambda event: self.clear_history(dialog)))
        # Last, away from the everyday entries: it cannot be undone.
        is_private = dialog["category"] not in (CATEGORY_GROUPS, CATEGORY_BROADCASTS)
        leave_key = CONTEXT_DELETE_CHAT_KEY if is_private else CONTEXT_LEAVE_KEY
        entries.append((leave_key, lambda event: self.leave_chat(dialog, is_private)))
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
            self.current_dialog_id = None
            self.show_chat_name(None)
            self.preview_text.ChangeValue("")
            self.set_compose()
            self.messages = []
            self.has_older = False
            self.messages_list.Clear()
            self.enable_chat(False)
        self.announce(self.i18n.get_string(MSG_LEFT_KEY).format(title=dialog["title"]))
