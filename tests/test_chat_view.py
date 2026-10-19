"""The read-only info window: a summary, the invite link and members to view. Management is apart from it,
in the chat's menu, for those who run the chat."""
from unittest import mock

import wx
from telethon.tl import types

import core.constants as c
import ui.chat_list
from tests.harness import NOW, FakeTelegramClient, WindowTestCase, make_channel, make_member, make_user, pump
from ui.chat_info_dialog import ChatInfoDialog

MY_GROUP = make_channel(4, "MyGroup", group=True, creator=True)
ALI = make_user(1, "Ali")
MEMBERS = [
    make_member(10, "Me", types.ChannelParticipantCreator(10, types.ChatAdminRights()), is_self=True),
    make_member(11, "Mona", types.ChannelParticipantAdmin(11, 10, NOW, types.ChatAdminRights(ban_users=True))),
    make_member(12, "Zed"),
]


class ReadOnlyInfoTest(WindowTestCase):
    chats = [(MY_GROUP, 0, False), (ALI, 0, False)]

    def info(self, index):
        FakeTelegramClient.members = list(MEMBERS)
        dialog = ChatInfoDialog(self.frame, self.i18n, self.manager, self.frame.all_dialogs[index])
        self.addCleanup(dialog.Destroy)
        self.assertTrue(pump(lambda: dialog.info is not None), "info did not load")
        return dialog

    def test_the_window_only_reads_it_has_no_editing_or_member_actions(self):
        dialog = self.info(0)
        # The summary is a read-only field, and there is no name box or save button to change anything.
        self.assertFalse(dialog.summary.IsEditable())
        self.assertFalse(hasattr(dialog, "title_input"))
        self.assertFalse(hasattr(dialog, "save_btn"))
        self.assertIn("MyGroup", dialog.GetTitle())
        self.assertIn(self.text(c.INFO_ROLE_MANAGER_KEY), dialog.summary.GetValue())

    def test_members_are_listed_for_viewing(self):
        dialog = self.info(0)
        self.assertTrue(pump(lambda: len(dialog.members) == len(MEMBERS)))
        rows = dialog.members_list.GetItems()
        self.assertIn("Mona", " ".join(rows))
        self.assertIn(self.text(c.MEMBER_ROLE_OWNER), rows[0])

    def test_each_member_says_whether_they_are_online(self):
        members = list(MEMBERS)
        members[1] = make_member(11, "Mona", MEMBERS[1].participant)
        members[1].status = types.UserStatusOnline(expires=NOW)
        members[2] = make_member(12, "Zed")
        members[2].status = types.UserStatusRecently()
        helper = make_member(13, "Helper bot")
        helper.bot = True
        FakeTelegramClient.members = members + [helper]
        dialog = ChatInfoDialog(self.frame, self.i18n, self.manager, self.frame.all_dialogs[0])
        self.addCleanup(dialog.Destroy)
        self.assertTrue(pump(lambda: len(dialog.members) == 4))
        rows = dialog.members_list.GetItems()
        role = self.text(c.INFO_MEMBER_ROLE_FORMAT_KEY).format
        self.assertEqual(rows[1], role(name=role(name="Mona", role=self.text(c.MEMBER_ROLE_ADMIN)), role=self.text(c.STATUS_ONLINE_KEY)))
        self.assertEqual(rows[2], role(name="Zed", role=self.text("STATUS_RECENTLY")))
        self.assertEqual(rows[3], role(name="Helper bot", role=self.text(c.MEMBER_BOT_KEY)))

    def test_invite_link_is_shown_and_copies(self):
        dialog = self.info(0)
        self.assertTrue(pump(lambda: dialog.invite_link is not None))
        self.assertTrue(dialog.invite_field.GetValue().startswith("https://t.me/"))
        self.assertEqual(dialog.invite_field.GetValue(), dialog.invite_link)
        self.assertTrue(dialog.copy_invite_btn.IsShown())
        dialog.on_copy_invite(None)
        data = wx.TextDataObject()
        wx.TheClipboard.Open(); wx.TheClipboard.GetData(data); wx.TheClipboard.Close()
        self.assertEqual(data.GetText(), dialog.invite_link)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_INVITE_COPIED_KEY))

    def test_info_has_no_way_into_management(self):
        self.assertFalse(hasattr(self.info(0), "manage_btn"))

    def menu(self, row):
        self.frame.dialogs_list.SetSelection(row)
        self.frame.on_dialog_context_menu(self.context_event(self.frame.dialogs_list))
        return list(self.menu_labels)

    def test_owner_gets_management_apart_from_the_info(self):
        labels = self.menu(0)
        info, manage = self.text(c.CONTEXT_INFO_GROUP_KEY), self.text(c.CONTEXT_MANAGE_GROUP_KEY)
        self.assertIn(info, labels)
        # Away from the info, just before the entries that cannot be undone.
        self.assertEqual(labels.index(manage), labels.index(self.text(c.CONTEXT_CLEAR_HISTORY_KEY)) - 1)
        self.assertNotIn(manage, self.menu(1))
        self.assertIn(self.text(c.CONTEXT_INFO_KEY), self.menu(1))

    def test_management_opens_and_carries_a_new_name_back_to_the_list(self):
        opened = []

        class FakeControl:
            def __init__(self, *args):
                opened.append(args)
                self.saved_title, self.deleted = "Renamed", False

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def ShowModal(self):
                return wx.ID_OK

        with mock.patch.object(ui.chat_list, "ChatControlDialog", FakeControl):
            self.frame.manage_chat(self.frame.dialogs[0])
        self.assertEqual(len(opened), 1)
        self.assertEqual(self.frame.dialogs[0]["title"], "Renamed")
        self.assertIn("Renamed", self.frame.dialogs_list.GetString(0))

    def test_management_is_refused_where_this_account_does_not_run_the_chat(self):
        self.frame.manage_chat(self.frame.dialogs[1])
        self.assertEqual(self.frame.GetStatusBar().GetStatusText(), self.text(c.MSG_NOT_ADMIN_KEY))

    def test_private_chat_shows_no_members_and_no_invite_link_and_no_manage(self):
        dialog = self.info(1)
        self.assertFalse(dialog.members_list.IsShown())
        self.assertFalse(dialog.invite_field.IsShown())


class SubscriberInfoTest(WindowTestCase):
    # A channel this account only follows: not its creator, with no admin rights.
    chats = [(make_channel(5, "BigChannel", group=False), 0, False)]

    def test_subscriber_sees_info_but_no_management(self):
        dialog = ChatInfoDialog(self.frame, self.i18n, self.manager, self.frame.all_dialogs[0])
        self.addCleanup(dialog.Destroy)
        self.assertTrue(pump(lambda: dialog.info is not None))
        self.assertFalse(self.frame.dialogs[0]["is_admin"])
        self.assertIn(self.text(c.INFO_ROLE_VIEWER_KEY), dialog.summary.GetValue())
