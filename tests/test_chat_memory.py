"""Coming back to a chat shows it at once from memory, then what Telegram says; nothing goes to the disk."""
import asyncio
import os

import core.constants as c
from tests.harness import FakeTelegramClient, WindowTestCase, make_message, make_user, pump

ALI = make_user(1, "Ali")
MONA = make_user(2, "Mona")


class ChatMemoryTest(WindowTestCase):
    chats = [(ALI, 0, False), (MONA, 0, False)]
    history = {
        1: [make_message(1, "first", sender=ALI), make_message(2, "second", sender=ALI)],
        2: [make_message(5, "hi Mona", sender=MONA)],
    }

    def rows(self):
        return [self.frame.messages_list.GetString(i) for i in range(self.frame.messages_list.GetCount())]

    def reopen(self, index):
        """Open a chat while Telegram is held back, as on a slow connection."""
        self.frame.close_chat()
        gate = FakeTelegramClient.history_gate = asyncio.Event()
        self.frame.dialogs_list.SetSelection(index)
        self.frame.on_open_dialog(None)
        return gate

    def let_through(self, gate):
        self.manager.loop.call_soon_threadsafe(gate.set)
        self.assertTrue(pump(lambda: not self.frame.showing_remembered))
        FakeTelegramClient.history_gate = None

    def test_a_chat_opened_again_shows_at_once_then_what_is_new(self):
        self.open_chat(0)
        self.assertEqual(len(self.frame.messages), 2)
        # While away, a message arrives that only Telegram knows of yet.
        FakeTelegramClient.history[1].append(make_message(3, "third", sender=ALI))
        gate = self.reopen(0)
        pump(timeout=0.2)
        # At once, with nothing from Telegram yet: the chat as it was left.
        self.assertEqual([m["id"] for m in self.frame.messages], [1, 2])
        self.assertTrue(any("second" in row for row in self.rows()))
        self.assertTrue(self.frame.messages_list.IsEnabled())
        self.let_through(gate)
        self.assertEqual([m["id"] for m in self.frame.messages], [1, 2, 3])
        self.assertTrue(any("third" in row for row in self.rows()))

    def test_the_user_stays_on_the_message_they_are_on_when_the_new_ones_come(self):
        self.open_chat(0)
        FakeTelegramClient.history[1].append(make_message(3, "third", sender=ALI))
        gate = self.reopen(0)
        pump(timeout=0.2)
        self.frame.messages_list.SetSelection(self.frame.message_offset())
        self.let_through(gate)
        self.assertEqual(self.frame.selected_message()["id"], 1)

    def test_a_chat_that_changed_while_away_is_not_shown_from_memory(self):
        self.open_chat(0)
        self.frame.close_chat()
        # Something happened there meanwhile: what was remembered of it is out of date.
        self.frame.on_message_edited(1, dict(self.frame.chat_memory[1][0][0], text="changed"))
        self.assertNotIn(1, self.frame.chat_memory)
        gate = self.reopen(0)
        pump(timeout=0.2)
        self.assertEqual(self.frame.messages, [])
        self.manager.loop.call_soon_threadsafe(gate.set)
        self.assertTrue(pump(lambda: len(self.frame.messages) == 2))
        FakeTelegramClient.history_gate = None

    def test_a_chat_with_new_messages_waits_for_telegram(self):
        self.open_chat(0)
        self.open_chat(1)
        self.assertIn(1, self.frame.chat_memory)
        # A new message in the chat left behind: it is no longer the same chat as remembered.
        self.frame.on_new_message(self.frame.find_known_dialog(1), {
            **self.frame.chat_memory[1][0][-1], "id": 9, "text": "news", "outgoing": False})
        self.assertNotIn(1, self.frame.chat_memory)

    def test_memory_holds_a_limited_number_of_chats_and_nothing_on_the_disk(self):
        for dialog_id in range(100, 100 + c.REMEMBERED_CHATS + 5):
            self.frame.chat_memory[dialog_id] = ([{"id": 1}], False)
        self.open_chat(0)
        self.frame.close_chat()
        self.assertEqual(len(self.frame.chat_memory), c.REMEMBERED_CHATS)
        # The one just left is kept; the oldest went first.
        self.assertIn(1, self.frame.chat_memory)
        self.assertNotIn(100, self.frame.chat_memory)
        written = [name for name in os.listdir(c.DATA_DIR) if name.endswith((".db", ".sqlite", ".cache"))]
        self.assertEqual(written, [])
