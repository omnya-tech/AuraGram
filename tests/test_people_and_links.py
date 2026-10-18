"""Contacts and blocking, finding and joining chats across Telegram, and the links inside messages."""
from unittest import mock

import wx
from telethon.tl import types

import core.constants as c
import core.telegram_client as telegram_client
import ui.chat_list
import ui.message_actions
from ui.global_search_dialog import GlobalSearchDialog
from tests.harness import (
    NOW, FakeChooser, FakeTelegramClient, WindowTestCase, make_channel, make_message, make_user, pump
)

ALI = make_user(1, "Ali")
STRANGER = make_user(2, "Stranger", contact=False)
GROUP = make_channel(4, "Team", group=True)
ZAKI = make_user(9, "Zaki", contact=False)
CLUB = make_channel(11, "Secret club", group=True)


def open_channel():
    """A public channel this account is looking at without having joined."""
    return types.Channel(id=12, title="Open news", photo=None, date=NOW, broadcast=True, left=True, access_hash=1)


class Entity:
    """One link or mention inside a message's text, as Telethon reports it."""

    def __init__(self, kind, text, **attributes):
        self.pair = (kind(offset=0, length=len(text), **attributes), text)


def linked_message(message_id, text, *entities):
    return make_message(
        message_id, text, sender=ALI, get_entities_text=lambda: [entity.pair for entity in entities]
    )


class PeopleTest(WindowTestCase):
    chats = [(ALI, 0, False), (STRANGER, 0, False), (GROUP, 0, False)]

    def requests(self, name):
        return [call[1] for call in self.calls(name)]

    def test_stranger_is_saved_under_the_name_the_user_types(self):
        stranger = self.frame.dialogs[1]
        FakeChooser.values = ["Samir from work"]
        self.frame.toggle_contact(stranger)
        self.assertTrue(pump(lambda: stranger["category"] == c.CATEGORY_CONTACTS))
        self.assertEqual(self.requests("AddContactRequest")[0].first_name, "Samir from work")
        self.assertIn("Stranger", self.spoken[-1])
        # Now the same entry offers the opposite.
        self.frame.dialogs_list.SetSelection(1)
        self.frame.on_dialog_context_menu(self.context_event(self.frame.dialogs_list))
        self.assertIn(self.text(c.CONTEXT_DELETE_CONTACT_KEY), self.menu_labels)

    def test_deleting_a_contact_asks_first(self):
        ali = self.frame.dialogs[0]
        self.box_answer = wx.NO
        self.frame.toggle_contact(ali)
        self.assertEqual(self.requests("DeleteContactsRequest"), [])
        self.box_answer = wx.YES
        self.frame.toggle_contact(ali)
        self.assertTrue(pump(lambda: ali["category"] == c.CATEGORY_NON_CONTACTS))
        self.assertEqual(len(self.requests("DeleteContactsRequest")), 1)

    def test_groups_cannot_be_contacts_or_blocked(self):
        group = self.frame.dialogs[2]
        self.frame.toggle_contact(group)
        self.frame.toggle_blocked(group)
        self.assertEqual(self.spoken, [self.text(c.MSG_NOT_A_PERSON_KEY)] * 2)
        self.frame.dialogs_list.SetSelection(2)
        self.frame.on_dialog_context_menu(self.context_event(self.frame.dialogs_list))
        self.assertNotIn(self.text(c.CONTEXT_BLOCK_KEY), self.menu_labels)

    def test_new_contact_by_phone_opens_their_chat(self):
        FakeTelegramClient.public["+201000000009"] = ZAKI
        FakeChooser.values = ["+201000000009", "Zaki"]
        self.frame.on_add_contact_menu(None)
        self.assertTrue(pump(lambda: self.frame.current_dialog_id == 9))
        self.assertEqual(self.requests("ImportContactsRequest")[0].contacts[0].first_name, "Zaki")

    def test_number_without_an_account_is_reported(self):
        FakeChooser.values = ["+201111111111", "Nobody"]
        self.frame.on_add_contact_menu(None)
        self.assertTrue(pump(lambda: self.boxes == [self.text(c.ERR_CHAT_NOT_FOUND_KEY)]))

    def test_blocking_asks_and_blocks(self):
        ali = self.frame.dialogs[0]
        self.frame.toggle_blocked(ali)
        self.assertTrue(pump(lambda: len(self.requests("BlockRequest")) == 1))
        self.assertIn("Ali", self.boxes[0])
        self.assertTrue(pump(lambda: self.spoken[-1] == self.text(c.MSG_BLOCKED_FORMAT_KEY).format(name="Ali")))

    def test_blocked_list_unblocks_the_chosen_person(self):
        self.frame.on_blocked_menu(None)
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.text(c.MSG_NO_BLOCKED_KEY)]))
        FakeTelegramClient.blocked_users = [ZAKI]
        self.frame.on_blocked_menu(None)
        self.assertTrue(pump(lambda: len(self.requests("UnblockRequest")) == 1))
        self.assertEqual(FakeChooser.last_choices, ["Zaki"])
        self.assertEqual(telegram_client.get_peer_id(self.requests("UnblockRequest")[0].id), 9)


class ScriptedSearch(GlobalSearchDialog):
    """The search window, worked by the test: it searches for `query` and opens the result at `pick`."""

    query = ""
    pick = 0

    def ShowModal(self):
        self.search_input.SetValue(ScriptedSearch.query)
        self.search()
        pump(lambda: not self.busy and self.round > 0)
        if not self.results:
            return wx.ID_CANCEL
        self.results_list.SetSelection(ScriptedSearch.pick)
        self.chosen = self.selected()
        return wx.ID_OK


class FindingAndJoiningTest(WindowTestCase):
    chats = [(ALI, 0, False)]
    history = {1: [
        linked_message(
            1, "see example.org and this, ask @openly",
            Entity(types.MessageEntityUrl, "example.org"),
            Entity(types.MessageEntityTextUrl, "this", url="https://t.me/openly"),
            Entity(types.MessageEntityMention, "@openly"),
        ),
        make_message(2, "nothing to follow", sender=ALI),
    ]}

    def setUp(self):
        super().setUp()
        patch = mock.patch.object(ui.chat_list, "GlobalSearchDialog", ScriptedSearch)
        patch.start()
        self.addCleanup(patch.stop)
        self.channel = open_channel()
        FakeTelegramClient.public.update(openly=self.channel, zaki=ZAKI)
        self.channel_id = telegram_client.get_peer_id(self.channel)

    def test_search_across_telegram_opens_the_chosen_result(self):
        ScriptedSearch.query = "zak"
        self.frame.on_global_search_menu(None)
        self.assertTrue(pump(lambda: self.frame.current_dialog_id == 9))

        ScriptedSearch.query = "nothing like this"
        self.frame.on_global_search_menu(None)
        self.assertIn(self.text(c.MSG_GLOBAL_SEARCH_EMPTY_KEY), self.spoken)

    def test_public_channel_opens_read_only_until_joined(self):
        self.frame.open_link("https://t.me/openly")
        self.assertTrue(pump(lambda: self.frame.current_dialog_id == self.channel_id))
        channel = self.frame.find_known_dialog(self.channel_id)
        self.assertFalse(channel["joined"])
        self.frame.on_dialog_context_menu(self.context_event(self.frame.dialogs_list))
        self.assertIn(self.text(c.CONTEXT_JOIN_KEY), self.menu_labels)

        self.frame.join_dialog(channel)
        self.assertTrue(pump(lambda: channel["joined"]))
        self.assertEqual(len(self.calls("JoinChannelRequest")), 1)
        self.frame.join_dialog(channel)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_ALREADY_JOINED_KEY))
        self.assertEqual(len(self.calls("JoinChannelRequest")), 1)

    def open_unjoined_channel(self):
        ScriptedSearch.query = "open"
        self.frame.on_global_search_menu(None)
        self.assertTrue(pump(lambda: self.frame.current_dialog_id == self.channel_id))
        return self.frame.find_known_dialog(self.channel_id)

    def test_a_channel_only_looked_at_says_how_to_join_and_leaves_the_list_when_closed(self):
        channel = self.open_unjoined_channel()
        hint = self.frame.join_hint(channel)
        self.assertIn("Ctrl+Shift+J", hint)
        self.assertIn(hint, self.spoken)
        self.assertEqual(self.frame.input_label.GetLabel(), hint)
        self.assertIn(self.text(c.DIALOG_NOT_JOINED_KEY), self.frame.dialogs_list.GetString(self.frame.find_dialog_index(self.channel_id)))
        self.frame.close_chat()
        self.assertIsNone(self.frame.find_known_dialog(self.channel_id))
        self.assertEqual(self.frame.find_dialog_index(self.channel_id), wx.NOT_FOUND)

    def test_leaving_a_channel_never_joined_asks_telegram_nothing_and_shows_no_error(self):
        channel = self.open_unjoined_channel()
        self.frame.leave_chat(channel, False)
        self.assertEqual(self.boxes, [])
        self.assertEqual(self.calls("leave"), [])
        self.assertIsNone(self.frame.find_known_dialog(self.channel_id))
        self.assertIsNone(self.frame.current_dialog_id)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_PREVIEW_REMOVED_FORMAT_KEY).format(title=channel["title"]))

    def test_joined_it_stays_in_the_list_and_can_be_written_to(self):
        channel = self.open_unjoined_channel()
        self.frame.join_dialog(channel)
        self.assertTrue(pump(lambda: channel["joined"]))
        self.assertNotIn("preview", channel)
        self.frame.close_chat()
        self.assertIs(self.frame.find_known_dialog(self.channel_id), channel)

    def test_invitation_link_joins_only_after_a_yes(self):
        FakeTelegramClient.invitation = ("Secret club", CLUB)
        self.box_answer = wx.NO
        self.frame.open_link("https://t.me/+AbCdEf123")
        self.assertTrue(pump(lambda: len(self.boxes) == 1))
        self.assertIn("Secret club", self.boxes[0])
        self.assertEqual(self.calls("ImportChatInviteRequest"), [])

        self.box_answer = wx.YES
        self.frame.open_link("https://t.me/+AbCdEf123")
        self.assertTrue(pump(lambda: self.frame.current_dialog_id == telegram_client.get_peer_id(CLUB)))
        self.assertEqual(self.calls("ImportChatInviteRequest")[0][1].hash, "AbCdEf123")

    def test_links_of_a_message_are_listed_with_their_real_addresses(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(0)
        with mock.patch.object(ui.message_actions.webbrowser, "open") as browser:
            FakeChooser.selection = 0
            self.frame.on_open_link_menu(None)
            self.assertEqual(FakeChooser.last_choices, ["example.org", "https://t.me/openly", "https://t.me/openly"])
            # An ordinary address goes to the browser.
            browser.assert_called_once_with("https://example.org")

            # A Telegram address opens here as a chat instead.
            FakeChooser.selection = 2
            self.frame.on_open_link_menu(None)
            self.assertTrue(pump(lambda: self.frame.current_dialog_id == self.channel_id))
            self.assertEqual(browser.call_count, 1)

    def test_message_without_links_says_so(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(1)
        self.frame.on_open_link_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NO_LINKS_KEY))
