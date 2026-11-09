import time
import wx
from core import sounds, speech
from core.speech import speak
from core.settings import (
    SETTING_PLAY_SOUND, SETTING_ANNOUNCE_MESSAGES, SETTING_MARK_READ_ON_OPEN, SETTING_ANNOUNCE_WHEN,
    SETTING_ANNOUNCE_WHAT, SETTING_ANNOUNCE_INTERRUPT, SETTING_BRAILLE_MESSAGES, SETTING_ANNOUNCE_TYPING
)
from core.constants import (
    EVENT_NEW_MESSAGE, EVENT_MESSAGE_EDITED, EVENT_MESSAGES_DELETED, ANNOUNCE_FORMAT_KEY,
    SOUND_MESSAGE_IN_CHAT, ANNOUNCE_WHEN_FOREGROUND, ANNOUNCE_WHEN_BACKGROUND,
    ANNOUNCE_WHAT_SENDER, ANNOUNCE_WHAT_WHOLE, ANNOUNCE_SENDER_FORMAT_KEY, EVENT_MESSAGES_READ, EVENT_USER_STATUS, EVENT_TYPING, TYPING_ACTION_TYPING, TYPING_ACTION_CANCEL, TYPING_ACTION_KEYS,
    TYPING_SHOWN_MS, EVENT_DRAFT, PREVIEW_SENDER_FORMAT_KEY, EVENT_MESSAGE_NUMBERS, LIVE_NUMBERS_SECONDS,
    LIVE_NUMBERS_AROUND, CONNECTION_OFFLINE, MESSAGE_VIEW_SCHEDULED, LIVE_NUMBERS_REST_SECONDS, ERR_FLOOD_KEY,
    VIEWS_FORMAT_KEY, COMMENTS_FORMAT_KEY, AUDIENCE_FORWARDS_FORMAT_KEY, FILE_LABEL_SEPARATOR_KEY
)

class LiveUpdatesMixin:
    """Reacting to what Telegram reports while the app is open.

    Mixed into MainFrame, which owns the widgets and the shared state.
    """

    def on_telegram_event(self, event, *details):
        if not self:
            return
        handlers = {
            EVENT_NEW_MESSAGE: self.on_new_message,
            EVENT_MESSAGE_EDITED: self.on_message_edited,
            EVENT_MESSAGES_DELETED: self.on_messages_deleted,
            EVENT_MESSAGES_READ: self.on_messages_read,
            EVENT_USER_STATUS: self.on_user_status,
            EVENT_TYPING: self.on_typing,
            EVENT_DRAFT: self.on_draft,
            EVENT_MESSAGE_NUMBERS: self.on_message_numbers,
        }
        handlers[event](*details)

    def on_new_message(self, chat, message):
        dialog_id = chat["id"]
        if not message["outgoing"]:
            # What they were typing has arrived.
            self.clear_typing_row(dialog_id)
        index = self.find_dialog_index(dialog_id)
        # Prefer the chat as already loaded: it knows its unread count and mute state.
        dialog = self.find_known_dialog(dialog_id) or chat

        is_current = dialog_id == self.current_dialog_id
        if not is_current:
            self.forget_remembered(dialog_id)
        # Hidden in the background, the window shows nothing to anyone.
        is_on_screen = self.IsShown() and not self.IsIconized()
        if not message["outgoing"] and not dialog["muted"]:
            if self.settings.get(SETTING_PLAY_SOUND):
                # A quiet tick for the chat being read, the full chime for anything else.
                is_being_read = is_current and is_on_screen and self.IsActive()
                sounds.play(SOUND_MESSAGE_IN_CHAT if is_being_read else self.message_tone(dialog_id))
            # In the open chat the sender is what matters; elsewhere, which chat it came from.
            self.report_message(message["sender"] if is_current else dialog["title"], message)

        # The chat list previews the newest message, whoever sent it.
        dialog["last_message"] = message
        reads_it = is_current and is_on_screen and self.settings.get(SETTING_MARK_READ_ON_OPEN)
        # Also what is written under the open post: its comments come from another chat than the one open.
        if is_current or dialog_id == self.peer(self.current_dialog_id):
            self.append_message(message)
        if not message["outgoing"]:
            if reads_it:
                self.telegram_manager.mark_read(dialog_id)
            else:
                dialog["unread"] += 1
        self.move_dialog_to_top(index, dialog)

    def report_message(self, source, message):
        """Tell the screen reader user about a new message, as the accessibility settings ask."""
        what = self.settings.get(SETTING_ANNOUNCE_WHAT)
        sender_only = what == ANNOUNCE_WHAT_SENDER
        # To the end if asked, with its line breaks as pauses; otherwise only how it begins.
        said = " ".join(self.message_text(message).split()) if what == ANNOUNCE_WHAT_WHOLE else self.message_snippet(message)
        if message.get("service") and message["sender"] and message["sender"] != source:
            # Telegram's own news says what was done; who did it is said first, as on the message's row.
            said = self.i18n.get_string(PREVIEW_SENDER_FORMAT_KEY).format(sender=message["sender"], text=said)
        text = self.i18n.get_string(ANNOUNCE_SENDER_FORMAT_KEY if sender_only else ANNOUNCE_FORMAT_KEY).format(
            source=source, text=said
        )
        if self.settings.get(SETTING_BRAILLE_MESSAGES):
            speech.braille(text)
        if not self.settings.get(SETTING_ANNOUNCE_MESSAGES):
            return
        when = self.settings.get(SETTING_ANNOUNCE_WHEN)
        is_in_front = self.IsShown() and self.IsActive()
        if (when == ANNOUNCE_WHEN_FOREGROUND and not is_in_front) or (when == ANNOUNCE_WHEN_BACKGROUND and is_in_front):
            return
        if self.settings.get(SETTING_ANNOUNCE_INTERRUPT):
            speak(text, interrupt=True)
        else:
            speak(text)

    def on_brought_forward(self):
        """The window is visible again: what arrived in the open chat meanwhile is now being read."""
        dialog = self.find_known_dialog(self.current_dialog_id)
        if dialog and dialog["unread"] and self.settings.get(SETTING_MARK_READ_ON_OPEN):
            self.telegram_manager.mark_read(dialog["id"])
            self.set_unread(dialog["id"], 0)

    def on_message_edited(self, dialog_id, message):
        if dialog_id != self.peer(self.current_dialog_id):
            self.forget_remembered(dialog_id)
            return
        for index, shown in enumerate(self.messages):
            if shown["id"] == message["id"]:
                self.messages[index] = message
                # Re-render: replies quoting this message show its text too.
                self.render_messages(self.messages_list.GetSelection() - self.message_offset())
                return

    def start_live_numbers(self):
        """Keep the open channel's views, forwards and comments current, as Telegram's apps do, without
        the chat being opened again."""
        wx.CallLater(LIVE_NUMBERS_SECONDS * 1000, self.live_numbers_tick)

    def live_numbers_tick(self):
        """Now and again, for as long as the window is there. Not a wx.Timer: one owned by the window
        outlives it, and takes the program down when it goes (as ui.reminders found before)."""
        if not self:
            return
        wx.CallLater(LIVE_NUMBERS_SECONDS * 1000, self.live_numbers_tick)
        self.ask_live_numbers()

    def ask_live_numbers(self, event=None):
        """Ask for the numbers of the posts around the selected one, when there is someone to see them."""
        if not self or self.numbers_pending or not self.IsShown() or self.IsIconized() or self.current_dialog_id is None:
            return
        if time.monotonic() < getattr(self, "numbers_rest_until", 0):
            # Telegram said it was asked too often: it is left alone for a while.
            return
        if self.telegram_manager.connection_state == CONNECTION_OFFLINE or self.message_view == MESSAGE_VIEW_SCHEDULED:
            return
        posts = [message for message in self.messages if message["views"] is not None]
        if not posts:
            # A private chat or a group: Telegram counts views of channel posts only.
            return
        selected = self.selected_message()
        middle = posts.index(selected) if selected in posts else len(posts) - 1
        start = max(0, middle - LIVE_NUMBERS_AROUND)
        ids = [message["id"] for message in posts[start:middle + LIVE_NUMBERS_AROUND + 1]]
        dialog_id = self.current_dialog_id
        self.numbers_pending = True

        def deliver(result, error_key):
            # A failure is no news: the next round asks again, or, asked too often, after a rest.
            wx.CallAfter(self.on_numbers_answer, dialog_id, result, error_key)
        self.telegram_manager.load_message_views(self.peer(dialog_id), ids, deliver)

    def on_numbers_answer(self, dialog_id, numbers, error_key=None):
        if not self:
            return
        self.numbers_pending = False
        if error_key == ERR_FLOOD_KEY:
            self.numbers_rest_until = time.monotonic() + LIVE_NUMBERS_REST_SECONDS
        if numbers:
            self.on_message_numbers(dialog_id, numbers)

    def on_message_numbers(self, dialog_id, numbers):
        """New numbers for posts of a chat: {message id: {"views"/"forwards"/"comments": number}}."""
        if dialog_id != self.current_dialog_id:
            return
        selected = self.messages_list.GetSelection()
        # Every row shows its new numbers, the one the eyes are on too. Only with a screen reader on that
        # row does it keep its words, since a screen reader reads a row whose words change out again, post
        # and all, at every new view: the new numbers are said instead, and the row catches up once the
        # selection moves.
        reading = selected if wx.Window.FindFocus() is self.messages_list and speech.screen_reader_running() else None
        offset = self.message_offset()
        selected_changed = False
        told = []
        for index, message in enumerate(self.messages):
            changed = {
                name: number for name, number in numbers.get(message["id"], {}).items()
                if number is not None and message.get(name) != number
            }
            if not changed:
                continue
            message.update(changed)
            row = index + offset
            if row == selected:
                selected_changed = True
            if row == reading:
                self.stale_rows.add(message["id"])
                told = self.numbers_words(changed)
            else:
                self.messages_list.SetString(row, self.format_message(message))
        if selected_changed:
            self.update_preview()
        if told and self.IsActive():
            # Only while this window is the one in use: news from a channel left open is no interruption.
            speech.speak(self.i18n.get_string(FILE_LABEL_SEPARATOR_KEY).join(told))

    def numbers_words(self, changed):
        """The new numbers in words, as the statistics say them: views, comments, forwards."""
        text = self.i18n.get_string
        words = []
        for name, key in (("views", VIEWS_FORMAT_KEY), ("comments", COMMENTS_FORMAT_KEY), ("forwards", AUDIENCE_FORWARDS_FORMAT_KEY)):
            if name in changed:
                words.append(text(key).format(count=changed[name]))
        return words

    def refresh_stale_rows(self):
        """Bring up to date the rows left as they were while being read, now that the selection is elsewhere."""
        if not self.stale_rows:
            return
        selected = self.messages_list.GetSelection()
        offset = self.message_offset()
        for index, message in enumerate(self.messages):
            if message["id"] in self.stale_rows and index + offset != selected:
                self.stale_rows.discard(message["id"])
                self.messages_list.SetString(index + offset, self.format_message(message))

    def on_messages_read(self, dialog_id, max_id):
        if dialog_id != self.current_dialog_id:
            self.forget_remembered(dialog_id)
            return
        newly_read = [m for m in self.messages if m["read"] is False and m["id"] <= max_id]
        for message in newly_read:
            message["read"] = True
        if newly_read:
            self.render_messages(self.messages_list.GetSelection() - self.message_offset())

    def on_user_status(self, user_id, status):
        # A person's private chat has the same id as the person.
        dialog = self.find_known_dialog(user_id)
        # A contact may be listed without having a chat, and so be known only there.
        contact = next((chat for chat in self.contacts if chat["id"] == user_id), None)
        for chat in (dialog, contact):
            # Not listed, or one that shows no status (this account itself, a bot).
            if chat is not None and chat["status"] is not None:
                chat["status"] = status
        if self.showing_contacts() and contact is not None:
            self.refresh_dialog_row(dialog or contact)
        if dialog is not None and user_id == self.current_dialog_id:
            self.show_chat_name(dialog)

    def on_draft(self, dialog_id, text):
        # In the open chat the field itself is the draft, and the user may be typing in it right now.
        if dialog_id == self.current_dialog_id:
            return
        if text:
            self.drafts[dialog_id] = text
        else:
            self.drafts.pop(dialog_id, None)

    def on_typing(self, dialog_id, action=TYPING_ACTION_TYPING, name=None):
        dialog = self.find_known_dialog(dialog_id)
        if dialog is None:
            return
        self.show_typing_row(dialog, action, name)
        if dialog_id != self.current_dialog_id:
            return
        if action == TYPING_ACTION_CANCEL:
            # They stopped: what the status bar said is no longer true.
            self.clear_typing(self.GetStatusBar().GetStatusText(), only_typing=True)
            return
        # In a group, the member's name; in a private chat, the chat is the person.
        text = self.i18n.get_string(TYPING_ACTION_KEYS[action]).format(chat=name or dialog["title"])
        self.typing_texts.add(text)
        # Telegram repeats this every few seconds while the typing goes on: say it once.
        if self.GetStatusBar().GetStatusText() != text and self.settings.get(SETTING_ANNOUNCE_TYPING):
            speak(text)
        self.SetStatusText(text)
        if self.typing_timer:
            self.typing_timer.Stop()
        self.typing_timer = wx.CallLater(TYPING_SHOWN_MS, self.clear_typing, text)

    def show_typing_row(self, dialog, action, name):
        """Put what someone is doing on the chat's row in the list, for as long as Telegram keeps saying so."""
        if action == TYPING_ACTION_CANCEL:
            self.clear_typing_row(dialog["id"])
            return
        text = self.i18n.get_string(TYPING_ACTION_KEYS[action]).format(chat=name or dialog["title"])
        timer = self.typing_row_timers.pop(dialog["id"], None)
        if timer:
            timer.Stop()
        self.typing_row_timers[dialog["id"]] = wx.CallLater(TYPING_SHOWN_MS, self.clear_typing_row, dialog["id"])
        if self.typing_in.get(dialog["id"]) != text:
            self.typing_in[dialog["id"]] = text
            self.refresh_dialog_row(dialog)

    def clear_typing_row(self, dialog_id):
        if not self:
            return
        timer = self.typing_row_timers.pop(dialog_id, None)
        if timer:
            timer.Stop()
        if self.typing_in.pop(dialog_id, None) is not None:
            dialog = self.find_known_dialog(dialog_id)
            if dialog is not None:
                self.refresh_dialog_row(dialog)

    def clear_typing(self, text, only_typing=False):
        # Only if nothing else has taken the status bar since.
        if not self or self.GetStatusBar().GetStatusText() != text:
            return
        if only_typing and text not in self.typing_texts:
            return
        self.SetStatusText("")

    def on_messages_deleted(self, dialog_id, message_ids):
        if dialog_id is None:
            # Telegram does not say which chat, so any chat remembered may have lost it.
            self.forget_remembered()
            # Outside channels message ids are unique across chats, so matching by id is safe there, but only there.
            if self.current_dialog_id is None or self.shown_chat()["is_channel"]:
                return
        elif dialog_id != self.peer(self.current_dialog_id):
            self.forget_remembered(dialog_id)
            return
        for message_id in message_ids:
            self.remove_message(message_id)
