import wx
from core.constants import (
    MESSAGE_VIEW_SCHEDULED, MSG_CONFIRM_CANCEL_SCHEDULED_KEY, MSG_SCHEDULED_CANCELLED_KEY,
    MSG_POLL_CLOSED_KEY, MSG_VOTED_KEY, MSG_CHOOSE_REACTION_KEY, REACTION_REMOVE_KEY,
    REACTION_CHOICE_FORMAT_KEY, MSG_REACTED_KEY, REACTION_EMOJIS, REACTION_NAME_KEY_PREFIX,
    MSG_FORWARD_TO_KEY, MSG_FORWARDED_FORMAT_KEY, MSG_PINNED_KEY, MSG_UNPINNED_KEY,
    MSG_CANNOT_PIN_KEY, MSG_CONFIRM_DELETE_OTHER_KEY, MSG_COPIED_KEY, MSG_CANNOT_DELETE_KEY,
    MSG_CONFIRM_DELETE_KEY, MSG_DELETED_KEY, APP_TITLE_KEY, MSG_LOADING_KEY,
    MSG_MARKED_COUNT_FORMAT_KEY, MSG_MARKS_CLEARED_KEY, MSG_CONFIRM_DELETE_MANY_FORMAT_KEY,
    MSG_CANNOT_DELETE_SOME_KEY, MSG_DELETED_MANY_FORMAT_KEY, MSG_LINK_COPIED_KEY
)

class MessageActionsMixin:
    """What can be done to an existing message.

    Mixed into MainFrame, which owns the widgets and the shared state.
    """

    def can_delete(self, message):
        return message["outgoing"] or self.current_dialog()["can_delete_others"]

    def on_delete_menu(self, event):
        message = self.selected_message()
        if message is None or self.is_busy:
            return
        if self.message_view == MESSAGE_VIEW_SCHEDULED:
            self.cancel_scheduled(message)
            return
        marked = self.marked_messages()
        if marked:
            self.delete_marked(marked)
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

    def marked_messages(self):
        """The marked messages in the order they are listed; empty when nothing is marked."""
        return [message for message in self.messages if message["id"] in self.marked]

    def on_mark_menu(self, event):
        message = self.actionable_message()
        if message is None:
            return
        # Toggle: marking a marked message unmarks it.
        self.marked ^= {message["id"]}
        self.render_messages(self.messages_list.GetSelection() - self.message_offset())
        self.announce(self.i18n.get_string(MSG_MARKED_COUNT_FORMAT_KEY).format(count=len(self.marked)))

    def on_unmark_all_menu(self, event):
        self.clear_marks()

    def clear_marks(self):
        """Returns True if anything was marked."""
        if not self.marked:
            return False
        self.marked = set()
        self.render_messages(self.messages_list.GetSelection() - self.message_offset())
        self.notify(MSG_MARKS_CLEARED_KEY)
        return True

    def delete_marked(self, marked):
        if not all(self.can_delete(message) for message in marked):
            self.notify(MSG_CANNOT_DELETE_SOME_KEY)
            return
        answer = wx.MessageBox(
            self.i18n.get_string(MSG_CONFIRM_DELETE_MANY_FORMAT_KEY).format(count=len(marked)),
            self.i18n.get_string(APP_TITLE_KEY),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self
        )
        if answer != wx.YES:
            return
        self.is_busy = True
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        message_ids = [message["id"] for message in marked]
        self.telegram_manager.delete_message(
            dialog_id, message_ids, self.on_ui_thread(self.on_marked_deleted, dialog_id, message_ids)
        )

    def on_marked_deleted(self, result, dialog_id, message_ids):
        self.is_busy = False
        if dialog_id == self.current_dialog_id:
            for message_id in message_ids:
                self.remove_message(message_id)
        self.announce(self.i18n.get_string(MSG_DELETED_MANY_FORMAT_KEY).format(count=len(message_ids)))

    def cancel_scheduled(self, message):
        answer = wx.MessageBox(
            self.i18n.get_string(MSG_CONFIRM_CANCEL_SCHEDULED_KEY).format(text=self.message_snippet(message)),
            self.i18n.get_string(APP_TITLE_KEY),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self
        )
        if answer != wx.YES:
            return
        self.is_busy = True
        dialog_id = self.current_dialog_id
        self.telegram_manager.delete_scheduled(
            dialog_id, message["id"],
            self.on_ui_thread(self.on_scheduled_cancelled, dialog_id, message["id"])
        )

    def on_scheduled_cancelled(self, result, dialog_id, message_id):
        self.is_busy = False
        if dialog_id == self.current_dialog_id and self.message_view == MESSAGE_VIEW_SCHEDULED:
            self.remove_message(message_id)
        self.notify(MSG_SCHEDULED_CANCELLED_KEY)

    def on_pin_menu(self, event):
        message = self.actionable_message()
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
        # With messages marked, copy all of their texts, one per line.
        texts = [marked["text"] for marked in self.marked_messages() if marked["text"]]
        if not texts and message is not None and message["text"]:
            texts = [message["text"]]
        if not texts or not wx.TheClipboard.Open():
            return
        wx.TheClipboard.SetData(wx.TextDataObject("\n".join(texts)))
        wx.TheClipboard.Close()
        self.notify(MSG_COPIED_KEY)

    def on_copy_link_menu(self, event):
        message = self.actionable_message()
        if message is None or not self.current_dialog()["has_links"]:
            return
        self.telegram_manager.load_message_link(
            self.current_dialog_id, message["id"], self.on_ui_thread(self.copy_link)
        )

    def copy_link(self, link):
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(link))
            wx.TheClipboard.Close()
            self.notify(MSG_LINK_COPIED_KEY)

    def on_forward_menu(self, event):
        message = self.actionable_message()
        if message is None or not self.all_dialogs:
            return
        target = self.choose_chat(MSG_FORWARD_TO_KEY, self.all_dialogs)
        if target is None:
            return
        marked = self.marked_messages()
        # Marked messages go together, in the order they appear in the chat.
        message_ids = [marked_message["id"] for marked_message in marked] if marked else message["id"]
        self.telegram_manager.forward_message(
            self.current_dialog_id, message_ids, target["id"],
            self.on_ui_thread(self.on_forwarded, target)
        )

    def on_forwarded(self, result, target):
        if self.marked:
            self.marked = set()
            self.render_messages(self.messages_list.GetSelection() - self.message_offset())
        self.announce(self.i18n.get_string(MSG_FORWARDED_FORMAT_KEY).format(title=target["title"]))

    def on_react_menu(self, event):
        message = self.actionable_message()
        if message is None or self.is_busy:
            return
        names = [
            self.i18n.get_string(REACTION_CHOICE_FORMAT_KEY).format(
                name=self.i18n.get_string(REACTION_NAME_KEY_PREFIX + str(index)), emoji=emoji
            )
            for index, emoji in enumerate(REACTION_EMOJIS)
        ]
        with wx.SingleChoiceDialog(
            self, self.i18n.get_string(MSG_CHOOSE_REACTION_KEY), self.i18n.get_string(APP_TITLE_KEY),
            names + [self.i18n.get_string(REACTION_REMOVE_KEY)]
        ) as reaction_dialog:
            if reaction_dialog.ShowModal() != wx.ID_OK:
                return
            choice = reaction_dialog.GetSelection()
        # The entry after the emoji is "remove my reaction".
        emoji = REACTION_EMOJIS[choice] if choice < len(REACTION_EMOJIS) else None
        self.is_busy = True
        dialog_id = self.current_dialog_id
        self.telegram_manager.react(
            dialog_id, message["id"], emoji, self.on_ui_thread(self.on_reacted, dialog_id)
        )

    def on_reacted(self, message, dialog_id):
        self.is_busy = False
        # Same path as an edit arriving from Telegram: swap the message in and redraw.
        self.on_message_edited(dialog_id, message)
        self.notify(MSG_REACTED_KEY)

    def on_vote_menu(self, event):
        message = self.actionable_message()
        if message is None or not message["poll"] or self.is_busy:
            return
        poll = message["poll"]
        if poll["closed"]:
            self.notify(MSG_POLL_CLOSED_KEY)
            return
        title = self.i18n.get_string(APP_TITLE_KEY)
        texts = [option["text"] for option in poll["options"]]
        chosen = [index for index, option in enumerate(poll["options"]) if option["chosen"]]
        if poll["multiple"]:
            with wx.MultiChoiceDialog(self, poll["question"], title, texts) as vote_dialog:
                vote_dialog.SetSelections(chosen)
                if vote_dialog.ShowModal() != wx.ID_OK:
                    return
                indexes = list(vote_dialog.GetSelections())
        else:
            with wx.SingleChoiceDialog(self, poll["question"], title, texts) as vote_dialog:
                if chosen:
                    vote_dialog.SetSelection(chosen[0])
                if vote_dialog.ShowModal() != wx.ID_OK:
                    return
                indexes = [vote_dialog.GetSelection()]
        self.is_busy = True
        dialog_id = self.current_dialog_id
        self.telegram_manager.vote(
            dialog_id, message["id"], indexes, self.on_ui_thread(self.on_voted, dialog_id)
        )

    def on_voted(self, message, dialog_id):
        self.is_busy = False
        self.on_message_edited(dialog_id, message)
        self.notify(MSG_VOTED_KEY)
