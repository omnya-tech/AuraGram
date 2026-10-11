import urllib.parse
import webbrowser
import wx
from core.constants import (
    MESSAGE_VIEW_SCHEDULED, MSG_CONFIRM_CANCEL_SCHEDULED_KEY, MSG_SCHEDULED_CANCELLED_KEY,
    MSG_POLL_CLOSED_KEY, MSG_VOTED_KEY, MSG_CHOOSE_REACTION_KEY, REACTION_REMOVE_KEY,
    REACTION_CHOICE_FORMAT_KEY, MSG_REACTED_KEY, REACTION_EMOJIS, REACTION_NAME_KEY_PREFIX,
    MSG_FORWARD_TO_KEY, MSG_FORWARDED_FORMAT_KEY, MSG_PINNED_KEY, MSG_UNPINNED_KEY,
    MSG_CANNOT_PIN_KEY, MSG_CONFIRM_DELETE_OTHER_KEY, MSG_COPIED_KEY, MSG_CANNOT_DELETE_KEY,
    MSG_CONFIRM_DELETE_KEY, MSG_DELETED_KEY, APP_TITLE_KEY, MSG_LOADING_KEY, STATUS_READY_KEY,
    MSG_MARKED_COUNT_FORMAT_KEY, MSG_MARKS_CLEARED_KEY, MSG_CONFIRM_DELETE_MANY_FORMAT_KEY,
    MSG_CANNOT_DELETE_SOME_KEY, MSG_DELETED_MANY_FORMAT_KEY, MSG_LINK_COPIED_KEY,
    MSG_CHOOSE_BUTTON_KEY, MSG_NO_BUTTONS_KEY, MSG_BUTTON_PRESSED_KEY, MSG_CONFIRM_OPEN_LINK_FORMAT_KEY,
    MSG_CHOOSE_LINK_KEY, MSG_NO_LINKS_KEY, TELEGRAM_LINK_HOSTS, MSG_DELETE_SCOPE_KEY, DELETE_FOR_ALL_KEY,
    DELETE_FOR_ME_KEY, MSG_REPORT_COMMENT_KEY, MSG_REPORTED_KEY
)

class MessageActionsMixin:
    """What can be done to an existing message.

    Mixed into MainFrame, which owns the widgets and the shared state.
    """

    def can_delete(self, message):
        return message["outgoing"] or self.shown_chat()["can_delete_others"]

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
        for_everyone = self.ask_delete_scope()
        if for_everyone is None:
            return
        self.is_busy = True
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        self.telegram_manager.delete_message(
            self.peer(dialog_id), message["id"],
            self.on_ui_thread(self.on_message_deleted, dialog_id, message["id"]), for_everyone=for_everyone
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
        for_everyone = self.ask_delete_scope()
        if for_everyone is None:
            return
        self.is_busy = True
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        message_ids = [message["id"] for message in marked]
        self.telegram_manager.delete_message(
            self.peer(dialog_id), message_ids, self.on_ui_thread(self.on_marked_deleted, dialog_id, message_ids),
            for_everyone=for_everyone
        )

    def ask_delete_scope(self):
        """Whether to delete for everyone (True) or only on this side (False); None if the user backs out.

        Only a private chat or a small group keeps a copy per person. In a channel or
        a large group there is one copy, and deleting it deletes it for all.
        """
        if self.shown_chat()["is_channel"]:
            return True
        with wx.SingleChoiceDialog(
            self, self.i18n.get_string(MSG_DELETE_SCOPE_KEY), self.i18n.get_string(APP_TITLE_KEY),
            [self.i18n.get_string(DELETE_FOR_ALL_KEY), self.i18n.get_string(DELETE_FOR_ME_KEY)]
        ) as scope_dialog:
            if scope_dialog.ShowModal() != wx.ID_OK:
                return None
            return scope_dialog.GetSelection() == 0

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
        if not self.shown_chat()["can_pin"]:
            self.notify(MSG_CANNOT_PIN_KEY)
            return
        pinned = not message["pinned"]
        self.is_busy = True
        dialog_id = self.current_dialog_id
        self.telegram_manager.set_pinned(
            self.peer(dialog_id), message["id"], pinned,
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
        if message is None or not self.shown_chat()["has_links"]:
            return
        self.telegram_manager.load_message_link(
            self.peer(self.current_dialog_id), message["id"], self.on_ui_thread(self.copy_link)
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
            self.peer(self.current_dialog_id), message_ids, target["id"],
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
            self.peer(dialog_id), message["id"], emoji, self.on_ui_thread(self.on_reacted, self.peer(dialog_id))
        )

    def on_reacted(self, message, dialog_id):
        self.is_busy = False
        # Same path as an edit arriving from Telegram: swap the message in and redraw.
        self.on_message_edited(dialog_id, message)
        self.notify(MSG_REACTED_KEY)

    def on_report_menu(self, event):
        message = self.actionable_message()
        if message is None or self.is_busy:
            return
        marked = self.marked_messages()
        message_ids = [marked_message["id"] for marked_message in marked] if marked else [message["id"]]
        self.report_step(self.peer(self.current_dialog_id), message_ids, b"", "")

    def report_step(self, dialog_id, message_ids, option, comment):
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.report(
            dialog_id, message_ids, option, comment, self.on_ui_thread(self.on_report_answer, dialog_id, message_ids, comment)
        )

    def on_report_answer(self, answer, dialog_id, message_ids, comment):
        """Telegram asks about a report one question at a time; each answer of the user brings the next."""
        self.set_status(STATUS_READY_KEY)
        if answer.get("done"):
            self.notify(MSG_REPORTED_KEY)
        elif "options" in answer:
            # The questions and reasons are Telegram's own words.
            with wx.SingleChoiceDialog(
                self, answer["title"], self.i18n.get_string(APP_TITLE_KEY), [text for text, option in answer["options"]]
            ) as reason_dialog:
                if reason_dialog.ShowModal() != wx.ID_OK:
                    return
                option = answer["options"][reason_dialog.GetSelection()][1]
            self.report_step(dialog_id, message_ids, option, comment)
        else:
            with wx.TextEntryDialog(
                self, self.i18n.get_string(MSG_REPORT_COMMENT_KEY), self.i18n.get_string(APP_TITLE_KEY)
            ) as comment_dialog:
                if comment_dialog.ShowModal() != wx.ID_OK:
                    return
                # A space at the least: an empty comment would bring the same question back.
                typed = comment_dialog.GetValue().strip() or " "
            self.report_step(dialog_id, message_ids, answer["comment"], typed)

    def on_open_link_menu(self, event):
        message = self.selected_message()
        if message is None:
            return
        if not message["links"]:
            self.notify(MSG_NO_LINKS_KEY)
            return
        # Asked even for a single link: the list is where the user sees the real address.
        with wx.SingleChoiceDialog(
            self, self.i18n.get_string(MSG_CHOOSE_LINK_KEY), self.i18n.get_string(APP_TITLE_KEY), message["links"]
        ) as link_dialog:
            if link_dialog.ShowModal() != wx.ID_OK:
                return
            link = message["links"][link_dialog.GetSelection()]
        self.follow_link(link)

    def follow_link(self, link):
        """Open a Telegram address as a chat here, and anything else in the browser."""
        address = link if "://" in link else "https://" + link
        host = (urllib.parse.urlsplit(address).hostname or "").lower()
        if host in TELEGRAM_LINK_HOSTS:
            self.open_link(address)
        else:
            webbrowser.open(address)

    def on_buttons_menu(self, event):
        """Let the user press one of the buttons a bot put under its message."""
        message = self.actionable_message()
        if message is None or self.is_busy:
            return
        if not message["buttons"]:
            self.notify(MSG_NO_BUTTONS_KEY)
            return
        with wx.SingleChoiceDialog(
            self, self.i18n.get_string(MSG_CHOOSE_BUTTON_KEY), self.i18n.get_string(APP_TITLE_KEY), message["buttons"]
        ) as button_dialog:
            if button_dialog.ShowModal() != wx.ID_OK:
                return
            index = button_dialog.GetSelection()
        self.is_busy = True
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.press_button(
            self.peer(self.current_dialog_id), message["id"], index, self.on_ui_thread(self.on_button_pressed)
        )

    def on_button_pressed(self, result):
        self.is_busy = False
        if result["url"]:
            self.set_status(STATUS_READY_KEY)
            answer = wx.MessageBox(
                self.i18n.get_string(MSG_CONFIRM_OPEN_LINK_FORMAT_KEY).format(url=result["url"]),
                self.i18n.get_string(APP_TITLE_KEY), wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self
            )
            if answer == wx.YES:
                webbrowser.open(result["url"])
        else:
            # What the bot does next, a new message or a change to this one, arrives by itself.
            self.announce(result["answer"] or self.i18n.get_string(MSG_BUTTON_PRESSED_KEY))

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
            self.peer(dialog_id), message["id"], indexes, self.on_ui_thread(self.on_voted, self.peer(dialog_id))
        )

    def on_voted(self, message, dialog_id):
        self.is_busy = False
        self.on_message_edited(dialog_id, message)
        self.notify(MSG_VOTED_KEY)
