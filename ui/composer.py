import datetime
import os
import tempfile
import wx
from core import sounds
from core.speech import speak
from core.settings import SETTING_SENT_SOUND
from core.schedule import parse_send_time
from ui.layout import file_kind, file_size
from core.constants import (
    SOUND_SENT,
    MSG_POLL_QUESTION_PROMPT_KEY, MSG_POLL_OPTIONS_PROMPT_KEY, MSG_POLL_SENT_KEY,
    ERR_POLL_OPTIONS_KEY, POLL_MIN_OPTIONS, POLL_MAX_OPTIONS, MSG_SCHEDULE_PROMPT_KEY,
    MSG_SCHEDULED_FORMAT_KEY, MSG_NOTHING_TO_SCHEDULE_KEY, ERR_BAD_TIME_KEY, REPLY_LABEL_FORMAT_KEY,
    EDIT_LABEL_KEY, MSG_CANNOT_EDIT_KEY, MSG_CHOOSE_FILE_KEY, MSG_UPLOADING_KEY, MSG_FILE_SENT_KEY,
    APP_TITLE_KEY, MESSAGE_INPUT_LABEL_KEY, MSG_LOADING_KEY, DATE_TIME_FORMAT, STATUS_READY_KEY,
    PHOTO_VIDEO_EXTENSIONS, PASTED_IMAGE_NAME, MSG_CAPTION_PROMPT_KEY, MSG_SEND_AS_PROMPT_KEY,
    SEND_AS_MEDIA_KEY, SEND_AS_FILES_KEY, MSG_FILES_SENT_FORMAT_KEY, STICKERS_RECENT_KEY,
    MSG_CHOOSE_STICKER_SET_KEY, MSG_CHOOSE_STICKER_KEY, STICKER_CHOICE_FORMAT_KEY, MSG_NO_STICKERS_KEY,
    MSG_STICKER_SENT_KEY, MSG_CHOOSE_CONTACT_TO_SEND_KEY, MSG_CONTACT_SENT_KEY, MSG_NO_CONTACTS_KEY,
    MSG_LOCATION_PROMPT_KEY, ERR_BAD_LOCATION_KEY, MSG_LOCATION_SENT_KEY, MSG_CHOOSE_MEMBER_KEY,
    MSG_MENTION_GROUPS_ONLY_KEY, MENTION_USERNAME_FORMAT, MENTION_LINK_FORMAT, CATEGORY_GROUPS,
    MSG_UPLOAD_PROGRESS_FORMAT_KEY, MSG_STORY_CAPTION_PROMPT_KEY, MSG_STORY_AUDIENCE_KEY, STORY_AUDIENCES,
    MSG_STORY_POSTED_KEY, MSG_SENDING_FILES_FORMAT_KEY, FILE_LABEL_SEPARATOR_KEY, MSG_CHOOSE_PHOTO_KEY, PHOTO_FILES_KEY, PHOTO_FILE_PATTERNS, MSG_CHOOSE_SEND_AS_KEY, MSG_SEND_AS_SAVED_FORMAT_KEY, MSG_NO_SEND_AS_KEY
)

class ComposerMixin:
    """Writing and sending: plain messages, replies, edits, files, polls and scheduling.

    Mixed into MainFrame, which owns the widgets and the shared state.
    """

    def on_reply_menu(self, event):
        message = self.actionable_message()
        if message is not None:
            self.set_compose(reply_to=message)

    def on_edit_menu(self, event):
        message = self.actionable_message()
        if message is None:
            return
        if not message["outgoing"] or not message["text"]:
            self.notify(MSG_CANNOT_EDIT_KEY)
            return
        self.set_compose(editing=message)

    def set_compose(self, reply_to=None, editing=None):
        """Choose what the message field does next: reply, edit, or (no arguments) a normal message."""
        was_editing = self.editing is not None
        self.reply_to = reply_to
        self.editing = editing
        if reply_to is not None:
            label = self.i18n.get_string(REPLY_LABEL_FORMAT_KEY).format(
                sender=self.sender_name(reply_to), text=self.message_snippet(reply_to)
            )
        elif editing is not None:
            label = self.i18n.get_string(EDIT_LABEL_KEY)
        else:
            label = self.i18n.get_string(MESSAGE_INPUT_LABEL_KEY)
        # The field's label is what the screen reader reads when it gets focus.
        self.input_label.SetLabel(label)
        self.message_input.SetName(label)
        self.panel.Layout()

        if editing is not None:
            self.message_input.SetValue(editing["text"])
            self.message_input.SetInsertionPointEnd()
        elif was_editing:
            # Leaving edit mode: the field still holds the old message's text.
            self.message_input.Clear()
        if reply_to is not None or editing is not None:
            self.message_input.SetFocus()
            speak(label)

    def on_input_changed(self, event):
        event.Skip()
        # Only for what the user types: restoring a draft or an edit also changes the field.
        if self.message_input.HasFocus():
            self.tell_typing()

    def tell_typing(self):
        # Nothing to tell when the field was just emptied, or while a message is being edited.
        if self.current_dialog_id is not None and self.message_input.GetValue() and not self.editing:
            self.telegram_manager.send_typing(self.peer(self.current_dialog_id))

    def on_send_message(self, event, silent=False):
        text = self.message_input.GetValue().strip()
        if not text or self.current_dialog_id is None:
            return
        self.enable_chat(False)
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        on_result = self.on_ui_thread(self.on_message_sent, dialog_id, self.editing is None)
        if self.editing is not None:
            self.telegram_manager.edit_message(self.peer(dialog_id), self.editing["id"], text, on_result)
        else:
            self.telegram_manager.send_message(
                self.peer(dialog_id), text, on_result,
                reply_to=self.reply_to["id"] if self.reply_to else self.thread_root(), silent=silent
            )

    def on_message_sent(self, result, dialog_id, is_new=True):
        # It was sent, so it is no longer a draft, even if another chat is open by now.
        self.drafts.pop(dialog_id, None)
        # An edit changes an old message; only something new makes the chat the latest one.
        if is_new:
            self.lift_dialog(dialog_id)
        if self.settings.get(SETTING_SENT_SOUND):
            sounds.play(SOUND_SENT)
        if dialog_id != self.current_dialog_id:
            return
        self.set_compose()
        # Re-enable before focusing: a disabled field cannot take focus.
        self.enable_chat(True)
        self.message_input.Clear()
        if self.thread is not None:
            self.open_thread(self.thread, after_sending=True)
        else:
            self.load_messages()
        self.message_input.SetFocus()

    def can_send_now(self):
        """Whether there is an open chat this account may write in, with nothing else under way."""
        return (
            self.current_dialog_id is not None and not self.is_busy
            and (self.current_dialog().get("can_send", True) or self.in_comments())
        )

    def on_send_file_menu(self, event):
        if not self.can_send_now():
            return
        with wx.FileDialog(
            self, self.i18n.get_string(MSG_CHOOSE_FILE_KEY),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_OK:
                return
            paths = file_dialog.GetPaths()
        self.send_paths(paths)

    def send_paths(self, paths):
        """Send files as one message, after asking what goes with them; cancelling either question sends nothing."""
        # Said before anything is sent: what each file is and how big, so a wrong pick is caught here.
        with wx.TextEntryDialog(
            self, self.describe_paths(paths) + "\n\n" + self.i18n.get_string(MSG_CAPTION_PROMPT_KEY),
            self.i18n.get_string(APP_TITLE_KEY)
        ) as caption_dialog:
            if caption_dialog.ShowModal() != wx.ID_OK:
                return
            caption = caption_dialog.GetValue().strip()
        as_documents = False
        if any(os.path.splitext(path)[1].lower() in PHOTO_VIDEO_EXTENSIONS for path in paths):
            with wx.SingleChoiceDialog(
                self, self.i18n.get_string(MSG_SEND_AS_PROMPT_KEY), self.i18n.get_string(APP_TITLE_KEY),
                [self.i18n.get_string(SEND_AS_MEDIA_KEY), self.i18n.get_string(SEND_AS_FILES_KEY)]
            ) as kind_dialog:
                if kind_dialog.ShowModal() != wx.ID_OK:
                    return
                as_documents = kind_dialog.GetSelection() == 1
        self.is_busy = True
        self.set_status(MSG_UPLOADING_KEY)
        dialog_id = self.current_dialog_id
        self.telegram_manager.send_files(
            self.peer(dialog_id), paths, caption, as_documents,
            self.on_ui_thread(self.on_files_sent, dialog_id, len(paths)), reply_to=self.take_reply(),
            on_progress=self.progress_reporter(MSG_UPLOAD_PROGRESS_FORMAT_KEY)
        )

    def describe_paths(self, paths):
        """One line per file about to be sent: its name, what it is, its size."""
        separator = self.i18n.get_string(FILE_LABEL_SEPARATOR_KEY)
        lines = []
        for path in paths:
            name = os.path.basename(path)
            parts = [name, file_kind(self.i18n, name)]
            if os.path.isfile(path):
                parts.append(file_size(self.i18n, os.path.getsize(path)))
            lines.append(separator.join(part for part in parts if part))
        return self.i18n.get_string(MSG_SENDING_FILES_FORMAT_KEY).format(files="\n".join(lines))

    def take_reply(self):
        """Id of the message being replied to, if any; the reply is used up by whatever is sent with it."""
        reply_to = self.reply_to["id"] if self.reply_to else None
        if reply_to is not None:
            self.set_compose()
        return reply_to or self.thread_root()

    def on_files_sent(self, result, dialog_id, count):
        if count == 1:
            self.on_file_sent(result, dialog_id)
        else:
            self.is_busy = False
            self.hide_progress()
            self.announce(self.i18n.get_string(MSG_FILES_SENT_FORMAT_KEY).format(count=count))
            self.refresh_after_sending(dialog_id)

    def refresh_after_sending(self, dialog_id):
        self.lift_dialog(dialog_id)
        if dialog_id != self.current_dialog_id:
            return
        if self.thread is not None:
            self.open_thread(self.thread, after_sending=True)
        else:
            self.load_messages()

    def paste_files(self):
        """Send what the clipboard holds if it is files or a picture; False if it is anything else (text is pasted as usual)."""
        if not self.can_send_now() or not wx.TheClipboard.Open():
            return False
        try:
            paths = []
            if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_FILENAME)):
                files = wx.FileDataObject()
                if wx.TheClipboard.GetData(files):
                    paths = list(files.GetFilenames())
            # A picture copied from a document often comes with its text too: then the text is what is wanted.
            elif wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_BITMAP)) and \
                    not wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_UNICODETEXT)):
                picture = wx.BitmapDataObject()
                if wx.TheClipboard.GetData(picture):
                    path = os.path.join(tempfile.mkdtemp(), PASTED_IMAGE_NAME)
                    if picture.GetBitmap().SaveFile(path, wx.BITMAP_TYPE_PNG):
                        paths = [path]
        finally:
            wx.TheClipboard.Close()
        if not paths:
            return False
        self.send_paths(paths)
        return True

    def on_send_sticker_menu(self, event):
        if self.can_send_now():
            self.set_status(MSG_LOADING_KEY)
            self.telegram_manager.load_sticker_sets(self.on_ui_thread(self.choose_sticker_set))

    def choose_sticker_set(self, sticker_sets):
        self.set_status(STATUS_READY_KEY)
        titles = [self.i18n.get_string(STICKERS_RECENT_KEY)] + [sticker_set["title"] for sticker_set in sticker_sets]
        with wx.SingleChoiceDialog(
            self, self.i18n.get_string(MSG_CHOOSE_STICKER_SET_KEY), self.i18n.get_string(APP_TITLE_KEY), titles
        ) as set_dialog:
            if set_dialog.ShowModal() != wx.ID_OK:
                return
            index = set_dialog.GetSelection()
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.load_stickers(
            sticker_sets[index - 1]["id"] if index else None, self.on_ui_thread(self.choose_sticker)
        )

    def choose_sticker(self, emojis):
        self.set_status(STATUS_READY_KEY)
        if not emojis:
            self.notify(MSG_NO_STICKERS_KEY)
            return
        # Numbered: several stickers of a set often stand for the same emoji.
        choices = [
            self.i18n.get_string(STICKER_CHOICE_FORMAT_KEY).format(number=number, emoji=emoji)
            for number, emoji in enumerate(emojis, 1)
        ]
        with wx.SingleChoiceDialog(
            self, self.i18n.get_string(MSG_CHOOSE_STICKER_KEY), self.i18n.get_string(APP_TITLE_KEY), choices
        ) as sticker_dialog:
            if sticker_dialog.ShowModal() != wx.ID_OK:
                return
            index = sticker_dialog.GetSelection()
        dialog_id = self.current_dialog_id
        self.telegram_manager.send_sticker(
            self.peer(dialog_id), index, self.on_ui_thread(self.on_file_sent, dialog_id, MSG_STICKER_SENT_KEY),
            reply_to=self.take_reply()
        )

    def on_send_contact_menu(self, event):
        if self.can_send_now():
            self.set_status(MSG_LOADING_KEY)
            self.telegram_manager.load_contacts(self.on_ui_thread(self.choose_contact_to_send))

    def choose_contact_to_send(self, contacts):
        self.set_status(STATUS_READY_KEY)
        if not contacts:
            self.notify(MSG_NO_CONTACTS_KEY)
            return
        contact = self.choose_chat(MSG_CHOOSE_CONTACT_TO_SEND_KEY, contacts)
        if contact is not None:
            dialog_id = self.current_dialog_id
            self.telegram_manager.send_contact(
                self.peer(dialog_id), contact["id"],
                self.on_ui_thread(self.on_file_sent, dialog_id, MSG_CONTACT_SENT_KEY), reply_to=self.take_reply()
            )

    def on_send_location_menu(self, event):
        if not self.can_send_now():
            return
        text = self.ask_text(MSG_LOCATION_PROMPT_KEY)
        if not text:
            return
        try:
            latitude, longitude = (float(part) for part in text.replace("،", ",").split(","))
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError(text)
        except ValueError:
            self.show_error(ERR_BAD_LOCATION_KEY)
            return
        dialog_id = self.current_dialog_id
        self.telegram_manager.send_location(
            self.peer(dialog_id), latitude, longitude,
            self.on_ui_thread(self.on_file_sent, dialog_id, MSG_LOCATION_SENT_KEY), reply_to=self.take_reply()
        )

    def on_post_story_menu(self, event):
        if self.is_busy:
            return
        with wx.FileDialog(
            self, self.i18n.get_string(MSG_CHOOSE_PHOTO_KEY),
            wildcard="%s (%s)|%s" % (self.i18n.get_string(PHOTO_FILES_KEY), PHOTO_FILE_PATTERNS, PHOTO_FILE_PATTERNS),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_OK:
                return
            path = file_dialog.GetPath()
        self.post_story(path)

    def post_story(self, path):
        caption = self.ask_text(MSG_STORY_CAPTION_PROMPT_KEY)
        if caption is None:
            return
        with wx.SingleChoiceDialog(
            self, self.i18n.get_string(MSG_STORY_AUDIENCE_KEY), self.i18n.get_string(APP_TITLE_KEY),
            [self.i18n.get_string(audience) for audience in STORY_AUDIENCES]
        ) as audience_dialog:
            if audience_dialog.ShowModal() != wx.ID_OK:
                return
            audience = STORY_AUDIENCES[audience_dialog.GetSelection()]
        self.is_busy = True
        self.set_status(MSG_UPLOADING_KEY)
        self.telegram_manager.post_story(
            path, caption, audience, self.on_ui_thread(self.on_story_posted),
            on_progress=self.progress_reporter(MSG_UPLOAD_PROGRESS_FORMAT_KEY)
        )

    def on_story_posted(self, result):
        self.is_busy = False
        self.hide_progress()
        self.notify(MSG_STORY_POSTED_KEY)

    def on_send_as_menu(self, event):
        if self.current_dialog_id is None or self.is_busy:
            return
        dialog_id = self.current_dialog_id
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.load_send_as(dialog_id, self.on_ui_thread(self.choose_send_as, dialog_id))

    def choose_send_as(self, senders, dialog_id):
        self.set_status(STATUS_READY_KEY)
        # One name on offer is no choice: it is this account itself.
        if len(senders) < 2:
            self.notify(MSG_NO_SEND_AS_KEY)
            return
        sender = self.choose_chat(MSG_CHOOSE_SEND_AS_KEY, senders)
        if sender is not None:
            self.telegram_manager.set_send_as(dialog_id, sender["id"], self.on_ui_thread(
                lambda result: self.announce(self.i18n.get_string(MSG_SEND_AS_SAVED_FORMAT_KEY).format(name=sender["title"]))
            ))

    def on_mention_menu(self, event):
        if not self.can_send_now():
            return
        if self.current_dialog()["category"] != CATEGORY_GROUPS:
            self.notify(MSG_MENTION_GROUPS_ONLY_KEY)
            return
        self.set_status(MSG_LOADING_KEY)
        self.telegram_manager.load_members(self.current_dialog_id, "", self.on_ui_thread(self.choose_mention))

    def choose_mention(self, members):
        self.set_status(STATUS_READY_KEY)
        members = [member for member in members if not member["is_self"]]
        with wx.SingleChoiceDialog(
            self, self.i18n.get_string(MSG_CHOOSE_MEMBER_KEY), self.i18n.get_string(APP_TITLE_KEY),
            [member["name"] for member in members]
        ) as member_dialog:
            if member_dialog.ShowModal() != wx.ID_OK:
                return
            member = members[member_dialog.GetSelection()]
        # Someone without a username can only be pointed at through a link to their account.
        mention = MENTION_USERNAME_FORMAT if member["username"] else MENTION_LINK_FORMAT
        self.message_input.WriteText(mention.format(**member))
        self.message_input.SetFocus()

    def on_file_sent(self, result, dialog_id, message_key=MSG_FILE_SENT_KEY):
        self.is_busy = False
        self.hide_progress()
        self.notify(message_key)
        self.refresh_after_sending(dialog_id)

    def on_schedule_menu(self, event):
        text = self.message_input.GetValue().strip()
        if self.current_dialog_id is None:
            return
        if not text:
            self.notify(MSG_NOTHING_TO_SCHEDULE_KEY)
            return
        with wx.TextEntryDialog(
            self, self.i18n.get_string(MSG_SCHEDULE_PROMPT_KEY), self.i18n.get_string(APP_TITLE_KEY)
        ) as time_dialog:
            if time_dialog.ShowModal() != wx.ID_OK:
                return
            when = parse_send_time(time_dialog.GetValue(), datetime.datetime.now())
        if when is None:
            self.show_error(ERR_BAD_TIME_KEY)
            return
        dialog_id = self.current_dialog_id
        self.telegram_manager.send_message(
            self.peer(dialog_id), text, self.on_ui_thread(self.on_message_scheduled, dialog_id, when),
            reply_to=self.reply_to["id"] if self.reply_to else self.thread_root(), schedule=when.astimezone()
        )

    def on_message_scheduled(self, result, dialog_id, when):
        if dialog_id == self.current_dialog_id:
            self.set_compose()
            self.message_input.Clear()
        self.announce(self.i18n.get_string(MSG_SCHEDULED_FORMAT_KEY).format(
            time=when.strftime(DATE_TIME_FORMAT)
        ))

    def on_new_poll_menu(self, event):
        if not self.can_send_now():
            return
        title = self.i18n.get_string(APP_TITLE_KEY)
        with wx.TextEntryDialog(self, self.i18n.get_string(MSG_POLL_QUESTION_PROMPT_KEY), title) as question_dialog:
            if question_dialog.ShowModal() != wx.ID_OK:
                return
            question = question_dialog.GetValue().strip()
        if not question:
            return
        with wx.TextEntryDialog(
            self, self.i18n.get_string(MSG_POLL_OPTIONS_PROMPT_KEY), title, style=wx.TextEntryDialogStyle|wx.TE_MULTILINE
        ) as options_dialog:
            if options_dialog.ShowModal() != wx.ID_OK:
                return
            options = [line.strip() for line in options_dialog.GetValue().splitlines() if line.strip()]
        if not POLL_MIN_OPTIONS <= len(options) <= POLL_MAX_OPTIONS:
            self.show_error(ERR_POLL_OPTIONS_KEY)
            return
        dialog_id = self.current_dialog_id
        self.telegram_manager.send_poll(
            self.peer(dialog_id), question, options,
            self.on_ui_thread(self.on_file_sent, dialog_id, MSG_POLL_SENT_KEY), reply_to=self.take_reply()
        )
