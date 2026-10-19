"""The chat info and management window, through the real manager and the fake Telegram."""
import unittest

import wx
from telethon.tl import types

import core.constants as c
import core.telegram_client as telegram_client
from tests.harness import (
    NOW, FakeChooser, FakeTelegramClient, WindowTestCase, make_channel, make_member, make_user, pump
)
from ui.chat_control_dialog import ChatControlDialog
from ui.invite_links_dialog import InviteLinksDialog

ADMIN_RIGHTS = types.ChatAdminRights(delete_messages=True, ban_users=True)
RESTRICTED = types.ChannelParticipantBanned(
    peer=types.PeerUser(13), kicked_by=10, date=NOW, left=False,
    banned_rights=types.ChatBannedRights(until_date=None, send_messages=True)
)
MEMBERS = [
    make_member(10, "Me", types.ChannelParticipantCreator(10, types.ChatAdminRights()), is_self=True),
    make_member(11, "Mona", types.ChannelParticipantAdmin(11, 10, NOW, ADMIN_RIGHTS)),
    make_member(12, "Zed"),
    make_member(13, "Quiet", RESTRICTED),
]


class ChatInfoTestCase(WindowTestCase):
    """Opens the info window on the first chat of `chats`."""

    def setUp(self):
        super().setUp()
        FakeTelegramClient.members = list(MEMBERS)
        FakeTelegramClient.banned = [make_member(30, "Spammer")]
        self.dialog = ChatControlDialog(self.frame, self.i18n, self.manager, self.frame.all_dialogs[0])
        self.addCleanup(self.dialog.Destroy)
        self.dialog.PopupMenu = self.frame.PopupMenu
        self.assertTrue(pump(lambda: self.dialog.info is not None), "chat info did not load")

    def wait_for_members(self, count):
        self.assertTrue(pump(lambda: len(self.dialog.members) == count), "members did not load")

    def member(self, name):
        return next(member for member in self.dialog.members if member["name"] == name)


class OwnedGroupTest(ChatInfoTestCase):
    chats = [(make_channel(4, "MyGroup", group=True, creator=True), 0, False)]

    def setUp(self):
        super().setUp()
        self.wait_for_members(4)

    def test_owner_can_edit_and_sees_every_management_control(self):
        self.assertTrue(self.dialog.title_input.IsEditable())
        for control in (self.dialog.save_btn, self.dialog.invite_btn, self.dialog.log_btn,
                        self.dialog.permissions_btn, self.dialog.list_choice):
            self.assertTrue(control.IsShown())
        self.assertEqual(self.dialog.list_choice.GetCount(), 3)

    def test_members_are_listed_with_their_roles(self):
        rows = self.dialog.members_list.GetItems()
        self.assertEqual(rows[2], "Zed")
        self.assertIn(self.text(c.MEMBER_ROLE_OWNER), rows[0])
        self.assertIn(self.text(c.MEMBER_ROLE_ADMIN), rows[1])
        self.assertIn(self.text(c.MEMBER_ROLE_RESTRICTED), rows[3])

    def test_actions_depend_on_who_the_member_is(self):
        actions = self.dialog.member_actions
        self.assertEqual(actions(self.member("Me")), [])
        self.assertEqual(actions(self.member("Zed")),
                         [c.MEMBER_ACTION_MUTE, c.MEMBER_ACTION_RESTRICT, c.MEMBER_ACTION_DELETE_MESSAGES,
                          c.MEMBER_ACTION_KICK, c.MEMBER_ACTION_BAN, c.MEMBER_ACTION_PROMOTE])
        self.assertEqual(actions(self.member("Quiet"))[0], c.MEMBER_ACTION_UNMUTE)
        self.assertEqual(actions(self.member("Mona")),
                         [c.MEMBER_ACTION_KICK, c.MEMBER_ACTION_BAN, c.MEMBER_ACTION_PROMOTE, c.MEMBER_ACTION_TITLE,
                          c.MEMBER_ACTION_DEMOTE])

    def test_nothing_happens_without_confirmation(self):
        self.box_answer = wx.NO
        self.dialog.manage_member(self.member("Zed"), c.MEMBER_ACTION_BAN)
        pump(timeout=0.2)
        self.assertIn("Zed", self.boxes[-1])
        self.assertIn("MyGroup", self.boxes[-1])
        self.assertEqual(self.calls("permissions"), [])
        self.assertEqual(self.saved_rights(), [])

    def saved_rights(self):
        return [call[1].banned_rights for call in self.calls("EditChatDefaultBannedRightsRequest")]

    def test_ban_mute_and_kick_reach_the_right_member(self):
        self.dialog.manage_member(self.member("Zed"), c.MEMBER_ACTION_BAN)
        self.dialog.manage_member(self.member("Zed"), c.MEMBER_ACTION_MUTE)
        self.dialog.manage_member(self.member("Zed"), c.MEMBER_ACTION_KICK)
        self.assertTrue(pump(lambda: len(self.calls("permissions")) == 2 and self.calls("kick")))
        self.assertEqual(self.calls("permissions"), [
            ("permissions", 12, {"view_messages": False}),
            ("permissions", 12, {"send_messages": False}),
        ])
        self.assertEqual(self.calls("kick"), [("kick", 12)])

    def test_editing_an_admin_starts_from_their_rights_and_sets_each_one_explicitly(self):
        mona = self.member("Mona")
        self.assertEqual(mona["rights"], {"delete_messages", "ban_users"})
        offered = [name for name in c.ADMIN_RIGHTS if name not in c.CHANNEL_ONLY_RIGHTS]
        FakeChooser.selections = [offered.index("pin_messages")]
        self.dialog.manage_member(mona, c.MEMBER_ACTION_PROMOTE)
        self.assertTrue(pump(lambda: self.calls("EditAdminRequest")))
        self.assertEqual(len(FakeChooser.last_choices), len(offered))
        request = self.calls("EditAdminRequest")[0][1]
        self.assertEqual(telegram_client.get_peer_id(request.user_id), 11)
        self.assertEqual(
            {name: bool(getattr(request.admin_rights, name)) for name in c.ADMIN_RIGHTS},
            {name: name == "pin_messages" for name in c.ADMIN_RIGHTS}
        )

    def test_promoting_with_no_rights_chosen_sends_nothing(self):
        FakeChooser.selections = []
        self.dialog.manage_member(self.member("Zed"), c.MEMBER_ACTION_PROMOTE)
        pump(timeout=0.2)
        self.assertEqual(self.calls("EditAdminRequest"), [])
        self.assertEqual(self.boxes, [self.text(c.MSG_NO_RIGHTS_CHOSEN_KEY)])

    def test_banned_list_offers_only_unban(self):
        self.dialog.list_choice.SetSelection(1)
        self.dialog.on_search_members(None)
        self.wait_for_members(1)
        spammer = self.dialog.members[0]
        self.assertEqual(self.dialog.member_actions(spammer), [c.MEMBER_ACTION_UNBAN])
        self.dialog.manage_member(spammer, c.MEMBER_ACTION_UNBAN)
        self.assertTrue(pump(lambda: self.calls("permissions") == [("permissions", 30, {})]))

    def test_member_search_filters_by_name(self):
        self.dialog.search_input.SetValue("mo")
        self.dialog.on_search_members(None)
        self.wait_for_members(1)
        self.assertEqual(self.dialog.members[0]["name"], "Mona")

    def test_member_permissions_change_only_what_was_edited(self):
        # Everything is allowed to start with; take away sending photos.
        FakeChooser.selections = [i for i, name in enumerate(c.MEMBER_PERMISSIONS) if name != "send_photos"]
        self.dialog.on_member_permissions(None)
        self.assertTrue(pump(lambda: self.saved_rights()))
        rights = self.saved_rights()[0]
        self.assertTrue(rights.send_photos)
        # Other media are still allowed, so media as a whole is, and writing.
        self.assertFalse(rights.send_media or rights.send_messages or rights.send_videos or rights.view_messages)
        self.assertFalse(rights.invite_users or rights.embed_links)

    def test_unchanged_member_permissions_are_not_saved(self):
        FakeChooser.selections = list(range(len(c.MEMBER_PERMISSIONS)))
        self.dialog.on_member_permissions(None)
        pump(timeout=0.3)
        self.assertEqual(self.calls("permissions"), [])


class InviteLinksTest(WindowTestCase):
    chats = [(make_channel(4, "MyGroup", group=True, creator=True), 0, False)]

    def setUp(self):
        super().setUp()
        FakeTelegramClient.invites = [
            types.ChatInviteExported(link="https://t.me/+main", admin_id=10, date=NOW, permanent=True, usage=7),
            types.ChatInviteExported(link="https://t.me/+friends", admin_id=10, date=NOW, title="Friends"),
        ]
        chat = self.frame.all_dialogs[0]
        self.dialog = InviteLinksDialog(self.frame, self.i18n, self.manager, chat["id"], chat["title"])
        self.addCleanup(self.dialog.Destroy)
        self.assertTrue(pump(lambda: len(self.dialog.links) == 2), "links did not load")

    def test_links_read_with_name_and_usage(self):
        rows = self.dialog.links_list.GetItems()
        self.assertIn(self.text(c.INVITE_LINK_MAIN_KEY), rows[0])
        self.assertIn("7", rows[0])
        self.assertTrue(rows[1].startswith("Friends"))

    def test_copy_puts_the_selected_link_on_the_clipboard(self):
        self.dialog.links_list.SetSelection(1)
        self.dialog.on_copy(None)
        data = wx.TextDataObject()
        wx.TheClipboard.Open()
        wx.TheClipboard.GetData(data)
        wx.TheClipboard.Close()
        self.assertEqual(data.GetText(), "https://t.me/+friends")

    def test_new_link_can_require_approval(self):
        FakeChooser.values = ["Work"]
        self.box_answer = wx.YES
        self.dialog.on_new(None)
        self.assertTrue(pump(lambda: len(self.dialog.links) == 3))
        request = self.calls("ExportChatInviteRequest")[0][1]
        self.assertEqual((request.title, request.request_needed), ("Work", True))
        self.assertIn(self.text(c.INVITE_LINK_APPROVAL_SUFFIX_KEY), self.dialog.links_list.GetString(2))

    def test_cancelling_the_approval_question_creates_nothing(self):
        FakeChooser.values = ["Work"]
        self.box_answer = wx.CANCEL
        self.dialog.on_new(None)
        pump(timeout=0.2)
        self.assertEqual(self.calls("ExportChatInviteRequest"), [])

    def test_revoke_needs_confirmation_and_targets_the_selected_link(self):
        self.dialog.links_list.SetSelection(1)
        self.box_answer = wx.NO
        self.dialog.on_revoke(None)
        pump(timeout=0.2)
        self.assertEqual(self.calls("EditExportedChatInviteRequest"), [])
        self.box_answer = wx.YES
        self.dialog.on_revoke(None)
        self.assertTrue(pump(lambda: len(self.dialog.links) == 1))
        request = self.calls("EditExportedChatInviteRequest")[0][1]
        self.assertEqual((request.link, request.revoked), ("https://t.me/+friends", True))


class RestrictedGroupPermissionsTest(ChatInfoTestCase):
    """A group that already limits things this app does not show: saving must not undo them."""

    restricted = make_channel(4, "Strict", group=True, creator=True)
    restricted.default_banned_rights = types.ChatBannedRights(until_date=None, send_games=True, send_inline=True)
    chats = [(restricted, 0, False)]

    def test_hidden_restrictions_survive_a_save(self):
        FakeChooser.selections = [i for i, name in enumerate(c.MEMBER_PERMISSIONS) if name != "invite_users"]
        self.dialog.on_member_permissions(None)
        saved = lambda: [call[1].banned_rights for call in self.calls("EditChatDefaultBannedRightsRequest")]
        self.assertTrue(pump(saved))
        rights = saved()[0]
        self.assertTrue(rights.send_games and rights.send_inline)
        self.assertTrue(rights.invite_users)
        self.assertFalse(rights.send_messages or rights.send_stickers)


class SubscriberTest(ChatInfoTestCase):
    chats = [(make_channel(3, "News"), 0, False)]

    def test_plain_subscriber_gets_a_read_only_window(self):
        self.assertFalse(self.dialog.title_input.IsEditable())
        for control in (self.dialog.save_btn, self.dialog.invite_btn, self.dialog.log_btn,
                        self.dialog.permissions_btn, self.dialog.list_choice):
            self.assertFalse(control.IsShown())
        self.wait_for_members(4)
        self.assertEqual(self.dialog.member_actions(self.member("Zed")), [])


class PrivateChatTest(ChatInfoTestCase):
    chats = [(make_user(1, "Ali"), 0, False)]

    def test_private_chat_has_no_members_section(self):
        self.assertFalse(self.dialog.members_list.IsShown())
        self.assertFalse(self.dialog.search_input.IsShown())
        self.assertIn(self.text(c.CHAT_KIND_USER), self.dialog.summary.GetValue())


if __name__ == "__main__":
    unittest.main()
