"""What else admins can do: every join request at once, revoked links cleared, who joined by each link, the group's
stickers and emoji, boosts, colours, a narrowed admin log with anti-spam's mistakes, and the newer switches."""
from unittest import mock

import wx
from telethon.tl import types

import core.constants as c
import ui.invite_links_dialog
from tests.harness import (
    NOW, FakeChooser, FakeTelegramClient, Record, WindowTestCase, make_channel, make_member, make_user, pump
)
from ui.admin_log_dialog import AdminLogDialog
from ui.chat_admin_dialog import ChatAdminDialog
from ui.chat_control_dialog import ChatControlDialog
from ui.invite_links_dialog import InviteLinksDialog

MY_GROUP = make_channel(4, "MyGroup", group=True, creator=True)
MY_CHANNEL = make_channel(5, "MyNews", creator=True)
MEMBERS = [
    make_member(10, "Me", types.ChannelParticipantCreator(10, types.ChatAdminRights()), is_self=True),
    make_member(11, "Mona", types.ChannelParticipantAdmin(11, 10, NOW, types.ChatAdminRights(other=True))),
    make_member(12, "Zed"),
]


class AdminExtrasTest(WindowTestCase):
    chats = [(MY_GROUP, 0, False), (MY_CHANNEL, 0, False)]

    def setUp(self):
        super().setUp()
        FakeTelegramClient.members = list(MEMBERS)

    def chat(self, index):
        return self.frame.all_dialogs[index]

    def admin(self, index):
        chat = self.chat(index)
        dialog = ChatAdminDialog(self.frame, self.i18n, self.manager, chat["id"], chat["title"])
        self.addCleanup(dialog.Destroy)
        self.assertTrue(pump(lambda: dialog.settings is not None), "admin settings did not load")
        return dialog

    def requests(self, name):
        return [call[1] for call in self.calls(name)]

    def said(self, key):
        return pump(lambda: self.spoken[-1:] == [self.text(key)])

    def heard(self, key):
        # Then the list, loaded anew, says how many are in it.
        return pump(lambda: self.text(key) in self.spoken)

    def requests_list(self):
        FakeTelegramClient.join_requests = [make_user(20, "Waiting"), make_user(21, "Hopeful")]
        dialog = ChatControlDialog(self.frame, self.i18n, self.manager, self.chat(0))
        self.addCleanup(dialog.Destroy)
        self.assertTrue(pump(lambda: len(dialog.members) == len(MEMBERS)), "members did not load")
        self.assertFalse(dialog.approve_all_btn.IsShown())
        dialog.list_choice.SetSelection(dialog.list_modes.index(c.MEMBERS_REQUESTS))
        dialog.load_members()
        self.assertTrue(pump(lambda: len(dialog.members) == 2), "join requests did not load")
        self.assertTrue(dialog.approve_all_btn.IsShown() and dialog.decline_all_btn.IsShown())
        return dialog

    def test_every_join_request_is_approved_at_once(self):
        dialog = self.requests_list()
        dialog.decide_all(True)
        self.assertTrue(self.heard(c.MSG_ALL_APPROVED_KEY))
        self.assertTrue(self.requests("HideAllChatJoinRequestsRequest")[0].approved)
        # Nobody is left waiting, so the buttons go.
        self.assertTrue(pump(lambda: not dialog.approve_all_btn.IsShown()))

    def test_declining_all_waits_for_a_yes(self):
        dialog = self.requests_list()
        self.box_answer = wx.NO
        dialog.decide_all(False)
        pump(timeout=0.2)
        self.assertEqual(self.requests("HideAllChatJoinRequestsRequest"), [])
        self.box_answer = wx.YES
        dialog.decide_all(False)
        self.assertTrue(self.heard(c.MSG_ALL_DECLINED_KEY))
        self.assertFalse(self.requests("HideAllChatJoinRequestsRequest")[0].approved)

    def invite_links(self):
        chat = self.chat(0)
        dialog = InviteLinksDialog(self.frame, self.i18n, self.manager, chat["id"], chat["title"])
        self.addCleanup(dialog.Destroy)
        return dialog

    def test_revoked_links_are_counted_then_deleted(self):
        FakeTelegramClient.revoked_invites = 3
        self.invite_links().on_delete_revoked(None)
        self.assertTrue(pump(lambda: self.requests("DeleteRevokedExportedChatInvitesRequest")))
        self.assertIn("3", self.boxes[-1])

    def test_no_revoked_links_is_said_and_nothing_deleted(self):
        self.invite_links().on_delete_revoked(None)
        self.assertTrue(self.said(c.MSG_NO_REVOKED_KEY))
        self.assertEqual(self.requests("DeleteRevokedExportedChatInvitesRequest"), [])

    def test_group_gets_a_sticker_set_or_none(self):
        FakeTelegramClient.full_chat = dict(can_set_stickers=True)
        FakeTelegramClient.sticker_sets = [("Cats", ["😺"]), ("Dogs", ["🐶"])]
        dialog = self.admin(0)
        self.assertTrue(dialog.buttons[c.BTN_GROUP_STICKERS_KEY].IsEnabled())
        FakeChooser.selection = 2
        dialog.on_group_stickers(None)
        self.assertTrue(self.said(c.MSG_GROUP_STICKERS_SAVED_KEY))
        self.assertEqual(FakeChooser.last_choices, [self.text(c.GROUP_STICKERS_NONE_KEY), "Cats", "Dogs"])
        self.assertEqual(self.requests("SetStickersRequest")[0].stickerset.id, 1)

        FakeChooser.selection = 0
        dialog.on_group_stickers(None)
        self.assertTrue(pump(lambda: len(self.requests("SetStickersRequest")) == 2))
        self.assertIsInstance(self.requests("SetStickersRequest")[1].stickerset, types.InputStickerSetEmpty)

    def test_stickers_are_not_offered_where_telegram_does_not_allow_them(self):
        self.assertFalse(self.admin(0).buttons[c.BTN_GROUP_STICKERS_KEY].IsEnabled())

    def test_boosts_say_the_level_and_what_the_next_one_needs(self):
        dialog = self.admin(1)
        shown = []
        dialog.show_boosts = lambda boosts: shown.append(boosts)
        dialog.on_boosts(None)
        self.assertTrue(pump(lambda: shown))
        self.assertEqual(shown[0], {"level": 2, "boosts": 7, "next": 10, "link": "https://t.me/boost/x"})

    def test_new_switches_are_read_and_saved(self):
        FakeTelegramClient.full_chat = dict(antispam=True, participants_hidden=False)
        group = self.admin(0)
        self.assertTrue(group.controls[c.SETTING_ANTISPAM].GetValue())
        group.controls[c.SETTING_ANTISPAM].SetValue(False)
        group.controls[c.SETTING_HIDE_MEMBERS].SetValue(True)
        group.on_save(None)
        self.assertTrue(self.said(c.MSG_ADMIN_SETTINGS_SAVED_KEY))
        self.assertFalse(self.requests("ToggleAntiSpamRequest")[0].enabled)
        self.assertTrue(self.requests("ToggleParticipantsHiddenRequest")[0].enabled)

    def test_the_authors_account_goes_with_the_signature(self):
        channel = self.admin(1)
        channel.controls[c.SETTING_SIGNATURES].SetValue(True)
        channel.controls[c.SETTING_SIGNATURE_PROFILES].SetValue(True)
        channel.on_save(None)
        self.assertTrue(self.said(c.MSG_ADMIN_SETTINGS_SAVED_KEY))
        requests = self.requests("ToggleSignaturesRequest")
        self.assertEqual(len(requests), 1)
        self.assertTrue(requests[0].signatures_enabled and requests[0].profiles_enabled)

    def test_admin_log_is_narrowed_by_kind_and_by_admin(self):
        FakeTelegramClient.admin_log = [Record(
            user=MEMBERS[1], date=NOW, action=types.ChannelAdminLogEventActionParticipantJoin()
        )]
        chat = self.chat(0)
        dialog = AdminLogDialog(self.frame, self.i18n, self.manager, chat["id"], chat["title"])
        self.addCleanup(dialog.Destroy)
        self.assertTrue(pump(lambda: dialog.admin_choice.GetCount() == 3), "admins did not load")
        self.assertEqual(dialog.admin_choice.GetString(2), "Mona")
        self.assertEqual(self.calls("admin_log")[0][1], {})

        dialog.kind_choice.SetSelection(list(c.ADMIN_LOG_FILTERS).index("ADMIN_LOG_FILTER_MEMBERS"))
        dialog.admin_choice.SetSelection(2)
        dialog.load()
        self.assertTrue(pump(lambda: len(self.calls("admin_log")) == 2))
        narrowed = self.calls("admin_log")[1][1]
        self.assertTrue(narrowed["join"] and narrowed["leave"] and narrowed["invite"])
        self.assertEqual(narrowed["admins"][0].user_id, 11)
        self.assertTrue(pump(lambda: "Mona" in dialog.events_list.GetString(0)))


    def test_who_joined_with_a_link_and_who_waits(self):
        FakeTelegramClient.invites = [
            types.ChatInviteExported(link="https://t.me/+friends", admin_id=10, date=NOW, title="Friends", usage=1),
        ]
        FakeTelegramClient.link_joiners = {
            ("https://t.me/+friends", False): [make_user(20, "Sami")],
            ("https://t.me/+friends", True): [make_user(21, "Hala"), make_user(22, "Omar")],
        }
        dialog = self.invite_links()
        self.assertTrue(pump(lambda: dialog.links), "links did not load")
        shown = []

        class FakeText:
            def __init__(self, parent, i18n, title, text):
                shown.append((title, text))

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def ShowModal(self):
                return wx.ID_OK

        with mock.patch.object(ui.invite_links_dialog, "TextDialog", FakeText):
            dialog.on_joiners(None)
            self.assertTrue(pump(lambda: shown))
        title, text = shown[0]
        self.assertIn("Friends", title)
        self.assertEqual(text.splitlines(), [
            self.text(c.LINK_JOINED_FORMAT_KEY).format(count=1, names="Sami"),
            self.text(c.LINK_WAITING_FORMAT_KEY).format(count=2, names="Hala، Omar"),
        ])

    def test_anti_spam_mistake_is_reported_from_the_log(self):
        FakeTelegramClient.admin_log = [
            Record(
                user=make_user(c.ANTISPAM_USER_ID, "Anti-Spam"), user_id=c.ANTISPAM_USER_ID, date=NOW,
                action=types.ChannelAdminLogEventActionDeleteMessage(message=Record(id=77, message="hello all"))
            ),
            Record(user=MEMBERS[1], user_id=11, date=NOW, action=types.ChannelAdminLogEventActionParticipantJoin()),
        ]
        chat = self.chat(0)
        dialog = AdminLogDialog(self.frame, self.i18n, self.manager, chat["id"], chat["title"])
        self.addCleanup(dialog.Destroy)
        self.assertTrue(pump(lambda: len(dialog.events) == 2), "the log did not load")
        self.assertIn("hello all", dialog.events_list.GetString(0))
        self.assertTrue(dialog.not_spam_btn.IsEnabled())
        dialog.on_not_spam(None)
        self.assertTrue(self.said(c.MSG_NOT_SPAM_REPORTED_KEY))
        self.assertEqual(self.requests("ReportAntiSpamFalsePositiveRequest")[0].msg_id, 77)
        # What an admin did is not anti-spam's to take back.
        dialog.events_list.SetSelection(1)
        dialog.update_not_spam()
        self.assertFalse(dialog.not_spam_btn.IsEnabled())

    def test_group_gets_an_emoji_pack(self):
        FakeTelegramClient.emoji_sets = ["Faces", "Hands"]
        dialog = self.admin(0)
        self.assertTrue(dialog.buttons[c.BTN_GROUP_EMOJI_KEY].IsEnabled())
        self.assertFalse(self.admin(1).buttons[c.BTN_GROUP_EMOJI_KEY].IsEnabled())
        FakeChooser.selection = 2
        dialog.on_group_emoji(None)
        self.assertTrue(self.said(c.MSG_GROUP_EMOJI_SAVED_KEY))
        self.assertEqual(FakeChooser.last_choices, [self.text(c.GROUP_STICKERS_NONE_KEY), "Faces", "Hands"])
        self.assertEqual(self.requests("SetEmojiStickersRequest")[0].stickerset.id, 1)

    def test_channel_posts_are_translated_for_subscribers(self):
        channel = self.admin(1)
        self.assertFalse(channel.controls[c.SETTING_AUTOTRANSLATION].GetValue())
        channel.controls[c.SETTING_AUTOTRANSLATION].SetValue(True)
        channel.on_save(None)
        self.assertTrue(self.said(c.MSG_ADMIN_SETTINGS_SAVED_KEY))
        self.assertTrue(self.requests("ToggleAutotranslationRequest")[0].enabled)

    def test_colours_of_the_name_and_the_profile(self):
        channel = self.admin(1)
        name, profile = channel.controls[c.SETTING_NAME_COLOR], channel.controls[c.SETTING_PROFILE_COLOR]
        self.assertEqual(name.GetStringSelection(), self.text(c.COLOR_DEFAULT_KEY))
        self.assertEqual(name.GetCount(), 8)
        self.assertEqual(profile.GetCount(), 9)
        name.SetSelection(4)
        profile.SetSelection(8)
        channel.on_save(None)
        self.assertTrue(self.said(c.MSG_ADMIN_SETTINGS_SAVED_KEY))
        requests = {bool(request.for_profile): request for request in self.requests("UpdateColorRequest")}
        self.assertEqual(requests[False].color, 3)
        self.assertEqual(requests[True].color, 7)
