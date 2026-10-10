import datetime
import os
import wx
from core import audio
from core.settings import SETTING_MARK_READ_ON_OPEN
from core.constants import (
    PREVIEW_FORMAT_KEY, CONTEXT_COPY_LINK_KEY, CONTEXT_SAVE_AS_KEY, CONTEXT_SELECT_KEY, CONTEXT_UNSELECT_KEY,
    MSG_CHOOSE_SAVE_FOLDER_KEY, MSG_SAVED_FORMAT_KEY, CONTEXT_READ_MESSAGE_KEY, READ_MESSAGE_TITLE_KEY, READ_MESSAGE_HEADER_FORMAT_KEY, MARKED_FORMAT_KEY, MESSAGE_VIEW_SEARCH, MESSAGE_VIEW_SCHEDULED, MSG_VIEW_RESULTS_FORMAT_KEY, MSG_VIEW_EMPTY_KEY,
    POLL_FORMAT_KEY, POLL_OPTION_FORMAT_KEY, POLL_CHOSEN_KEY, POLL_VOTERS_FORMAT_KEY,
    POLL_CLOSED_SUFFIX_KEY, CONTEXT_VOTE_KEY, CONTEXT_REACT_KEY, REACTIONS_FORMAT_KEY,
    REACTION_COUNT_FORMAT_KEY, CONTEXT_FORWARD_KEY, CONTEXT_PIN_KEY, CONTEXT_UNPIN_KEY,
    PINNED_FORMAT_KEY, CONTEXT_REPLY_KEY, CONTEXT_EDIT_KEY, CONTEXT_DELETE_KEY, CONTEXT_COPY_KEY,
    CONTEXT_OPEN_MEDIA_KEY, MSG_SEARCH_MESSAGES_PROMPT_KEY, MSG_SEARCH_RESULTS_FORMAT_KEY,
    MSG_SEARCH_NO_RESULTS_KEY, MSG_SEARCH_CLOSED_KEY, MEDIA_VOICE, MESSAGES_LIMIT,
    MSG_LOAD_OLDER_KEY, MSG_DOWNLOADING_KEY, DOWNLOADABLE_MEDIA, SAFE_OPEN_EXTENSIONS,
    SNIPPET_LENGTH, REPLY_PREFIX_FORMAT_KEY, APP_TITLE_KEY, MESSAGE_FORMAT_KEY, SENDER_YOU_KEY,
    MSG_NO_TEXT_KEY, MSG_LOADING_KEY, STATUS_READY_KEY, TIME_FORMAT, DATE_TIME_FORMAT,
    MEDIA_FORMAT_KEY
)

class MessageListMixin:
    """The message area: the conversation, its other views, and how messages read.

    Mixed into MainFrame, which owns the widgets and the shared state.
    """

    def load_messages(self, focus_messages=False):
        self.message_view = None
        self.marked = set()
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        mark_read = self.settings.get(SETTING_MARK_READ_ON_OPEN)
        self.telegram_manager.load_messages(
            dialog_id, self.on_ui_thread(self.show_messages, dialog_id, focus_messages, mark_read),
            mark_read=mark_read
        )

    def show_messages(self, messages, dialog_id, focus_messages, marked_read):
        # The user may have opened another chat while this one was loading.
        if dialog_id != self.current_dialog_id:
            return
        self.messages = messages
        # A full page means Telegram most likely has more before it.
        self.has_older = len(messages) == MESSAGES_LIMIT
        self.render_messages(len(messages) - 1)
        chat = self.find_known_dialog(dialog_id)
        if chat is not None and messages:
            # The conversation is fresher than the chat list's preview of it.
            chat["last_message"] = messages[-1]
            self.refresh_dialog_row(chat)
        if marked_read:
            self.set_unread(dialog_id, 0)
        self.enable_chat(True)
        self.set_status(STATUS_READY_KEY)
        if focus_messages:
            self.messages_list.SetFocus()

    def render_messages(self, selected_message_index):
        """Refill the list; when older messages exist, its first row is the "load older" action."""
        items = [self.format_message(message) for message in self.messages]
        if self.has_older:
            items.insert(0, self.i18n.get_string(MSG_LOAD_OLDER_KEY))
        self.messages_list.Set(items)
        if self.messages:
            self.messages_list.SetSelection(selected_message_index + self.message_offset())
        # Setting the selection from code raises no event, so refresh the preview here.
        self.update_preview()

    def update_preview(self):
        """Show the selected message in full below the list."""
        message = self.selected_message()
        if message is None:
            # Nothing selected, or the "load older messages" row.
            self.preview_text.ChangeValue("")
            return
        self.preview_text.ChangeValue(self.i18n.get_string(PREVIEW_FORMAT_KEY).format(
            sender=self.sender_name(message),
            time=message["date"].astimezone().strftime(DATE_TIME_FORMAT),
            text=self.message_text(message)
        ))

    def message_offset(self):
        return 1 if self.has_older else 0

    def append_message(self, message):
        # Search results are a fixed list; the message shows up once the search is closed.
        if self.message_view is not None:
            return
        if any(shown["id"] == message["id"] for shown in self.messages):
            return
        self.messages.append(message)
        count = self.messages_list.GetCount()
        was_at_end = self.messages_list.GetSelection() in (wx.NOT_FOUND, count - 1)
        self.messages_list.Append(self.format_message(message))
        # Follow the conversation only if the user is not reading older messages.
        if was_at_end:
            self.messages_list.SetSelection(count)
            self.update_preview()

    def remove_message(self, message_id):
        for index, message in enumerate(self.messages):
            if message["id"] == message_id:
                break
        else:
            return
        if self.reply_to is message or self.editing is message:
            self.set_compose()
        del self.messages[index]
        self.marked.discard(message_id)
        # Re-render rather than delete one row: replies quoting this message change too.
        self.render_messages(min(index, len(self.messages) - 1))

    def load_older_messages(self):
        self.is_busy = True
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        self.telegram_manager.load_messages(
            dialog_id, self.on_ui_thread(self.show_older_messages, dialog_id),
            before_id=self.messages[0]["id"]
        )

    def show_older_messages(self, older, dialog_id):
        self.is_busy = False
        if dialog_id != self.current_dialog_id:
            return
        self.messages = older + self.messages
        self.has_older = len(older) == MESSAGES_LIMIT
        # Land on the message just before the ones already read, so Up keeps going back in time.
        self.render_messages(max(len(older) - 1, 0))
        self.set_status(STATUS_READY_KEY)

    def selected_message(self):
        index = self.messages_list.GetSelection() - self.message_offset()
        if 0 <= index < len(self.messages):
            return self.messages[index]
        return None

    def actionable_message(self):
        """The selected message, unless it is a scheduled one: those are not in the chat yet,
        so they can only be cancelled or copied."""
        if self.message_view == MESSAGE_VIEW_SCHEDULED:
            return None
        return self.selected_message()

    def on_activate_message(self, event):
        index = self.messages_list.GetSelection()
        if index == wx.NOT_FOUND or self.is_busy:
            return
        if self.has_older and index == 0:
            self.load_older_messages()
            return
        # Enter while a voice note plays stops it, like a play/stop button.
        if self.stop_playback():
            return
        message = self.messages[index - self.message_offset()]
        if message["poll"]:
            self.on_vote_menu(event)
        elif message["media"] in DOWNLOADABLE_MEDIA:
            self.download_media(message)

    def on_message_context_menu(self, event):
        self.select_item_under_mouse(self.messages_list, event)
        message = self.selected_message()
        if message is None:
            return
        if self.message_view == MESSAGE_VIEW_SCHEDULED:
            # Not sent yet, so there is nothing to reply to, pin or forward.
            entries = [(CONTEXT_DELETE_KEY, self.on_delete_menu)]
            if message["text"]:
                entries.append((CONTEXT_COPY_KEY, self.on_copy_message))
            self.show_context_menu(entries)
            return
        # Same order as Telegram's own desktop apps, and only what works on this message.
        chat = self.current_dialog()
        has_media = message["media"] in DOWNLOADABLE_MEDIA
        entries = []
        if message["poll"] and not message["poll"]["closed"]:
            entries.append((CONTEXT_VOTE_KEY, self.on_vote_menu))
        entries.append((CONTEXT_REACT_KEY, self.on_react_menu))
        if chat["can_send"]:
            entries.append((CONTEXT_REPLY_KEY, self.on_reply_menu))
        if message["outgoing"] and message["text"]:
            entries.append((CONTEXT_EDIT_KEY, self.on_edit_menu))
        if chat["can_pin"]:
            entries.append((CONTEXT_UNPIN_KEY if message["pinned"] else CONTEXT_PIN_KEY, self.on_pin_menu))
        entries.append((CONTEXT_FORWARD_KEY, self.on_forward_menu))
        if message["text"]:
            entries.append((CONTEXT_COPY_KEY, self.on_copy_message))
        if chat["has_links"]:
            entries.append((CONTEXT_COPY_LINK_KEY, self.on_copy_link_menu))
        if has_media:
            entries.append((CONTEXT_OPEN_MEDIA_KEY, self.on_activate_message))
            entries.append((CONTEXT_SAVE_AS_KEY, self.on_save_as_menu))
        entries.append((CONTEXT_READ_MESSAGE_KEY, self.on_read_message_menu))
        is_marked = message["id"] in self.marked
        entries.append((CONTEXT_UNSELECT_KEY if is_marked else CONTEXT_SELECT_KEY, self.on_mark_menu))
        if self.can_delete(message):
            entries.append((CONTEXT_DELETE_KEY, self.on_delete_menu))
        self.show_context_menu(entries)

    def on_save_as_menu(self, event):
        message = self.actionable_message()
        if message is None or message["media"] not in DOWNLOADABLE_MEDIA or self.is_busy:
            return
        with wx.DirDialog(self, self.i18n.get_string(MSG_CHOOSE_SAVE_FOLDER_KEY)) as folder_dialog:
            if folder_dialog.ShowModal() != wx.ID_OK:
                return
            folder = folder_dialog.GetPath()
        self.is_busy = True
        self.set_status(MSG_DOWNLOADING_KEY)
        self.telegram_manager.download_media(
            self.current_dialog_id, message["id"], self.on_ui_thread(self.on_media_saved), folder=folder
        )

    def on_media_saved(self, path):
        self.is_busy = False
        self.announce(self.i18n.get_string(MSG_SAVED_FORMAT_KEY).format(path=path))

    def download_media(self, message):
        cache_key = (self.current_dialog_id, message["id"])
        cached = self.downloaded.get(cache_key)
        if cached and os.path.exists(cached):
            self.open_media(cached, cache_key, message["media"])
            return
        self.is_busy = True
        self.set_status(MSG_DOWNLOADING_KEY)
        self.telegram_manager.download_media(
            self.current_dialog_id, message["id"],
            self.on_ui_thread(self.open_media, cache_key, message["media"])
        )

    def open_media(self, path, cache_key, media):
        self.is_busy = False
        self.downloaded[cache_key] = path
        self.set_status(STATUS_READY_KEY)
        if media == MEDIA_VOICE and audio.AVAILABLE:
            self.play_voice(path)
        # Only hand known media formats to their default app; anything else
        # could be a program, so just show the folder it was saved in.
        elif os.path.splitext(path)[1].lower() in SAFE_OPEN_EXTENSIONS:
            wx.LaunchDefaultApplication(path)
        else:
            wx.LaunchDefaultApplication(os.path.dirname(path))

    def on_search_messages_menu(self, event):
        if self.current_dialog_id is None or self.is_busy:
            return
        with wx.TextEntryDialog(
            self, self.i18n.get_string(MSG_SEARCH_MESSAGES_PROMPT_KEY),
            self.i18n.get_string(APP_TITLE_KEY), self.search_query or ""
        ) as search_dialog:
            if search_dialog.ShowModal() != wx.ID_OK:
                return
            query = search_dialog.GetValue().strip()
        if not query:
            return
        self.is_busy = True
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        self.telegram_manager.search_messages(
            dialog_id, query, self.on_ui_thread(self.show_search_results, dialog_id, query)
        )

    def show_search_results(self, results, dialog_id, query):
        self.is_busy = False
        if dialog_id != self.current_dialog_id:
            return
        if not results:
            self.notify(MSG_SEARCH_NO_RESULTS_KEY)
            return
        self.search_query = query
        self.show_message_list(MESSAGE_VIEW_SEARCH, results)
        self.announce(
            self.i18n.get_string(MSG_SEARCH_RESULTS_FORMAT_KEY).format(count=len(results))
        )

    def show_message_list(self, view, messages):
        """Replace the conversation in the message area with another list; Escape brings it back."""
        self.message_view = view
        self.marked = set()
        self.set_compose()
        self.messages = messages
        self.has_older = False
        self.render_messages(len(messages) - 1)
        self.messages_list.SetFocus()

    def close_search(self):
        self.notify(MSG_SEARCH_CLOSED_KEY)
        self.load_messages(focus_messages=True)

    def open_message_view(self, view):
        if self.current_dialog_id is None or self.is_busy:
            return
        self.is_busy = True
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        self.telegram_manager.load_message_view(
            dialog_id, view, self.on_ui_thread(self.on_message_view_loaded, dialog_id, view)
        )

    def on_message_view_loaded(self, messages, dialog_id, view):
        self.is_busy = False
        if dialog_id != self.current_dialog_id:
            return
        name = self.i18n.get_string(view)
        if not messages:
            self.announce(self.i18n.get_string(MSG_VIEW_EMPTY_KEY).format(view=name))
            return
        self.show_message_list(view, messages)
        self.announce(
            self.i18n.get_string(MSG_VIEW_RESULTS_FORMAT_KEY).format(view=name, count=len(messages))
        )

    def sender_name(self, message):
        if message["outgoing"]:
            return self.i18n.get_string(SENDER_YOU_KEY)
        return message["sender"]

    def poll_text(self, poll):
        options = []
        for option in poll["options"]:
            details = []
            if option["chosen"]:
                details.append(self.i18n.get_string(POLL_CHOSEN_KEY))
            # Telegram hides the counts until this account has voted.
            if option["voters"] is not None:
                details.append(self.i18n.get_string(POLL_VOTERS_FORMAT_KEY).format(count=option["voters"]))
            if details:
                options.append(self.i18n.get_string(POLL_OPTION_FORMAT_KEY).format(
                    text=option["text"], details="، ".join(details)
                ))
            else:
                options.append(option["text"])
        return self.i18n.get_string(POLL_FORMAT_KEY).format(
            closed=self.i18n.get_string(POLL_CLOSED_SUFFIX_KEY) if poll["closed"] else "",
            question=poll["question"], options="، ".join(options)
        )

    def message_text(self, message):
        if message["poll"]:
            return self.poll_text(message["poll"])
        text = message["text"]
        if message["media"]:
            text = self.i18n.get_string(MEDIA_FORMAT_KEY).format(
                media=self.i18n.get_string(message["media"]), text=text
            ).strip()
        return text or self.i18n.get_string(MSG_NO_TEXT_KEY)

    def message_snippet(self, message):
        text = " ".join(self.message_text(message).split())
        if len(text) > SNIPPET_LENGTH:
            text = text[:SNIPPET_LENGTH] + "…"
        return text

    def on_read_message_menu(self, event):
        message = self.selected_message()
        if message is None:
            return
        header = self.i18n.get_string(READ_MESSAGE_HEADER_FORMAT_KEY).format(
            sender=self.sender_name(message),
            time=message["date"].astimezone().strftime(DATE_TIME_FORMAT)
        )
        # The list squeezes a message into one row; here it keeps its own line breaks.
        self.show_text(READ_MESSAGE_TITLE_KEY, header + "\n\n" + self.message_text(message))

    def format_message(self, message):
        local_date = message["date"].astimezone()
        is_today = local_date.date() == datetime.date.today()
        text = self.message_text(message)
        # The replied-to message can only be quoted if it is among the loaded ones.
        replied = next((m for m in self.messages if m["id"] == message["reply_to"]), None)
        if replied is not None:
            text = self.i18n.get_string(REPLY_PREFIX_FORMAT_KEY).format(
                sender=self.sender_name(replied), quote=self.message_snippet(replied), text=text
            )
        if message["pinned"]:
            text = self.i18n.get_string(PINNED_FORMAT_KEY).format(text=text)
        if message["reactions"]:
            text = self.i18n.get_string(REACTIONS_FORMAT_KEY).format(
                text=text,
                reactions="، ".join(
                    self.i18n.get_string(REACTION_COUNT_FORMAT_KEY).format(emoji=emoji, count=count)
                    for emoji, count in message["reactions"]
                )
            )
        line = self.i18n.get_string(MESSAGE_FORMAT_KEY).format(
            sender=self.sender_name(message),
            # A row is one line: the list would drop the line breaks and glue the
            # words on either side together, so turn them into spaces first.
            text=" ".join(text.split()),
            time=local_date.strftime(TIME_FORMAT if is_today else DATE_TIME_FORMAT)
        )
        if message["id"] in self.marked:
            # First thing on the row, so it is heard before anything else.
            line = self.i18n.get_string(MARKED_FORMAT_KEY).format(text=line)
        return line
