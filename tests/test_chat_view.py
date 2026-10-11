"""The read-only info window: a summary, the invite link, members to view, and a way through to management."""
from unittest import mock

import wx
from telethon.tl import types

import core.constants as c
import ui.chat_info_dialog
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

    def test_admin_gets_a_manage_button_that_opens_the_control_window(self):
        dialog = self.info(0)
        self.assertTrue(dialog.manage_btn.IsShown())
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

        with mock.patch.object(ui.chat_info_dialog, "ChatControlDialog", FakeControl):
            dialog.on_manage(None)
        self.assertEqual(len(opened), 1)
        # A rename done in management is carried back and the window reloads under the new name.
        self.assertEqual(dialog.saved_title, "Renamed")
        self.assertIn("Renamed", dialog.GetTitle())

    def test_private_chat_shows_no_members_and_no_invite_link_and_no_manage(self):
        dialog = self.info(1)
        self.assertFalse(dialog.members_list.IsShown())
        self.assertFalse(dialog.invite_field.IsShown())
        self.assertFalse(dialog.manage_btn.IsShown())


class SubscriberInfoTest(WindowTestCase):
    # A channel this account only follows: not its creator, with no admin rights.
    chats = [(make_channel(5, "BigChannel", group=False), 0, False)]

    def test_subscriber_sees_info_but_no_manage_button(self):
        dialog = ChatInfoDialog(self.frame, self.i18n, self.manager, self.frame.all_dialogs[0])
        self.addCleanup(dialog.Destroy)
        self.assertTrue(pump(lambda: dialog.info is not None))
        self.assertFalse(dialog.manage_btn.IsShown())
        self.assertIn(self.text(c.INFO_ROLE_VIEWER_KEY), dialog.summary.GetValue())
