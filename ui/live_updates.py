from core import sounds
from core.speech import speak
from core.settings import SETTING_PLAY_SOUND, SETTING_ANNOUNCE_MESSAGES, SETTING_MARK_READ_ON_OPEN
from core.constants import (
    EVENT_NEW_MESSAGE, EVENT_MESSAGE_EDITED, EVENT_MESSAGES_DELETED, ANNOUNCE_FORMAT_KEY,
    SOUND_MESSAGE, SOUND_MESSAGE_IN_CHAT
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
        }
        handlers[event](*details)

    def on_new_message(self, chat, message):
        dialog_id = chat["id"]
        index = self.find_dialog_index(dialog_id)
        # Prefer the chat as already loaded: it knows its unread count and mute state.
        dialog = self.find_known_dialog(dialog_id) or chat

        is_current = dialog_id == self.current_dialog_id
        # Hidden in the background, the window shows nothing to anyone.
        is_on_screen = self.IsShown() and not self.IsIconized()
        if not message["outgoing"] and not dialog["muted"]:
            if self.settings.get(SETTING_PLAY_SOUND):
                # A quiet tick for the chat being read, the full chime for anything else.
                is_being_read = is_current and is_on_screen and self.IsActive()
                sounds.play(SOUND_MESSAGE_IN_CHAT if is_being_read else SOUND_MESSAGE)
            if self.settings.get(SETTING_ANNOUNCE_MESSAGES):
                # In the open chat the sender is what matters; elsewhere, which chat it came from.
                speak(self.i18n.get_string(ANNOUNCE_FORMAT_KEY).format(
                    source=message["sender"] if is_current else dialog["title"],
                    text=self.message_snippet(message)
                ))

        reads_it = is_current and is_on_screen and self.settings.get(SETTING_MARK_READ_ON_OPEN)
        if is_current:
            self.append_message(message)
        if not message["outgoing"]:
            if reads_it:
                self.telegram_manager.mark_read(dialog_id)
            else:
                dialog["unread"] += 1
        self.move_dialog_to_top(index, dialog)

    def on_brought_forward(self):
        """The window is visible again: what arrived in the open chat meanwhile is now being read."""
        dialog = self.find_known_dialog(self.current_dialog_id)
        if dialog and dialog["unread"] and self.settings.get(SETTING_MARK_READ_ON_OPEN):
            self.telegram_manager.mark_read(dialog["id"])
            self.set_unread(dialog["id"], 0)

    def on_message_edited(self, dialog_id, message):
        if dialog_id != self.current_dialog_id:
            return
        for index, shown in enumerate(self.messages):
            if shown["id"] == message["id"]:
                self.messages[index] = message
                # Re-render: replies quoting this message show its text too.
                self.render_messages(self.messages_list.GetSelection() - self.message_offset())
                return

    def on_messages_deleted(self, dialog_id, message_ids):
        if dialog_id is None:
            # Telegram does not say which chat. Outside channels message ids are
            # unique across chats, so matching by id is safe there, but only there.
            if self.current_dialog_id is None or self.current_dialog()["is_channel"]:
                return
        elif dialog_id != self.current_dialog_id:
            return
        for message_id in message_ids:
            self.remove_message(message_id)
