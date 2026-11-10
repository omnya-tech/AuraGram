"""A chat's row in the list says the newest message, the ones this program sent too, as Telegram's apps do:
Telegram sends no news of what a program sent itself, so the row asks once something has gone."""
import wx

import core.constants as c
from tests.harness import FakeChooser, FakeTelegramClient, WindowTestCase, make_message, make_user, pump

ALI = make_user(1, "Ali")
MONA = make_user(2, "Mona")


class RowAfterSendingTest(WindowTestCase):
    chats = [(ALI, 0, False), (MONA, 0, False)]
    history = {1: [make_message(1, "old news", sender=ALI)], 2: [make_message(1, "hello", sender=MONA)]}

    def row(self, dialog_id):
        return self.frame.dialogs_list.GetString(self.frame.find_dialog_index(dialog_id))

    def test_what_was_sent_in_the_chat_shows_on_its_row_back_in_the_list(self):
        self.open_chat(0)
        self.frame.message_input.SetValue("on my way")
        self.frame.on_send_message(None)
        self.assertTrue(pump(lambda: "on my way" in self.row(1)))
        self.assertNotIn("old news", self.row(1))

    def test_a_chat_forwarded_to_goes_up_with_what_went_there(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(self.frame.message_offset())
        FakeChooser.picked = [1]
        self.frame.on_forward_menu(None)
        self.assertTrue(pump(lambda: self.calls("forward")))
        # What the fake keeps of a forward: the copy, newest in Mona's chat.
        FakeTelegramClient.history[2].append(make_message(2, "old news", outgoing=True))
        self.frame.lift_dialog(2)
        self.assertTrue(pump(lambda: "old news" in self.row(2)))
        self.assertEqual(self.frame.all_dialogs[0]["id"], 2)

    def test_newer_news_that_came_meanwhile_is_not_taken_back(self):
        dialog = self.frame.find_known_dialog(1)
        dialog["last_message"] = dict(dialog["last_message"], id=50, text="newest")
        self.frame.on_last_message(1, dict(dialog["last_message"], id=2, text="older"))
        self.assertEqual(dialog["last_message"]["text"], "newest")
