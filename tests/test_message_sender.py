"""From a message in a group to a private chat with whoever wrote it."""
import core.constants as c
import core.telegram_client as telegram_client
from tests.harness import WindowTestCase, make_channel, make_message, make_user, pump

ALI = make_user(1, "Ali")
# Met only in the group: no chat with her yet.
MONA = make_user(5, "Mona", contact=False)
GROUP = make_channel(20, "Team", group=True)
NEWS = make_channel(30, "News")
GROUP_ID = telegram_client.get_peer_id(GROUP)
NEWS_ID = telegram_client.get_peer_id(NEWS)


class MessageSenderTest(WindowTestCase):
    chats = [(GROUP, 0, False), (NEWS, 0, False), (ALI, 0, False)]
    history = {
        GROUP_ID: [make_message(1, "hello team", sender=MONA), make_message(2, "mine", outgoing=True)],
        NEWS_ID: [make_message(7, "headline")],
        1: [make_message(3, "hi", sender=ALI)],
    }

    def label(self, name):
        return self.text(c.CONTEXT_MESSAGE_SENDER_FORMAT_KEY).format(name=name)

    def menu(self, row):
        self.frame.messages_list.SetSelection(row)
        self.frame.on_message_context_menu(self.context_event(self.frame.messages_list))
        return list(self.menu_labels)

    def test_group_message_offers_its_writer_by_name_and_opens_their_chat(self):
        self.open_chat(0)
        self.assertIn(self.label("Mona"), self.menu(0))
        self.frame.on_message_sender_menu(None)
        self.assertTrue(pump(lambda: self.frame.current_dialog_id == 5 and self.frame.message_input.IsEnabled()))
        self.assertIn("Mona", self.frame.GetTitle())
        # A chat like any other from now on, there to come back to.
        self.assertEqual(self.frame.find_known_dialog(5)["title"], "Mona")

    def test_not_offered_on_own_messages_channel_posts_or_in_a_private_chat(self):
        self.open_chat(0)
        self.assertFalse([entry for entry in self.menu(1) if entry.startswith(self.label("")[:6])])
        self.frame.on_message_sender_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NO_SENDER_TO_MESSAGE_KEY))
        self.assertEqual(self.frame.current_dialog_id, GROUP_ID)

        self.frame.close_chat()
        self.open_chat(1)
        self.assertNotIn(self.label(""), self.menu(0))
        self.frame.on_message_sender_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NO_SENDER_TO_MESSAGE_KEY))

        self.frame.close_chat()
        self.open_chat(2)
        self.assertNotIn(self.label("Ali"), self.menu(0))
