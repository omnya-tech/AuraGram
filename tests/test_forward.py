"""Forwarding: offered only where this account may write, and one chat refusing does not stop the rest."""
import core.constants as c
import core.telegram_client as telegram_client
from tests.harness import FakeChooser, FakeTelegramClient, WindowTestCase, make_channel, make_message, make_user, pump

ALI = make_user(1, "Ali")
SARA = make_user(2, "Sara")
NEWS = make_channel(3, "News")
MY_GROUP = make_channel(4, "MyGroup", group=True, creator=True)
NEWS_ID = telegram_client.get_peer_id(NEWS)
GROUP_ID = telegram_client.get_peer_id(MY_GROUP)


class ForwardTest(WindowTestCase):
    chats = [(ALI, 0, False), (SARA, 0, False), (NEWS, 0, False), (MY_GROUP, 0, False)]
    history = {NEWS_ID: [make_message(7, "post")]}

    def setUp(self):
        super().setUp()
        self.open_chat([dialog["id"] for dialog in self.frame.dialogs].index(NEWS_ID))
        self.frame.messages_list.SetSelection(self.frame.message_offset())

    def pick(self, *titles):
        """Tick these chats in the picker, by the place they get in the list it is shown."""
        offered = [chat["title"] for chat in self.frame.all_dialogs if chat.get("can_send", True)]
        FakeChooser.picked = [offered.index(title) for title in titles]

    def test_a_channel_this_account_only_reads_is_not_offered(self):
        FakeChooser.confirmed = False
        self.frame.on_forward_menu(None)
        self.assertNotIn("News", FakeChooser.last_choices)
        self.assertIn("MyGroup", FakeChooser.last_choices)
        self.assertIn("Ali", FakeChooser.last_choices)

    def test_a_chat_that_refuses_is_named_with_its_kind_and_the_rest_still_get_it(self):
        FakeTelegramClient.refused_forwards = {GROUP_ID}
        self.pick("Ali", "MyGroup", "Sara")
        self.frame.on_forward_menu(None)
        self.assertTrue(pump(lambda: self.boxes))
        # The two that took it, in order, past the one that refused.
        self.assertEqual([call[1] for call in self.calls("forward")], [1, 2])
        row = self.text(c.FORWARD_FAILURE_ROW_FORMAT_KEY).format(
            title="MyGroup", kind=self.text(c.CHAT_KIND_GROUP), reason=self.text(c.ERR_NO_PERMISSION_KEY)
        )
        self.assertEqual(self.boxes, [self.text(c.MSG_FORWARD_PARTLY_FORMAT_KEY).format(count=2, failures=row)])

    def test_when_every_chat_refuses_it_says_so(self):
        FakeTelegramClient.refused_forwards = {1}
        self.pick("Ali")
        self.frame.on_forward_menu(None)
        self.assertTrue(pump(lambda: self.boxes))
        row = self.text(c.FORWARD_FAILURE_ROW_FORMAT_KEY).format(
            title="Ali", kind=self.text(c.CHAT_KIND_USER), reason=self.text(c.ERR_NO_PERMISSION_KEY)
        )
        self.assertEqual(self.boxes, [self.text(c.MSG_FORWARD_FAILED_FORMAT_KEY).format(failures=row)])
