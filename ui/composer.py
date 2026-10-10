import datetime
import wx
from core.speech import speak
from core.schedule import parse_send_time
from core.constants import (
    MSG_POLL_QUESTION_PROMPT_KEY, MSG_POLL_OPTIONS_PROMPT_KEY, MSG_POLL_SENT_KEY,
    ERR_POLL_OPTIONS_KEY, POLL_MIN_OPTIONS, POLL_MAX_OPTIONS, MSG_SCHEDULE_PROMPT_KEY,
    MSG_SCHEDULED_FORMAT_KEY, MSG_NOTHING_TO_SCHEDULE_KEY, ERR_BAD_TIME_KEY, REPLY_LABEL_FORMAT_KEY,
    EDIT_LABEL_KEY, MSG_CANNOT_EDIT_KEY, MSG_CHOOSE_FILE_KEY, MSG_UPLOADING_KEY, MSG_FILE_SENT_KEY,
    APP_TITLE_KEY, MESSAGE_INPUT_LABEL_KEY, MSG_LOADING_KEY, DATE_TIME_FORMAT
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

    def on_send_message(self, event):
        text = self.message_input.GetValue().strip()
        if not text or self.current_dialog_id is None:
            return
        self.enable_chat(False)
        self.set_status(MSG_LOADING_KEY)
        dialog_id = self.current_dialog_id
        on_result = self.on_ui_thread(self.on_message_sent, dialog_id)
        if self.editing is not None:
            self.telegram_manager.edit_message(dialog_id, self.editing["id"], text, on_result)
        else:
            self.telegram_manager.send_message(
                dialog_id, text, on_result,
                reply_to=self.reply_to["id"] if self.reply_to else None
            )

    def on_message_sent(self, result, dialog_id):
        if dialog_id != self.current_dialog_id:
            return
        self.set_compose()
        # Re-enable before focusing: a disabled field cannot take focus.
        self.enable_chat(True)
        self.message_input.Clear()
        self.load_messages()
        self.message_input.SetFocus()

    def on_send_file_menu(self, event):
        if self.current_dialog_id is None or self.is_busy:
            return
        with wx.FileDialog(
            self, self.i18n.get_string(MSG_CHOOSE_FILE_KEY),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_OK:
                return
            path = file_dialog.GetPath()
        self.is_busy = True
        self.set_status(MSG_UPLOADING_KEY)
        dialog_id = self.current_dialog_id
        self.telegram_manager.send_file(
            dialog_id, path, self.on_ui_thread(self.on_file_sent, dialog_id)
        )

    def on_file_sent(self, result, dialog_id, message_key=MSG_FILE_SENT_KEY):
        self.is_busy = False
        self.notify(message_key)
        if dialog_id == self.current_dialog_id:
            self.load_messages()

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
            dialog_id, text, self.on_ui_thread(self.on_message_scheduled, dialog_id, when),
            reply_to=self.reply_to["id"] if self.reply_to else None, schedule=when.astimezone()
        )

    def on_message_scheduled(self, result, dialog_id, when):
        if dialog_id == self.current_dialog_id:
            self.set_compose()
            self.message_input.Clear()
        self.announce(self.i18n.get_string(MSG_SCHEDULED_FORMAT_KEY).format(
            time=when.strftime(DATE_TIME_FORMAT)
        ))

    def on_new_poll_menu(self, event):
        if self.current_dialog_id is None:
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
            dialog_id, question, options, self.on_ui_thread(self.on_file_sent, dialog_id, MSG_POLL_SENT_KEY)
        )
