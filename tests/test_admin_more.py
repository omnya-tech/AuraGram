"""The rest of running a chat: topics, the discussion group, chosen reactions, limited invite links, writing as a channel."""
import datetime

import wx
from telethon.tl import types

import core.constants as c
import core.telegram_client as telegram_client
from tests.harness import (
    NOW, FakeChooser, FakeTelegramClient, Record, WindowTestCase, make_channel, make_user, pump
)
from ui.chat_admin_dialog import ChatAdminDialog
from ui.invite_links_dialog import InviteLinksDialog

FORUM = types.Channel(
    id=8, title="Builders", photo=None, date=NOW, megagroup=True, forum=True, creator=True, access_hash=1
)
PLAIN_GROUP = make_channel(4, "MyGroup", group=True, creator=True)
MY_CHANNEL = make_channel(5, "MyNews", creator=True)
ME = make_user(10, "Me", is_self=True)
TALK = make_channel(20, "Talk about news", group=True, creator=True)


class MoreAdminTest(WindowTestCase):
    chats = [(FORUM, 0, False), (PLAIN_GROUP, 0, False), (MY_CHANNEL, 0, False)]

    def admin(self, index, answers=()):
        chat = self.frame.all_dialogs[index]
        dialog = ChatAdminDialog(self.frame, self.i18n, self.manager, chat["id"], chat["title"])
        self.addCleanup(dialog.Destroy)
        self.assertTrue(pump(lambda: dialog.settings is not None), "admin settings did not load")
        # Each list the dialog asks about is answered in turn, and what it offered is kept.
        self.offered = []
        answers = list(answers)
        dialog.choose = lambda prompt, choices: (self.offered.append(choices), answers.pop(0))[1]
        return dialog

    def requests(self, name):
        return [call[1] for call in self.calls(name)]

    def saved(self, key):
        return pump(lambda: self.spoken[-1:] == [self.text(key)])

    def set_topics(self):
        FakeTelegramClient.topics = [
            Record(id=1, title="General", closed=False), Record(id=30, title="Materials", closed=True),
        ]

    def test_topics_are_managed_only_where_the_group_has_them(self):
        self.assertTrue(self.admin(0).buttons[c.BTN_MANAGE_TOPICS_KEY].IsEnabled())
        self.assertFalse(self.admin(1).buttons[c.BTN_MANAGE_TOPICS_KEY].IsEnabled())

    def test_new_topic(self):
        self.set_topics()
        FakeChooser.values = ["Tools"]
        self.admin(0, answers=[0]).on_topics(None)
        self.assertTrue(self.saved(c.MSG_TOPIC_SAVED_KEY))
        self.assertEqual(self.requests("CreateForumTopicRequest")[0].title, "Tools")
        self.assertEqual(self.offered[0], [
            self.text(c.TOPIC_NEW_KEY), "General", self.text(c.TOPIC_CLOSED_FORMAT_KEY).format(title="Materials"),
        ])

    def test_closed_topic_can_be_reopened_and_the_first_topic_never_deleted(self):
        self.set_topics()
        self.admin(0, answers=[2, 1]).on_topics(None)
        self.assertTrue(self.saved(c.MSG_TOPIC_SAVED_KEY))
        request = self.requests("EditForumTopicRequest")[0]
        self.assertEqual((request.topic_id, request.closed, request.title), (30, False, None))
        self.assertEqual(self.offered[1], [
            self.text(c.TOPIC_RENAME_KEY), self.text(c.TOPIC_REOPEN_KEY), self.text(c.TOPIC_PIN_KEY),
            self.text(c.TOPIC_DELETE_KEY),
        ])

        self.admin(0, answers=[1, 1]).on_topics(None)
        self.assertTrue(pump(lambda: len(self.requests("EditForumTopicRequest")) == 2))
        self.assertTrue(self.requests("EditForumTopicRequest")[1].closed)
        self.assertEqual(self.offered[1], [
            self.text(c.TOPIC_RENAME_KEY), self.text(c.TOPIC_CLOSE_KEY), self.text(c.TOPIC_PIN_KEY),
        ])

    def test_topic_is_renamed_or_deleted_after_a_yes(self):
        self.set_topics()
        FakeChooser.values = ["Bricks and wood"]
        self.admin(0, answers=[2, 0]).on_topics(None)
        self.assertTrue(self.saved(c.MSG_TOPIC_SAVED_KEY))
        self.assertEqual(self.requests("EditForumTopicRequest")[0].title, "Bricks and wood")

        self.box_answer = wx.NO
        self.admin(0, answers=[2, 3]).on_topics(None)
        pump(timeout=0.3)
        self.assertEqual(self.requests("DeleteTopicHistoryRequest"), [])
        self.box_answer = wx.YES
        self.admin(0, answers=[2, 3]).on_topics(None)
        self.assertTrue(pump(lambda: self.requests("DeleteTopicHistoryRequest")))
        self.assertEqual(self.requests("DeleteTopicHistoryRequest")[0].top_msg_id, 30)

    def test_topic_is_pinned_and_a_pinned_one_offers_to_be_unpinned(self):
        FakeTelegramClient.topics = [
            Record(id=1, title="General", closed=False), Record(id=30, title="Materials", closed=False, pinned=True),
        ]
        self.admin(0, answers=[1, 2]).on_topics(None)
        self.assertTrue(self.saved(c.MSG_TOPIC_SAVED_KEY))
        request = self.requests("UpdatePinnedForumTopicRequest")[0]
        self.assertEqual((request.topic_id, request.pinned), (1, True))
        self.assertEqual(self.offered[0][2], self.text(c.TOPIC_PINNED_FORMAT_KEY).format(title="Materials"))

        self.admin(0, answers=[2, 2]).on_topics(None)
        self.assertTrue(pump(lambda: len(self.requests("UpdatePinnedForumTopicRequest")) == 2))
        self.assertFalse(self.requests("UpdatePinnedForumTopicRequest")[1].pinned)
        self.assertIn(self.text(c.TOPIC_UNPIN_KEY), self.offered[1])

    def test_channel_gets_a_group_for_its_comments_or_loses_it(self):
        FakeTelegramClient.discussion_groups = [TALK]
        dialog = self.admin(2, answers=[1])
        self.assertTrue(dialog.buttons[c.BTN_DISCUSSION_KEY].IsEnabled())
        dialog.on_discussion(None)
        self.assertTrue(self.saved(c.MSG_DISCUSSION_SAVED_KEY))
        self.assertEqual(
            telegram_client.get_peer_id(self.requests("SetDiscussionGroupRequest")[0].group),
            telegram_client.get_peer_id(TALK)
        )
        self.assertEqual(self.offered[0], [self.text(c.DISCUSSION_NONE_KEY), "Talk about news"])

        self.admin(2, answers=[0]).on_discussion(None)
        self.assertTrue(pump(lambda: len(self.requests("SetDiscussionGroupRequest")) == 2))
        self.assertIsInstance(self.requests("SetDiscussionGroupRequest")[1].group, types.InputChannelEmpty)
        # A group has no comments to host.
        self.assertFalse(self.admin(1).buttons[c.BTN_DISCUSSION_KEY].IsEnabled())

    def test_only_the_chosen_reactions_are_allowed(self):
        FakeTelegramClient.full_chat = dict(
            available_reactions=types.ChatReactionsSome([types.ReactionEmoji(emoticon=c.REACTION_EMOJIS[6])])
        )
        dialog = self.admin(2)
        self.assertEqual(dialog.settings["reactions"], [c.REACTION_EMOJIS[6]])
        FakeChooser.selections = [0, 1]
        dialog.on_reactions(None)
        self.assertTrue(pump(lambda: self.requests("SetChatAvailableReactionsRequest")))
        allowed = self.requests("SetChatAvailableReactionsRequest")[0].available_reactions
        self.assertEqual([reaction.emoticon for reaction in allowed.reactions], list(c.REACTION_EMOJIS[:2]))

    def links(self):
        chat = self.frame.all_dialogs[1]
        dialog = InviteLinksDialog(self.frame, self.i18n, self.manager, chat["id"], chat["title"])
        self.addCleanup(dialog.Destroy)
        pump(timeout=0.2)
        return dialog

    def test_invite_link_can_expire_and_stop_after_a_number_of_people(self):
        dialog = self.links()
        FakeChooser.values = ["Open day", "25"]
        FakeChooser.selection = 2
        self.box_answer = wx.NO
        dialog.on_new(None)
        self.assertTrue(pump(lambda: len(dialog.links) == 1))
        request = self.requests("ExportChatInviteRequest")[0]
        self.assertEqual(request.usage_limit, 25)
        remaining = request.expire_date - datetime.datetime.now(datetime.timezone.utc)
        self.assertAlmostEqual(remaining.total_seconds(), 24 * 60 * 60, delta=60)
        row = dialog.links_list.GetString(0)
        self.assertIn(self.text(c.INVITE_LINK_LIMIT_FORMAT_KEY).format(limit=25), row)
        self.assertIn(self.text(c.INVITE_LINK_EXPIRES_FORMAT_KEY).format(date="")[:5], row)

    def test_limit_that_is_not_a_number_creates_nothing(self):
        dialog = self.links()
        FakeChooser.values = ["Open day", "many"]
        FakeChooser.selection = 0
        self.box_answer = wx.NO
        dialog.on_new(None)
        pump(timeout=0.2)
        self.assertEqual(self.boxes[-1], self.text(c.ERR_LINK_LIMIT_KEY))
        self.assertEqual(self.requests("ExportChatInviteRequest"), [])

    def test_writing_as_the_channel_in_a_group(self):
        self.open_chat(1)
        FakeTelegramClient.send_as = [ME]
        self.frame.on_send_as_menu(None)
        self.assertTrue(self.saved(c.MSG_NO_SEND_AS_KEY))

        FakeTelegramClient.send_as = [MY_CHANNEL, ME]
        FakeChooser.selection = 0
        self.frame.on_send_as_menu(None)
        self.assertTrue(pump(lambda: self.requests("SaveDefaultSendAsRequest")))
        self.assertEqual(
            telegram_client.get_peer_id(self.requests("SaveDefaultSendAsRequest")[0].send_as),
            telegram_client.get_peer_id(MY_CHANNEL)
        )
        self.assertTrue(pump(lambda: "MyNews" in self.spoken[-1]))
