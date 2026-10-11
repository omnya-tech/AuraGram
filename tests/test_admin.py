"""Running a group or channel: its settings, its members' limits and titles, its numbers, and its end."""
import datetime

import wx
from telethon.tl import types

import core.constants as c
import core.telegram_client as telegram_client
from tests.harness import (
    NOW, FakeChooser, FakeTelegramClient, Record, WindowTestCase, make_channel, make_member, make_message, pump
)
from ui.chat_admin_dialog import ChatAdminDialog
from ui.chat_info_dialog import ChatInfoDialog

MY_GROUP = make_channel(4, "MyGroup", group=True, creator=True)
MY_CHANNEL = make_channel(5, "MyNews", creator=True)
HELPED = make_channel(6, "Helped", group=True, admin_rights=types.ChatAdminRights(invite_users=True))
ZAKI = types.User(id=9, first_name="Zaki", contact=True, access_hash=1)
MONA_RIGHTS = types.ChatAdminRights(delete_messages=True, ban_users=True, other=True)
MEMBERS = [
    make_member(10, "Me", types.ChannelParticipantCreator(10, types.ChatAdminRights()), is_self=True),
    make_member(11, "Mona", types.ChannelParticipantAdmin(11, 10, NOW, MONA_RIGHTS, rank="Helper")),
    make_member(12, "Zed"),
]
CHANNEL_ID = telegram_client.get_peer_id(MY_CHANNEL)


class AdminTestCase(WindowTestCase):
    chats = [(MY_GROUP, 0, False), (MY_CHANNEL, 0, False), (HELPED, 0, False)]
    history = {CHANNEL_ID: [make_message(1, "launch day", post=True, views=950, forwards=12)]}

    def setUp(self):
        super().setUp()
        FakeTelegramClient.members = list(MEMBERS)

    def admin(self, index):
        chat = self.frame.all_dialogs[index]
        dialog = ChatAdminDialog(self.frame, self.i18n, self.manager, chat["id"], chat["title"])
        self.addCleanup(dialog.Destroy)
        self.assertTrue(pump(lambda: dialog.settings is not None), "admin settings did not load")
        return dialog

    def requests(self, name):
        return [call[1] for call in self.calls(name)]


class ChatSettingsTest(AdminTestCase):
    def test_each_kind_of_chat_shows_only_its_own_settings(self):
        group, channel = set(self.admin(0).controls), set(self.admin(1).controls)
        shared = {c.SETTING_USERNAME, c.SETTING_PROTECTED, c.SETTING_TTL, c.SETTING_REACTIONS}
        self.assertEqual(channel, shared | {c.SETTING_SIGNATURES})
        self.assertEqual(group, shared | {
            c.SETTING_SLOW_MODE, c.SETTING_HISTORY_HIDDEN, c.SETTING_JOIN_TO_SEND,
            c.SETTING_JOIN_REQUEST, c.SETTING_FORUM,
        })

    def test_only_what_was_changed_is_sent(self):
        dialog = self.admin(0)
        dialog.on_save(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NOTHING_CHANGED_KEY))

        dialog.controls[c.SETTING_SLOW_MODE].SetSelection(2)
        dialog.controls[c.SETTING_PROTECTED].SetValue(True)
        dialog.controls[c.SETTING_USERNAME].SetValue("@my_group")
        self.assertEqual(dialog.changes(), {
            c.SETTING_SLOW_MODE: 30, c.SETTING_PROTECTED: True, c.SETTING_USERNAME: "@my_group",
        })
        dialog.on_save(None)
        self.assertTrue(pump(lambda: self.spoken[-1] == self.text(c.MSG_ADMIN_SETTINGS_SAVED_KEY)))
        self.assertEqual(self.requests("ToggleSlowModeRequest")[0].seconds, 30)
        self.assertTrue(self.requests("ToggleNoForwardsRequest")[0].enabled)
        self.assertEqual(self.requests("UpdateUsernameRequest")[0].username, "my_group")
        self.assertEqual(self.requests("ToggleForumRequest"), [])
        self.assertEqual(self.requests("SetHistoryTTLRequest"), [])

    def test_current_values_come_from_telegram(self):
        FakeTelegramClient.full_chat = dict(slowmode_seconds=60, ttl_period=7 * 24 * 60 * 60, hidden_prehistory=True)
        dialog = self.admin(0)
        self.assertEqual(dialog.controls[c.SETTING_SLOW_MODE].GetStringSelection(), self.text("SLOW_1_MINUTE"))
        self.assertEqual(dialog.controls[c.SETTING_TTL].GetStringSelection(), self.text("TTL_1_WEEK"))
        self.assertTrue(dialog.controls[c.SETTING_HISTORY_HIDDEN].GetValue())
        self.assertEqual(dialog.changes(), {})

    def test_value_this_window_does_not_offer_is_shown_and_left_alone(self):
        FakeTelegramClient.full_chat = dict(available_reactions=types.ChatReactionsSome(reactions=[]), ttl_period=3600)
        dialog = self.admin(1)
        self.assertIn(self.text(c.REACTIONS_SOME), dialog.controls[c.SETTING_REACTIONS].GetStringSelection())
        self.assertIn("3600", dialog.controls[c.SETTING_TTL].GetStringSelection())
        self.assertEqual(dialog.changes(), {})
        dialog.controls[c.SETTING_REACTIONS].SetSelection(0)
        dialog.on_save(None)
        self.assertTrue(pump(lambda: self.requests("SetChatAvailableReactionsRequest")))
        self.assertIsInstance(
            self.requests("SetChatAvailableReactionsRequest")[0].available_reactions, types.ChatReactionsAll
        )

    def test_admin_without_the_right_sees_but_cannot_change(self):
        dialog = self.admin(2)
        self.assertFalse(any(control.IsEnabled() for control in dialog.controls.values()))
        enabled = {key for key, button in dialog.buttons.items() if button.IsEnabled()}
        # This admin may only invite.
        self.assertEqual(enabled, {c.BTN_ADD_MEMBERS_KEY})

    def test_photo_and_new_members(self):
        dialog = self.admin(0)
        dialog.set_photo("logo.png")
        self.assertTrue(pump(lambda: self.requests("EditPhotoRequest")))
        self.assertEqual(self.requests("EditPhotoRequest")[0].photo.file, "uploaded:logo.png")

        FakeTelegramClient.contacts = [ZAKI]
        FakeChooser.selections = [0]
        dialog.on_add_members(None)
        self.assertTrue(pump(lambda: self.requests("InviteToChannelRequest")))
        self.assertEqual(len(self.requests("InviteToChannelRequest")[0].users), 1)
        self.assertTrue(pump(lambda: self.spoken[-1] == self.text(c.MSG_MEMBERS_ADDED_FORMAT_KEY).format(count=1)))

    def test_statistics_compare_with_the_period_before(self):
        value = lambda current, previous: Record(current=current, previous=previous)
        FakeTelegramClient.stats = Record(
            followers=value(1200.0, 1100.0), views_per_post=value(640.4, 500.0), shares_per_post=value(12.0, 9.0),
            reactions_per_post=value(30.0, 31.0), enabled_notifications=Record(part=30.0, total=120.0)
        )
        dialog = self.admin(1)
        shown = []
        dialog.show_stats = lambda rows: shown.append(dialog.stats_text(rows))
        dialog.on_stats(None)
        self.assertTrue(pump(lambda: shown))
        lines = shown[0].splitlines()
        self.assertEqual(lines[0], self.text(c.STATS_ROW_FORMAT_KEY).format(
            label=self.text("STATS_LABEL_followers"), current=1200, previous=1100
        ))
        self.assertIn("640", lines[1])
        self.assertEqual(lines[-1], self.text(c.STATS_PERCENT_FORMAT_KEY).format(
            label=self.text("STATS_LABEL_enabled_notifications"), percent=25.0
        ))

    def test_chat_without_statistics_says_so(self):
        dialog = self.admin(0)
        dialog.on_stats(None)
        self.assertTrue(pump(lambda: self.boxes == [self.text(c.ERR_STATS_UNAVAILABLE_KEY)]))

    def test_deleting_for_everyone_needs_the_name_typed_out(self):
        dialog = self.admin(1)
        cancelled = self.text(c.MSG_DELETE_CHAT_CANCELLED_KEY)
        self.box_answer = wx.NO
        dialog.on_delete(None)
        self.box_answer = wx.YES
        FakeChooser.values = ["mynews"]
        dialog.on_delete(None)
        pump(timeout=0.2)
        self.assertEqual(self.spoken.count(cancelled), 2)
        self.assertEqual(self.requests("DeleteChannelRequest"), [])

        FakeChooser.values = ["MyNews"]
        dialog.on_delete(None)
        self.assertTrue(pump(lambda: dialog.deleted))
        self.assertEqual(len(self.requests("DeleteChannelRequest")), 1)

    def test_ownership_cannot_move_without_two_step_verification(self):
        dialog = self.admin(0)
        dialog.on_transfer(None)
        self.assertTrue(pump(lambda: self.boxes == [self.text(c.ERR_TRANSFER_NEEDS_PASSWORD_KEY)]))
        self.assertEqual(self.requests("EditChatCreatorRequest"), [])


class MemberAdminTest(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.dialog = ChatInfoDialog(self.frame, self.i18n, self.manager, self.frame.all_dialogs[0])
        self.addCleanup(self.dialog.Destroy)
        self.dialog.PopupMenu = self.frame.PopupMenu
        self.assertTrue(pump(lambda: len(self.dialog.members) == len(MEMBERS)), "members did not load")

    def member(self, name):
        return next(member for member in self.dialog.members if member["name"] == name)

    def test_member_is_limited_to_what_stays_ticked_for_as_long_as_chosen(self):
        FakeChooser.selections = [c.MEMBER_PERMISSIONS.index("send_messages")]
        FakeChooser.selection = 2
        self.dialog.manage_member(self.member("Zed"), c.MEMBER_ACTION_RESTRICT)
        self.assertTrue(pump(lambda: self.calls("permissions")))
        target, allowed = self.calls("permissions")[0][1:]
        self.assertEqual(target, 12)
        self.assertEqual(allowed, {name: name == "send_messages" for name in c.MEMBER_PERMISSIONS})
        self.assertEqual(self.calls("until"), [("until", 12, datetime.timedelta(days=1))])

    def test_new_title_keeps_every_right_the_admin_has(self):
        mona = self.member("Mona")
        self.assertEqual(mona["title"], "Helper")
        FakeChooser.values = ["Night shift"]
        self.dialog.manage_member(mona, c.MEMBER_ACTION_TITLE)
        self.assertTrue(pump(lambda: self.requests("EditAdminRequest")))
        request = self.requests("EditAdminRequest")[0]
        self.assertEqual(request.rank, "Night shift")
        rights = request.admin_rights
        # Including one this app has no tick box for.
        self.assertTrue(rights.delete_messages and rights.ban_users and rights.other)
        self.assertFalse(rights.add_admins)

    def test_changing_rights_keeps_the_title_and_the_rights_not_shown(self):
        offered = [name for name in c.ADMIN_RIGHTS if name not in c.CHANNEL_ONLY_RIGHTS]
        FakeChooser.selections = [offered.index("pin_messages")]
        self.dialog.manage_member(self.member("Mona"), c.MEMBER_ACTION_PROMOTE)
        self.assertTrue(pump(lambda: self.requests("EditAdminRequest")))
        request = self.requests("EditAdminRequest")[0]
        self.assertEqual(request.rank, "Helper")
        self.assertTrue(request.admin_rights.pin_messages and request.admin_rights.other)
        self.assertFalse(request.admin_rights.ban_users)

    def test_new_admin_is_not_offered_anonymity_or_appointing_admins_by_default(self):
        self.dialog.manage_member(self.member("Zed"), c.MEMBER_ACTION_PROMOTE)
        pump(timeout=0.1)
        offered = [name for name in c.ADMIN_RIGHTS if name not in c.CHANNEL_ONLY_RIGHTS]
        self.assertIn(self.text(c.ADMIN_RIGHT_KEY_PREFIX + "anonymous"), FakeChooser.last_choices)
        self.assertEqual(len(FakeChooser.last_choices), len(offered))

    def test_all_messages_of_a_member_are_deleted_after_a_yes(self):
        self.box_answer = wx.NO
        self.dialog.manage_member(self.member("Zed"), c.MEMBER_ACTION_DELETE_MESSAGES)
        pump(timeout=0.2)
        self.assertEqual(self.requests("DeleteParticipantHistoryRequest"), [])
        self.box_answer = wx.YES
        self.dialog.manage_member(self.member("Zed"), c.MEMBER_ACTION_DELETE_MESSAGES)
        self.assertTrue(pump(lambda: self.requests("DeleteParticipantHistoryRequest")))
        self.assertEqual(telegram_client.get_peer_id(self.requests("DeleteParticipantHistoryRequest")[0].participant), 12)


class PostNumbersTest(AdminTestCase):
    def test_post_reports_how_many_saw_it_and_passed_it_on(self):
        shown = []
        self.frame.show_text = lambda title_key, text: shown.append(text)
        self.open_chat(1)
        self.frame.messages_list.SetSelection(0)
        self.frame.on_audience_menu(None)
        self.assertTrue(pump(lambda: shown))
        lines = shown[0].splitlines()
        self.assertEqual(lines[0], self.text(c.AUDIENCE_VIEWS_FORMAT_KEY).format(count=950))
        self.assertEqual(lines[1], self.text(c.AUDIENCE_FORWARDS_FORMAT_KEY).format(count=12))
        # A post has viewers, not readers by name: no line apologising for a list that does not exist.
        self.assertNotIn(self.text(c.AUDIENCE_READERS_UNKNOWN_KEY), shown[0])
