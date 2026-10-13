"""The view that lists the account's contacts and says who is online, and chat rows that carry the whole last message."""
import asyncio
import datetime

from telethon.tl import types

import core.constants as c
from tests.harness import FakeTelegramClient, Record, WindowTestCase, make_message, make_user, pump

LONG = "word " * 60 + "the very end"

ALI = make_user(1, "Ali")
ALI.status = types.UserStatusOffline(was_online=datetime.datetime(2026, 1, 2, 3, 4, tzinfo=datetime.timezone.utc))
BASMA = make_user(2, "Basma")
BASMA.status = types.UserStatusOnline(expires=None)
# In the contact list, but never written to.
ZAKI = make_user(9, "Zaki")
STRANGER = make_user(5, "Stranger", contact=False)

CONTACTS_VIEW = 3


class ContactsViewTest(WindowTestCase):
    chats = [(ALI, 2, False), (STRANGER, 0, False)]
    history = {1: [make_message(1, "first line\nsecond line " + LONG, sender=ALI)]}

    def setUp(self):
        super().setUp()
        FakeTelegramClient.contacts = [ZAKI, BASMA, ALI]

    def show_contacts(self):
        self.frame.view_tabs.SetSelection(CONTACTS_VIEW)
        self.frame.on_view_changed(None)
        self.assertTrue(pump(lambda: len(self.frame.dialogs) == len(FakeTelegramClient.contacts)))

    def rows(self):
        return [self.frame.dialogs_list.GetString(index) for index in range(self.frame.dialogs_list.GetCount())]

    def fire(self, handler, event):
        asyncio.run_coroutine_threadsafe(self.manager.client.handlers[handler](event), self.manager.loop)

    def test_contacts_are_listed_with_who_is_online_first(self):
        self.show_contacts()
        online, offline = self.text(c.STATUS_ONLINE_KEY), self.text(c.STATUS_OFFLINE_KEY)
        rows = self.rows()
        self.assertEqual([dialog["title"] for dialog in self.frame.dialogs], ["Basma", "Ali", "Zaki"])
        self.assertEqual(rows[0], "Basma، " + online)
        self.assertIn(self.text(c.STATUS_LAST_SEEN_FORMAT_KEY).format(time="")[:8], rows[1])
        # Telegram says nothing about Zaki: that is still an answer to "is he there?".
        self.assertEqual(rows[2], "Zaki، " + offline)
        # The last message belongs to the chat views, not to this one.
        self.assertNotIn("first line", rows[1])
        self.assertEqual(self.spoken[-1], self.text(c.MSG_CONTACTS_COUNT_FORMAT_KEY).format(
            view=self.text(c.VIEW_CONTACTS_KEY), count=3, online=1
        ))

    def test_a_contact_coming_online_shows_on_their_row(self):
        self.show_contacts()
        self.fire("UserUpdate", Record(status=types.UserStatusOnline(expires=None), user_id=1))
        self.assertTrue(pump(lambda: self.text(c.STATUS_ONLINE_KEY) in self.rows()[1]))
        # Nothing moves under the user's cursor; the order is set afresh on the next visit.
        self.assertEqual([dialog["title"] for dialog in self.frame.dialogs], ["Basma", "Ali", "Zaki"])

    def test_a_contact_never_written_to_opens_as_a_chat(self):
        self.show_contacts()
        self.frame.dialogs_list.SetSelection(2)
        self.frame.on_open_dialog(None)
        self.assertTrue(pump(lambda: self.frame.message_input.IsEnabled()))
        self.assertEqual(self.frame.current_dialog_id, 9)
        self.assertIsNotNone(self.frame.find_known_dialog(9))

    def test_people_who_are_not_contacts_and_the_load_more_row_stay_out(self):
        self.frame.has_more_dialogs = True
        self.show_contacts()
        self.assertEqual(len(self.rows()), 3)
        self.assertNotIn("Stranger", " ".join(self.rows()))

    def test_an_account_without_contacts_says_so(self):
        FakeTelegramClient.contacts = []
        self.frame.view_tabs.SetSelection(CONTACTS_VIEW)
        self.frame.on_view_changed(None)
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.text(c.MSG_NO_CONTACTS_KEY)]))
        self.assertEqual(self.rows(), [])

    def test_a_deleted_contact_leaves_the_view(self):
        self.show_contacts()
        self.frame.toggle_contact(self.frame.dialogs[1])
        self.assertTrue(pump(lambda: len(self.rows()) == 2))
        self.assertEqual([dialog["title"] for dialog in self.frame.dialogs], ["Basma", "Zaki"])

    def test_chat_row_carries_the_whole_last_message_on_one_line(self):
        row = self.frame.dialogs_list.GetString(0)
        self.assertTrue(row.endswith("the very end"))
        self.assertIn("first line second line word", row)
        self.assertNotIn("…", row)
