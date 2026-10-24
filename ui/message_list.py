import datetime
import os
import subprocess
import wx
from core.speech import speak
from core import audio
from core.settings import SETTING_VOICE_SPEED, SETTING_MARK_READ_ON_OPEN, SETTING_MESSAGE_STATS, SETTING_TIME_STYLE
from ui.layout import duration_text, file_kind, file_size
from core.constants import (
    FEEDBACK_WAITING,
    FEEDBACK_NAVIGATION,
    FEEDBACK_COUNT,
    FEEDBACK_UNAVAILABLE,
    FEEDBACK_COUNT,
    BOT_START_ROW_KEY,
    CONTEXT_MORE_KEY, CONTEXT_TRANSLATE_KEY, CONTEXT_AUDIENCE_KEY, CONTEXT_VOICE_SPEED_KEY, CONTEXT_REMIND_KEY,
    CONTEXT_UNMARK_ALL_KEY, CONTEXT_REPORT_KEY, PLAYABLE_MEDIA,
    PREVIEW_FORMAT_KEY, CONTEXT_COPY_LINK_KEY, CONTEXT_SAVE_AS_KEY, CONTEXT_DESCRIBE_IMAGE_KEY, DESCRIBABLE_MEDIA,
    CONTEXT_MESSAGE_SENDER_FORMAT_KEY,
    MESSAGE_STATS_BEFORE, STATS_AFTER_FORMAT, STATS_BEFORE_FORMAT, STATS_SEPARATOR, TIME_STYLE_NUMBERS,
    TIME_STYLE_NONE, TIME_STYLE_WORDS_12, MONTH_KEY_PREFIX, TIME_AM_KEY, TIME_PM_KEY, TIME_12_FORMAT,
    DATE_WORDS_FORMAT_KEY, DATE_WORDS_YEAR_FORMAT_KEY, DATE_TIME_WORDS_FORMAT_KEY, MESSAGE_NO_TIME_FORMAT, CONTEXT_SELECT_KEY, CONTEXT_UNSELECT_KEY,
    MSG_CHOOSE_SAVE_FOLDER_KEY, MSG_SAVED_FORMAT_KEY, CONTEXT_READ_MESSAGE_KEY, READ_MESSAGE_TITLE_KEY, READ_MESSAGE_HEADER_FORMAT_KEY, MARKED_FORMAT_KEY, MESSAGE_VIEW_SEARCH, MESSAGE_VIEW_SCHEDULED, MSG_VIEW_RESULTS_FORMAT_KEY, MSG_VIEW_EMPTY_KEY,
    POLL_FORMAT_KEY, POLL_OPTION_FORMAT_KEY, POLL_CHOSEN_KEY, POLL_VOTERS_FORMAT_KEY,
    POLL_CLOSED_SUFFIX_KEY, CONTEXT_POLL_VOTERS_KEY, CONTEXT_CLOSE_POLL_KEY, QUIZ_FORMAT_KEY, POLL_CORRECT_KEY, POLL_EXPLANATION_FORMAT_KEY, CONTEXT_VOTE_KEY, CONTEXT_REACT_KEY, REACTIONS_FORMAT_KEY,
    REACTION_COUNT_FORMAT_KEY, CONTEXT_FORWARD_KEY, CONTEXT_PIN_KEY, CONTEXT_UNPIN_KEY,
    PINNED_FORMAT_KEY, CONTEXT_REPLY_KEY, CONTEXT_EDIT_KEY, CONTEXT_DELETE_KEY, CONTEXT_COPY_KEY,
    CONTEXT_OPEN_MEDIA_KEY, MSG_SEARCH_MESSAGES_PROMPT_KEY, MSG_SEARCH_RESULTS_FORMAT_KEY,
    MSG_SEARCH_NO_RESULTS_KEY, MSG_SEARCH_CLOSED_KEY, MEDIA_VOICE, MESSAGES_LIMIT,
    MSG_LOAD_OLDER_KEY, MSG_DOWNLOADING_KEY, DOWNLOADABLE_MEDIA, RUNNABLE_EXTENSIONS, INTERNET_ZONE_MARK,
    CONTEXT_SHOW_IN_FOLDER_KEY, MSG_RUN_PROGRAM_FORMAT_KEY,
    PLAYABLE_MEDIA, MSG_FETCHING_SOUND_KEY, MSG_PLAYING_KEY, VOICE_SPEEDS, SERVICE_NAMES_SEPARATOR_KEY,
    SNIPPET_LENGTH, REPLY_PREFIX_FORMAT_KEY, APP_TITLE_KEY, MESSAGE_FORMAT_KEY, SENDER_YOU_KEY,
    MESSAGE_NO_SENDER_FORMAT_KEY, MESSAGE_NO_SENDER_NO_TIME_FORMAT, CATEGORY_BROADCASTS,
    MSG_NO_TEXT_KEY, MSG_LOADING_KEY, STATUS_READY_KEY, TIME_FORMAT, DATE_TIME_FORMAT,
    MEDIA_FORMAT_KEY, MESSAGE_READ_FORMAT_KEY, MESSAGE_UNREAD_FORMAT_KEY, BUTTONS_FORMAT_KEY, CONTEXT_BUTTONS_KEY,
    CONTEXT_OPEN_LINK_KEY, CONTEXT_MESSAGE_STATS_KEY, MSG_NO_MESSAGE_STATS_KEY, AUDIENCE_FORWARDS_FORMAT_KEY,
    MESSAGE_VIEW_COMMENTS, MESSAGE_VIEW_TOPIC, COMMENTS_FORMAT_KEY, CONTEXT_COMMENTS_KEY,
    MSG_NO_COMMENTS_KEY, COMMENTS_TITLE_FORMAT_KEY, MSG_NOT_FORUM_KEY, MSG_CHOOSE_TOPIC_KEY,
    TOPIC_CHOICE_FORMAT_KEY, TOPIC_TITLE_FORMAT_KEY, MSG_THREAD_OPENED_FORMAT_KEY, THREAD_LABEL_FORMAT_KEY,
    AUDIENCE_TITLE_KEY, AUDIENCE_READERS_FORMAT_KEY, AUDIENCE_NO_READERS_KEY, AUDIENCE_READERS_UNKNOWN_KEY,
    AUDIENCE_REACTIONS_KEY, AUDIENCE_REACTION_FORMAT_KEY, AUDIENCE_NO_REACTIONS_KEY,
    FORWARDED_FORMAT_KEY, FORWARDED_UNKNOWN_FORMAT_KEY, EDITED_FORMAT_KEY, VIEWS_FORMAT_KEY,
    TRANSLATION_TITLE_KEY, MSG_NOTHING_TO_TRANSLATE_KEY, MSG_NO_STORIES_KEY, MSG_CHOOSE_STORY_PERSON_KEY,
    STORY_PERSON_FORMAT_KEY, MSG_CHOOSE_STORY_KEY, STORY_FORMAT_KEY, MSG_DOWNLOAD_PROGRESS_FORMAT_KEY,
    AUDIENCE_VIEWS_FORMAT_KEY, AUDIENCE_FORWARDS_FORMAT_KEY, MESSAGE_VIEW_AROUND, NEW_FROM_HERE_FORMAT_KEY,
    MSG_NEW_MESSAGES_FORMAT_KEY, MSG_JUMPED_KEY, MSG_MESSAGE_NOT_FOUND_KEY, CONTEXT_GO_TO_REPLY_KEY,
    MSG_NOT_A_REPLY_KEY, MSG_DATE_PROMPT_KEY, ERR_BAD_DATE_KEY, MSG_NOTHING_ON_DATE_KEY, DATE_INPUT_FORMATS,
    MSG_SEARCH_ALL_PROMPT_KEY, MSG_SEARCH_ALL_RESULTS_FORMAT_KEY, SEARCH_ALL_ROW_FORMAT_KEY,
    FILE_LABEL_SEPARATOR_KEY, MEDIA_FILE
)

class MessageListMixin:
    """The message area: the conversation, its other views, and how messages read.

    Mixed into MainFrame, which owns the widgets and the shared state.
    """

    def load_messages(self, focus_messages=False):
        self.message_view = None
        if self.thread is not None:
            # Back from comments or a topic: the list is the chat's own again, and so is its name.
            self.thread = None
            self.show_chat_name(self.find_known_dialog(self.current_dialog_id))
        self.marked = set()
        dialog_id = self.current_dialog_id
        mark_read = self.settings.get(SETTING_MARK_READ_ON_OPEN)
        remembered = self.chat_memory.get(dialog_id)
        # Only on coming into the chat, not on coming back to it from a view of it.
        if remembered is not None and not self.unread_on_open and not self.messages:
            # As it was left, straight away; what Telegram sends next only brings what changed since.
            messages, has_older = remembered
            self.show_messages(list(messages), dialog_id, focus_messages, False, remembered=True)
            self.has_older = has_older
            self.render_messages(self.messages_list.GetSelection() - self.message_offset())
        else:
            self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.load_messages(
            dialog_id, self.on_ui_thread(self.show_messages, dialog_id, focus_messages, mark_read),
            mark_read=mark_read
        )

    def show_messages(self, messages, dialog_id, focus_messages, marked_read, remembered=False):
        # The user may have opened another chat while this one was loading.
        if dialog_id != self.current_dialog_id:
            return
        if self.showing_remembered and not remembered:
            self.show_fresh_messages(messages, dialog_id, marked_read)
            return
        self.showing_remembered = remembered
        self.messages = messages
        # A full page means Telegram most likely has more before it.
        self.has_older = len(messages) == MESSAGES_LIMIT
        # Entering a chat with unread messages lands on the first of them, not on the last.
        unread, self.unread_on_open = self.unread_on_open, 0
        first_unread = max(len(messages) - unread, 0) if unread and messages else None
        self.first_unread_id = messages[first_unread]["id"] if first_unread is not None else None
        self.render_messages(len(messages) - 1 if first_unread is None else first_unread)
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
        if self.pending_jump is not None:
            target, self.pending_jump = self.pending_jump, None
            self.jump_to_message(target)
        elif first_unread is not None:
            self.announce(self.i18n.get_string(MSG_NEW_MESSAGES_FORMAT_KEY).format(count=unread), FEEDBACK_COUNT)

    def show_fresh_messages(self, messages, dialog_id, marked_read):
        """Telegram's answer for a chat already shown from memory: change only what differs, and keep
        the user where they are, on the same message."""
        self.showing_remembered = False
        if marked_read:
            self.set_unread(dialog_id, 0)
        self.set_status(STATUS_READY_KEY)
        if self.message_view is not None or self.thread is not None:
            # A view or a topic was opened meanwhile; the chat is loaded again on coming back to it.
            return
        if messages == self.messages:
            return
        selected = self.selected_message()
        on_last = self.messages_list.GetSelection() == self.messages_list.GetCount() - 1
        self.messages = messages
        self.has_older = len(messages) == MESSAGES_LIMIT
        ids = [message["id"] for message in messages]
        if selected is not None and selected["id"] in ids and not on_last:
            self.render_messages(ids.index(selected["id"]))
        else:
            self.render_messages(len(messages) - 1)
        chat = self.find_known_dialog(dialog_id)
        if chat is not None and messages:
            chat["last_message"] = messages[-1]
            self.refresh_dialog_row(chat)

    def jump_to_message(self, message_id):
        """Put the selection on a message of this chat, fetching its part of the conversation if need be."""
        for index, message in enumerate(self.messages):
            if message["id"] == message_id:
                self.messages_list.SetSelection(index + self.message_offset())
                self.update_preview()
                self.messages_list.SetFocus()
                return
        # Inside a topic or under a post only what is loaded can be reached.
        if self.is_busy or self.thread is not None:
            self.notify(MSG_MESSAGE_NOT_FOUND_KEY)
            return
        self.is_busy = True
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        self.telegram_manager.load_messages_around(
            dialog_id, message_id, self.on_ui_thread(self.show_part, dialog_id, message_id, MSG_MESSAGE_NOT_FOUND_KEY)
        )

    def show_part(self, messages, dialog_id, message_id, empty_key):
        """Show a stretch of the conversation away from its end, on `message_id` (None: on its first message)."""
        self.is_busy = False
        self.set_status(STATUS_READY_KEY)
        if dialog_id != self.current_dialog_id:
            return
        found = message_id is None or any(message["id"] == message_id for message in messages)
        if not messages or not found:
            self.notify(empty_key)
            return
        self.show_message_list(MESSAGE_VIEW_AROUND, messages)
        target = 0 if message_id is None else next(i for i, m in enumerate(messages) if m["id"] == message_id)
        self.messages_list.SetSelection(target + self.message_offset())
        self.update_preview()
        self.notify(MSG_JUMPED_KEY)

    def on_go_to_reply_menu(self, event):
        message = self.selected_message()
        if message is None:
            return
        if not message["reply_to"]:
            self.notify(MSG_NOT_A_REPLY_KEY)
        else:
            self.jump_to_message(message["reply_to"])

    def on_go_to_date_menu(self, event):
        if self.current_dialog_id is None or self.is_busy or self.thread is not None:
            return
        typed = self.ask_text(MSG_DATE_PROMPT_KEY)
        if not typed:
            return
        date = None
        for date_format in DATE_INPUT_FORMATS:
            try:
                date = datetime.datetime.strptime(typed, date_format)
                break
            except ValueError:
                pass
        if date is None:
            self.show_error(ERR_BAD_DATE_KEY)
            return
        self.is_busy = True
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        # The day as the user's clock has it, from its first minute.
        self.telegram_manager.load_messages_from(
            dialog_id, date.astimezone(), self.on_ui_thread(self.show_part, dialog_id, None, MSG_NOTHING_ON_DATE_KEY)
        )

    def on_search_all_menu(self, event):
        query = self.ask_text(MSG_SEARCH_ALL_PROMPT_KEY)
        if query:
            self.set_status(MSG_LOADING_KEY)
            self.telegram_manager.search_all(query, self.on_ui_thread(self.choose_search_result))

    def choose_search_result(self, results):
        self.set_status(STATUS_READY_KEY)
        if not results:
            self.notify(MSG_SEARCH_NO_RESULTS_KEY)
            return
        with wx.SingleChoiceDialog(
            self, self.i18n.get_string(MSG_SEARCH_ALL_RESULTS_FORMAT_KEY).format(count=len(results)),
            self.i18n.get_string(APP_TITLE_KEY), [
                self.i18n.get_string(SEARCH_ALL_ROW_FORMAT_KEY).format(
                    chat=result["chat"]["title"], sender=self.sender_name(result["message"]),
                    text=self.message_snippet(result["message"]),
                    time=result["message"]["date"].astimezone().strftime(DATE_TIME_FORMAT)
                )
                for result in results
            ]
        ) as results_dialog:
            if results_dialog.ShowModal() != wx.ID_OK:
                return
            result = results[results_dialog.GetSelection()]
        if result["chat"]["id"] == self.current_dialog_id:
            self.jump_to_message(result["message"]["id"])
        else:
            # Its chat has to be entered and loaded first; the message is gone to after that.
            self.pending_jump = result["message"]["id"]
            self.open_chat(result["chat"])

    def render_messages(self, selected_message_index):
        """Refill the list; when older messages exist, its first row is the "load older" action."""
        items = [self.format_message(message) for message in self.messages]
        if self.has_older:
            items.insert(0, self.i18n.get_string(MSG_LOAD_OLDER_KEY))
        if self.upload_row() is not None:
            # Files still on their way up to this chat, after everything already in it.
            items.append(self.upload_row())
        elif self.start_row_wanted():
            # A bot that was never started, or a link that says what to start it with: the way in, in sight.
            items.append(self.i18n.get_string(BOT_START_ROW_KEY))
        self.messages_list.Set(items)
        if self.messages:
            self.messages_list.SetSelection(selected_message_index + self.message_offset())
        elif items:
            self.messages_list.SetSelection(len(items) - 1)
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
            time=self.time_text(message["date"], True),
            text=self.message_text(message)
        ))

    def message_offset(self):
        return 1 if self.has_older else 0

    def append_message(self, message):
        # Search results are a fixed list; the message shows up once the search is closed.
        # An open topic or post grows only by what is written into it.
        if self.message_view is not None and not self.belongs_to_thread(message):
            return
        if any(shown["id"] == message["id"] for shown in self.messages):
            return
        # Rows of messages, not counting the one for files still going up.
        count = len(self.messages) + self.message_offset()
        was_at_end = self.messages_list.GetSelection() in (wx.NOT_FOUND, count - 1)
        shown = self.upload_row_shown()
        self.messages.append(message)
        if shown:
            self.messages_list.Insert(self.format_message(message), count)
        else:
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
        message = self.selected_message()
        if message is None and self.start_row_wanted() and self.upload_row() is None \
                and index == self.messages_list.GetCount() - 1:
            self.on_bot_start_menu(event)
            return
        if message is None:
            # The row of files still going up: nothing to open yet, but they can be stopped.
            if self.upload_row_shown():
                self.on_cancel_upload_menu(event)
            return
        if message["poll"]:
            self.on_vote_menu(event)
        elif message["media"] in DOWNLOADABLE_MEDIA:
            self.download_media(message)
        elif message["buttons"]:
            self.on_buttons_menu(event)
        elif message["comments"] is not None:
            self.on_comments_menu(event)

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
        chat = self.shown_chat()
        has_media = message["media"] in DOWNLOADABLE_MEDIA
        entries = []
        if message["buttons"]:
            entries.append((CONTEXT_BUTTONS_KEY, self.on_buttons_menu))
        if message["poll"] and not message["poll"]["closed"]:
            entries.append((CONTEXT_VOTE_KEY, self.on_vote_menu))
        if message["poll"] and message["poll"].get("public"):
            entries.append((CONTEXT_POLL_VOTERS_KEY, self.on_poll_voters_menu))
        if message["poll"] and not message["poll"]["closed"] and message["outgoing"]:
            entries.append((CONTEXT_CLOSE_POLL_KEY, self.on_close_poll_menu))
        entries.append((CONTEXT_REACT_KEY, self.on_react_menu))
        if chat["can_send"]:
            entries.append((CONTEXT_REPLY_KEY, self.on_reply_menu))
        if message["outgoing"] and message["text"]:
            entries.append((CONTEXT_EDIT_KEY, self.on_edit_menu))
        if chat["can_pin"]:
            entries.append((CONTEXT_UNPIN_KEY if message["pinned"] else CONTEXT_PIN_KEY, self.on_pin_menu))
        if self.can_message_sender(message):
            # Already worded, with the person's name in it: a text that is no key is shown as it is.
            label = self.i18n.get_string(CONTEXT_MESSAGE_SENDER_FORMAT_KEY).format(name=message["sender"])
            entries.append((label, self.on_message_sender_menu))
        entries.append((CONTEXT_FORWARD_KEY, self.on_forward_menu))
        if message["text"]:
            entries.append((CONTEXT_COPY_KEY, self.on_copy_message))
        if chat["has_links"]:
            entries.append((CONTEXT_COPY_LINK_KEY, self.on_copy_link_menu))
        if message["reply_to"]:
            entries.append((CONTEXT_GO_TO_REPLY_KEY, self.on_go_to_reply_menu))
        if message["links"]:
            entries.append((CONTEXT_OPEN_LINK_KEY, self.on_open_link_menu))
        if message["comments"] is not None:
            entries.append((CONTEXT_COMMENTS_KEY, self.on_comments_menu))
        if self.message_stats(message):
            entries.append((CONTEXT_MESSAGE_STATS_KEY, self.on_message_stats_menu))
        if has_media:
            entries.append((CONTEXT_OPEN_MEDIA_KEY, self.on_activate_message))
            entries.append((CONTEXT_SHOW_IN_FOLDER_KEY, self.on_show_in_folder_menu))
            entries.append((CONTEXT_SAVE_AS_KEY, self.on_save_as_menu))
        if message["media"] in DESCRIBABLE_MEDIA:
            entries.append((CONTEXT_DESCRIBE_IMAGE_KEY, self.on_describe_image_menu))
        entries.append((CONTEXT_READ_MESSAGE_KEY, self.on_read_message_menu))
        is_marked = message["id"] in self.marked
        entries.append((CONTEXT_UNSELECT_KEY if is_marked else CONTEXT_SELECT_KEY, self.on_mark_menu))
        more = []
        if message["text"]:
            more.append((CONTEXT_TRANSLATE_KEY, self.on_translate_menu))
        if message["outgoing"] and not self.is_private_chat(chat):
            more.append((CONTEXT_AUDIENCE_KEY, self.on_audience_menu))
        if message["media"] in PLAYABLE_MEDIA:
            more.append((CONTEXT_VOICE_SPEED_KEY, self.on_voice_speed_menu))
        more.append((CONTEXT_REMIND_KEY, self.on_remind_menu))
        if self.marked:
            more.append((CONTEXT_UNMARK_ALL_KEY, self.on_unmark_all_menu))
        if not message["outgoing"]:
            more.append((CONTEXT_REPORT_KEY, self.on_report_menu))
        # Less often wanted: one step aside, so the menu stays short.
        entries.append((CONTEXT_MORE_KEY, more))
        if self.can_delete(message):
            entries.append((CONTEXT_DELETE_KEY, self.on_delete_menu))
        self.show_context_menu(entries)

    def on_save_as_menu(self, event):
        message = self.actionable_message()
        if message is None or message["media"] not in DOWNLOADABLE_MEDIA:
            return
        with wx.DirDialog(self, self.i18n.get_string(MSG_CHOOSE_SAVE_FOLDER_KEY)) as folder_dialog:
            if folder_dialog.ShowModal() != wx.ID_OK:
                return
            folder = folder_dialog.GetPath()
        self.set_status(MSG_DOWNLOADING_KEY)
        self.telegram_manager.download_media(
            self.peer(self.current_dialog_id), message["id"], self.on_transfer_done(self.on_media_saved), folder=folder,
            on_progress=self.progress_reporter(MSG_DOWNLOAD_PROGRESS_FORMAT_KEY)
        )

    def on_media_saved(self, path):
        self.announce(self.i18n.get_string(MSG_SAVED_FORMAT_KEY).format(path=path))

    def download_media(self, message, then=None):
        """Fetch the message's attachment into the downloads, unless it is there already, then open it,
        or hand it to `then`(path, cache_key, media) instead."""
        then = then or self.open_media
        cache_key = (self.peer(self.current_dialog_id), message["id"])
        cached = self.downloaded.get(cache_key)
        if cached and os.path.exists(cached):
            then(cached, cache_key, message["media"])
            return
        if cache_key in self.downloading:
            # Already on its way: Enter again only says so.
            self.notify(MSG_DOWNLOADING_KEY, FEEDBACK_WAITING)
            return
        self.downloading.add(cache_key)
        self.set_status(MSG_DOWNLOADING_KEY)
        self.telegram_manager.download_media(
            self.peer(self.current_dialog_id), message["id"],
            self.on_transfer_done(
                then, cache_key, message["media"], cleanup=lambda: self.downloading.discard(cache_key)
            ),
            folder=self.downloads_folder(), on_progress=self.progress_reporter(MSG_DOWNLOAD_PROGRESS_FORMAT_KEY)
        )

    def listen(self):
        """Space on a voice message or a song: play it from Telegram as it arrives, as Telegram's own
        apps do, or stop it if it is playing. False if the selected message has no sound to play."""
        message = self.selected_message()
        if message is None or message["media"] not in PLAYABLE_MEDIA or not audio.AVAILABLE:
            return False
        if self.stop_playback():
            return True
        key = (self.peer(self.current_dialog_id), message["id"])
        # Telegram tells a sound's length with it, before any of it arrives.
        self.player.duration = (message.get("file") or {}).get("duration") or 0
        buffer = audio.StreamBuffer()
        # Whatever happens to the request reaches the player through the buffer.
        self.stream_request = self.telegram_manager.stream_media(key[0], key[1], buffer, lambda result, error_key: None)
        self.set_status(MSG_PLAYING_KEY)
        self.player.play_stream(
            buffer, lambda completed, error, started: wx.CallAfter(self.on_stream_finished, key, completed, error, started),
            speed=VOICE_SPEEDS[self.settings.get(SETTING_VOICE_SPEED)]
        )
        return True

    def on_stream_finished(self, key, completed, error, started):
        if not self:
            return
        self.stream_request = None
        if error is not None and not started:
            # A song whose file must be read from its end first cannot play as it arrives: fetched
            # whole, into memory only, it plays all the same.
            self.set_status(MSG_FETCHING_SOUND_KEY)
            self.telegram_manager.fetch_media(key[0], key[1], self.on_transfer_done(self.play_voice))
            return
        self.on_playback_finished(completed, error)

    def keep_download(self, path, cache_key):
        self.downloaded[cache_key] = path
        self.set_status(STATUS_READY_KEY)
        try:
            # Only beside a file that is there: opening the mark would make an empty one otherwise.
            if not os.path.isfile(path):
                return
            with open(path + ":Zone.Identifier", "w") as mark:
                mark.write(INTERNET_ZONE_MARK)
        except OSError:
            # A drive that keeps no such marks (FAT, a network share): the file opens all the same.
            pass

    def open_media(self, path, cache_key, media):
        """Open the file itself in the program Windows has for it: a song in the player, a document
        in its editor. A program runs, so that is asked first, and Windows checks it as well."""
        self.keep_download(path, cache_key)
        if os.path.splitext(path)[1].lower() in RUNNABLE_EXTENSIONS and not self.confirm(
            self.i18n.get_string(MSG_RUN_PROGRAM_FORMAT_KEY).format(name=os.path.basename(path))
        ):
            return
        if not wx.LaunchDefaultApplication(path):
            # Nothing on this computer opens it: there it is, in its folder.
            self.reveal_file(path, cache_key, media)

    def reveal_file(self, path, cache_key, media):
        """Show the file in its folder in File Explorer, selected there."""
        self.keep_download(path, cache_key)
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])

    def on_show_in_folder_menu(self, event):
        message = self.selected_message()
        if message is None or message["media"] not in DOWNLOADABLE_MEDIA or self.is_busy:
            return
        self.download_media(message, then=self.reveal_file)

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
            self.announce(self.i18n.get_string(MSG_VIEW_EMPTY_KEY).format(view=name), FEEDBACK_UNAVAILABLE)
            return
        self.show_message_list(view, messages)
        self.announce(
            self.i18n.get_string(MSG_VIEW_RESULTS_FORMAT_KEY).format(view=name, count=len(messages))
        , FEEDBACK_COUNT)

    def on_comments_menu(self, event):
        message = self.actionable_message()
        if message is None:
            return
        if message["comments"] is None:
            self.notify(MSG_NO_COMMENTS_KEY)
            return
        title = self.i18n.get_string(COMMENTS_TITLE_FORMAT_KEY).format(text=self.message_snippet(message))
        self.open_thread({"view": MESSAGE_VIEW_COMMENTS, "id": message["id"], "title": title})

    def on_topics_menu(self, event):
        if self.current_dialog_id is None or self.is_busy:
            return
        if not self.current_dialog().get("is_forum"):
            self.notify(MSG_NOT_FORUM_KEY)
            return
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.load_topics(
            self.current_dialog_id, self.on_ui_thread(self.choose_topic, self.current_dialog_id)
        )

    def choose_topic(self, topics, dialog_id):
        self.set_status(STATUS_READY_KEY)
        if dialog_id != self.current_dialog_id:
            return
        choices = [
            self.i18n.get_string(TOPIC_CHOICE_FORMAT_KEY).format(**topic) if topic["unread"] else topic["title"]
            for topic in topics
        ]
        with wx.SingleChoiceDialog(
            self, self.i18n.get_string(MSG_CHOOSE_TOPIC_KEY), self.i18n.get_string(APP_TITLE_KEY), choices
        ) as topic_dialog:
            if topic_dialog.ShowModal() != wx.ID_OK:
                return
            topic = topics[topic_dialog.GetSelection()]
        title = self.i18n.get_string(TOPIC_TITLE_FORMAT_KEY).format(title=topic["title"])
        self.open_thread({"view": MESSAGE_VIEW_TOPIC, "id": topic["id"], "title": title})

    def open_thread(self, thread, after_sending=False):
        """Show the comments of a post or the messages of a topic in place of the conversation."""
        self.is_busy = True
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        self.telegram_manager.load_thread(
            dialog_id, thread["id"], thread["view"],
            self.on_ui_thread(self.show_thread, dialog_id, thread, after_sending)
        )

    def show_thread(self, loaded, dialog_id, thread, after_sending):
        self.is_busy = False
        if dialog_id != self.current_dialog_id:
            return
        messages = loaded["messages"]
        # Where its messages live and what they answer: everything written here goes by these.
        self.thread = dict(thread, peer=loaded["peer"], root=loaded["root"])
        self.show_message_list(thread["view"], messages)
        label = self.i18n.get_string(THREAD_LABEL_FORMAT_KEY).format(title=thread["title"])
        self.messages_label.SetLabel(label)
        self.messages_list.SetName(label)
        # Writing may be allowed here where it is not in the chat itself, and the other way round.
        self.enable_chat(True)
        if after_sending:
            # Still writing: the place and the count were said when the thread was opened.
            self.set_status(STATUS_READY_KEY)
            self.message_input.SetFocus()
        else:
            self.announce(self.i18n.get_string(MSG_THREAD_OPENED_FORMAT_KEY).format(
                title=thread["title"], count=len(messages)
            ), FEEDBACK_NAVIGATION)

    def on_translate_menu(self, event):
        message = self.actionable_message()
        if message is None or self.is_busy:
            return
        if not message["text"]:
            self.notify(MSG_NOTHING_TO_TRANSLATE_KEY)
            return
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.translate(
            self.peer(self.current_dialog_id), message["id"], self.on_ui_thread(self.show_translation)
        )

    def show_translation(self, text):
        self.set_status(STATUS_READY_KEY)
        self.show_text(TRANSLATION_TITLE_KEY, text)

    def on_stories_menu(self, event):
        if self.is_busy:
            return
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.load_stories(self.on_ui_thread(self.choose_story))

    def choose_story(self, groups):
        self.set_status(STATUS_READY_KEY)
        if not groups:
            self.notify(MSG_NO_STORIES_KEY)
            return
        title = self.i18n.get_string(APP_TITLE_KEY)
        with wx.SingleChoiceDialog(self, self.i18n.get_string(MSG_CHOOSE_STORY_PERSON_KEY), title, [
            self.i18n.get_string(STORY_PERSON_FORMAT_KEY).format(name=group["name"], count=len(group["stories"]))
            for group in groups
        ]) as person_dialog:
            if person_dialog.ShowModal() != wx.ID_OK:
                return
            group = groups[person_dialog.GetSelection()]
        with wx.SingleChoiceDialog(self, self.i18n.get_string(MSG_CHOOSE_STORY_KEY), title, [
            self.i18n.get_string(STORY_FORMAT_KEY).format(
                media=self.i18n.get_string(story["media"]), caption=story["caption"],
                time=story["date"].astimezone().strftime(DATE_TIME_FORMAT)
            ).strip()
            for story in group["stories"]
        ]) as story_dialog:
            if story_dialog.ShowModal() != wx.ID_OK:
                return
            story = group["stories"][story_dialog.GetSelection()]
        self.set_status(MSG_DOWNLOADING_KEY)
        cache_key = ("story", group["peer_id"], story["id"])
        # Comes down like any other file, holding nothing up.
        self.telegram_manager.open_story(
            group["peer_id"], story["id"], self.on_transfer_done(self.open_media, cache_key, story["media"])
        )

    def on_message_stats_menu(self, event):
        """Say the selected message's numbers at once, without going through its whole row."""
        message = self.actionable_message()
        if message is None:
            return
        stats = self.message_stats(message)
        if message["forwards"]:
            forwards = self.i18n.get_string(AUDIENCE_FORWARDS_FORMAT_KEY).format(count=message["forwards"])
            stats = STATS_SEPARATOR.join(filter(None, (stats, forwards)))
        if stats:
            # Asked for by name, so it is spoken whatever the setting for passing remarks says.
            self.SetStatusText(stats)
            speak(stats)
        else:
            self.notify(MSG_NO_MESSAGE_STATS_KEY)

    def on_audience_menu(self, event):
        message = self.actionable_message()
        if message is None or self.is_busy:
            return
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.load_audience(
            self.peer(self.current_dialog_id), message["id"], self.on_ui_thread(self.show_audience, message)
        )

    def show_audience(self, audience, message):
        self.set_status(STATUS_READY_KEY)
        lines = []
        # A channel post is counted, not signed for: how many saw it and passed it on.
        if message["views"] is not None:
            lines.append(self.i18n.get_string(AUDIENCE_VIEWS_FORMAT_KEY).format(count=message["views"]))
        if message["forwards"] is not None:
            lines.append(self.i18n.get_string(AUDIENCE_FORWARDS_FORMAT_KEY).format(count=message["forwards"]))
        if audience["readers"]:
            lines.append(self.i18n.get_string(AUDIENCE_READERS_FORMAT_KEY).format(names=self.i18n.get_string(FILE_LABEL_SEPARATOR_KEY).join(audience["readers"])))
        elif message["views"] is None:
            lines.append(self.i18n.get_string(
                AUDIENCE_READERS_UNKNOWN_KEY if audience["readers"] is None else AUDIENCE_NO_READERS_KEY
            ))
        lines.append("")
        if audience["reactions"]:
            lines.append(self.i18n.get_string(AUDIENCE_REACTIONS_KEY))
            lines.extend(
                self.i18n.get_string(AUDIENCE_REACTION_FORMAT_KEY).format(name=name, emoji=emoji)
                for name, emoji in audience["reactions"]
            )
        else:
            lines.append(self.i18n.get_string(AUDIENCE_NO_REACTIONS_KEY))
        self.show_text(AUDIENCE_TITLE_KEY, "\n".join(lines))

    def sender_name(self, message):
        if message["outgoing"]:
            return self.i18n.get_string(SENDER_YOU_KEY)
        return message["sender"]

    def is_channel_post(self, message):
        """Whether the message is the open channel speaking as itself, so its row need not name it."""
        chat = self.current_dialog()
        # Posted by its admins, this account among them, it is still the channel that speaks.
        return chat.get("category") == CATEGORY_BROADCASTS and message["sender_id"] is None             and (message["outgoing"] or message["sender"] in (chat.get("title"), ""))

    def poll_text(self, poll):
        options = []
        for option in poll["options"]:
            details = []
            if option["chosen"]:
                details.append(self.i18n.get_string(POLL_CHOSEN_KEY))
            if option.get("correct"):
                details.append(self.i18n.get_string(POLL_CORRECT_KEY))
            # Telegram hides the counts until this account has voted.
            if option["voters"] is not None:
                details.append(self.i18n.get_string(POLL_VOTERS_FORMAT_KEY).format(count=option["voters"]))
            if details:
                options.append(self.i18n.get_string(POLL_OPTION_FORMAT_KEY).format(
                    text=option["text"], details=self.i18n.get_string(FILE_LABEL_SEPARATOR_KEY).join(details)
                ))
            else:
                options.append(option["text"])
        text = self.i18n.get_string(QUIZ_FORMAT_KEY if poll.get("quiz") else POLL_FORMAT_KEY).format(
            closed=self.i18n.get_string(POLL_CLOSED_SUFFIX_KEY) if poll["closed"] else "",
            question=poll["question"], options=self.i18n.get_string(FILE_LABEL_SEPARATOR_KEY).join(options)
        )
        if poll.get("explanation"):
            text = self.i18n.get_string(POLL_EXPLANATION_FORMAT_KEY).format(text=text, explanation=poll["explanation"])
        return text

    def message_text(self, message):
        service = message.get("service")
        if service is not None:
            # Telegram's own news: said in words, after the name of whoever did it.
            key, fields = service
            fields = dict(fields)
            if "names" in fields:
                fields["names"] = self.i18n.get_string(SERVICE_NAMES_SEPARATOR_KEY).join(fields["names"])
            return self.i18n.get_string(key).format(**fields)
        if message["poll"]:
            return self.poll_text(message["poll"])
        text = message["text"] or message["detail"]
        if message["media"]:
            text = self.i18n.get_string(MEDIA_FORMAT_KEY).format(media=self.media_label(message), text=text).strip()
        return text or self.i18n.get_string(MSG_NO_TEXT_KEY)

    def media_label(self, message):
        """Names the attachment as closely as is known: what kind of file, what it is called, how big, how long."""
        kind = self.i18n.get_string(message["media"])
        attached = message["file"]
        if attached is None:
            return kind
        if message["media"] == MEDIA_FILE:
            # "File" says nothing; its name usually says what it really is.
            kind = file_kind(self.i18n, attached["name"]) or kind
        parts = [kind]
        if attached["name"]:
            parts.append(attached["name"])
        if attached["duration"]:
            parts.append(duration_text(attached["duration"]))
        # A photo's size in bytes is of no use to anyone; a file's tells how long it takes to fetch.
        if attached["size"] and (attached["name"] or attached["duration"]):
            parts.append(file_size(self.i18n, attached["size"]))
        return self.i18n.get_string(FILE_LABEL_SEPARATOR_KEY).join(parts)

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
            time=self.time_text(message["date"], True)
        )
        # The list squeezes a message into one row; here it keeps its own line breaks.
        self.show_text(READ_MESSAGE_TITLE_KEY, header + "\n\n" + self.message_text(message))

    def time_text(self, date, with_day):
        """A moment written the way the settings ask; `with_day` says which day, not only what time."""
        local = date.astimezone()
        style = self.settings.get(SETTING_TIME_STYLE)
        # Where the row leaves the time out, the places that still tell it use plain numbers.
        if style in (TIME_STYLE_NUMBERS, TIME_STYLE_NONE):
            return local.strftime(DATE_TIME_FORMAT if with_day else TIME_FORMAT)
        text = self.i18n.get_string
        if style == TIME_STYLE_WORDS_12:
            clock = TIME_12_FORMAT.format(
                hour=local.hour % 12 or 12, minute="%02d" % local.minute,
                half=text(TIME_AM_KEY if local.hour < 12 else TIME_PM_KEY)
            )
        else:
            clock = local.strftime(TIME_FORMAT)
        if not with_day:
            return clock
        # The year only when it is not this one: said every time, it is just noise.
        this_year = local.year == datetime.date.today().year
        day = text(DATE_WORDS_FORMAT_KEY if this_year else DATE_WORDS_YEAR_FORMAT_KEY).format(
            day=local.day, month=text(MONTH_KEY_PREFIX + str(local.month)), year=local.year
        )
        return text(DATE_TIME_WORDS_FORMAT_KEY).format(date=day, time=clock)

    def message_stats(self, message):
        """A message's numbers in words: how many saw it, commented on it, reacted to it; empty if it has none."""
        stats = []
        if message["views"] is not None:
            stats.append(self.i18n.get_string(VIEWS_FORMAT_KEY).format(count=message["views"]))
        if message["comments"] is not None:
            stats.append(self.i18n.get_string(COMMENTS_FORMAT_KEY).format(count=message["comments"]))
        if message["reactions"]:
            stats.append(self.i18n.get_string(REACTIONS_FORMAT_KEY).format(reactions=self.i18n.get_string(FILE_LABEL_SEPARATOR_KEY).join(
                self.i18n.get_string(REACTION_COUNT_FORMAT_KEY).format(emoji=emoji, count=count)
                for emoji, count in message["reactions"]
            )))
        return STATS_SEPARATOR.join(stats)

    def format_message(self, message):
        local_date = message["date"].astimezone()
        is_today = local_date.date() == datetime.date.today()
        text = self.message_text(message)
        # Who it answers, if that message is among the loaded ones; not what it said, which the
        # user has heard already, and which "go to the replied message" reads in full.
        replied = next((m for m in self.messages if m["id"] == message["reply_to"]), None)
        if replied is not None:
            text = self.i18n.get_string(REPLY_PREFIX_FORMAT_KEY).format(sender=self.sender_name(replied), text=text)
        if message["forwarded_from"] is not None:
            forward_key = FORWARDED_FORMAT_KEY if message["forwarded_from"] else FORWARDED_UNKNOWN_FORMAT_KEY
            text = self.i18n.get_string(forward_key).format(name=message["forwarded_from"], text=text)
        if message["edited"]:
            text = self.i18n.get_string(EDITED_FORMAT_KEY).format(text=text)
        if message["buttons"]:
            text = self.i18n.get_string(BUTTONS_FORMAT_KEY).format(text=text, buttons=self.i18n.get_string(FILE_LABEL_SEPARATOR_KEY).join(message["buttons"]))
        stats = self.message_stats(message)
        stats_first = self.settings.get(SETTING_MESSAGE_STATS) == MESSAGE_STATS_BEFORE
        if stats and not stats_first:
            text = STATS_AFTER_FORMAT.format(text=text, stats=stats)
        if message["pinned"]:
            text = self.i18n.get_string(PINNED_FORMAT_KEY).format(text=text)
        no_time = self.settings.get(SETTING_TIME_STYLE) == TIME_STYLE_NONE
        if self.is_channel_post(message):
            row_format = MESSAGE_NO_SENDER_NO_TIME_FORMAT if no_time else self.i18n.get_string(MESSAGE_NO_SENDER_FORMAT_KEY)
        else:
            row_format = MESSAGE_NO_TIME_FORMAT if no_time else self.i18n.get_string(MESSAGE_FORMAT_KEY)
        line = row_format.format(
            sender=self.sender_name(message),
            # A row is one line: the list would drop the line breaks and glue the
            # words on either side together, so turn them into spaces first.
            text=" ".join(text.split()),
            time=self.time_text(message["date"], not is_today)
        )
        if message["read"] is not None:
            # Last on the row, where Telegram's own apps put their check marks.
            read_key = MESSAGE_READ_FORMAT_KEY if message["read"] else MESSAGE_UNREAD_FORMAT_KEY
            line = self.i18n.get_string(read_key).format(text=line)
        if stats and stats_first:
            # Ahead of the sender's name too: heard before the message itself begins.
            line = STATS_BEFORE_FORMAT.format(stats=stats, text=line)
        if message["id"] == self.first_unread_id:
            # Where reading stopped last time.
            line = self.i18n.get_string(NEW_FROM_HERE_FORMAT_KEY).format(text=line)
        if message["id"] in self.marked:
            # First thing on the row, so it is heard before anything else.
            line = self.i18n.get_string(MARKED_FORMAT_KEY).format(text=line)
        return line
