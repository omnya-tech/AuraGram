import datetime
import wx
from core import reminders, sounds
from core.schedule import parse_send_time
from core.speech import speak
from core.constants import (
    REMIND_CHOICES, MSG_REMIND_WHEN_KEY, MSG_REMIND_TIME_PROMPT_KEY, ERR_BAD_TIME_KEY, MSG_REMINDER_SET_FORMAT_KEY,
    MSG_REMINDER_DUE_FORMAT_KEY, MSG_REMINDER_OPEN_KEY, REMINDER_ROW_FORMAT_KEY, MSG_NO_REMINDERS_KEY,
    MSG_REMINDERS_PROMPT_KEY, MSG_REMINDER_DELETE_FORMAT_KEY, MSG_REMINDER_DELETED_KEY, MSG_CHAT_GONE_KEY,
    REMINDER_CHECK_MS, SOUND_MESSAGE
)

class RemindersMixin:
    """Reminders of a message at a time the user picks. They are kept on this computer and
    looked at every few seconds; one that came due while the program was closed is given at the next start."""

    def init_reminders(self):
        self.reminders = reminders.load()
        # True while a reminder is being shown, so the next look does not stack a second one on it.
        self.reminding = False
        wx.CallAfter(self.reminder_tick)

    def reminder_tick(self):
        """Look at the reminders now and again in a while, for as long as the window is there. Not a
        wx.Timer: one owned by the window can fire into it while it is being destroyed."""
        if not self:
            return
        wx.CallLater(REMINDER_CHECK_MS, self.reminder_tick)
        self.check_reminders()

    def on_remind_menu(self, event):
        message = self.actionable_message()
        if message is None or self.current_dialog_id is None:
            return
        text = self.i18n.get_string
        index = self.pick(text(MSG_REMIND_WHEN_KEY), [text(key) for key, minutes in REMIND_CHOICES])
        if index is None:
            return
        now = datetime.datetime.now().astimezone()
        choice = REMIND_CHOICES[index][1]
        if choice == "time":
            typed = self.ask_text(MSG_REMIND_TIME_PROMPT_KEY)
            if typed is None:
                return
            due = parse_send_time(typed, now)
            if due is None:
                self.show_error(ERR_BAD_TIME_KEY)
                return
        else:
            due = reminders.when(choice, now)
        chat = self.current_dialog()
        self.reminders.append({
            "chat_id": self.current_dialog_id, "chat_title": chat.get("title", ""), "message_id": message["id"],
            "text": self.message_snippet(message), "due": due.isoformat(),
        })
        self.reminders.sort(key=reminders.due_of)
        reminders.save(self.reminders)
        self.announce(text(MSG_REMINDER_SET_FORMAT_KEY).format(time=self.time_text(due, True)))

    def check_reminders(self):
        """Give every reminder whose time has come, one after another."""
        if not self or self.reminding:
            return
        due, self.reminders = reminders.take_due(self.reminders, datetime.datetime.now().astimezone())
        if not due:
            return
        reminders.save(self.reminders)
        self.reminding = True
        try:
            for reminder in due:
                self.remind(reminder)
        finally:
            self.reminding = False

    def remind(self, reminder):
        text = self.i18n.get_string(MSG_REMINDER_DUE_FORMAT_KEY).format(
            chat=reminder["chat_title"], text=reminder["text"]
        )
        sounds.play(SOUND_MESSAGE)
        # Said whether or not the window is in sight: that is the point of a reminder.
        speak(text)
        self.bring_forward()
        if self.confirm(text + "\n\n" + self.i18n.get_string(MSG_REMINDER_OPEN_KEY)):
            self.open_reminded(reminder)

    def open_reminded(self, reminder):
        chat = self.find_known_dialog(reminder["chat_id"])
        if chat is None:
            self.notify(MSG_CHAT_GONE_KEY)
            return
        if chat["id"] == self.current_dialog_id:
            self.jump_to_message(reminder["message_id"])
            return
        # Gone to once the chat has loaded.
        self.pending_jump = reminder["message_id"]
        self.open_chat(chat)

    def reminder_row(self, reminder):
        return self.i18n.get_string(REMINDER_ROW_FORMAT_KEY).format(
            time=self.time_text(reminders.due_of(reminder), True), chat=reminder["chat_title"], text=reminder["text"]
        )

    def on_reminders_menu(self, event):
        """The reminders still to come; picking one offers to delete it."""
        if not self.reminders:
            self.notify(MSG_NO_REMINDERS_KEY)
            return
        rows = [self.reminder_row(reminder) for reminder in self.reminders]
        index = self.pick(self.i18n.get_string(MSG_REMINDERS_PROMPT_KEY), rows)
        if index is None:
            return
        if self.confirm(self.i18n.get_string(MSG_REMINDER_DELETE_FORMAT_KEY).format(reminder=rows[index])):
            del self.reminders[index]
            reminders.save(self.reminders)
            self.notify(MSG_REMINDER_DELETED_KEY)
