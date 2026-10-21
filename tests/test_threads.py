"""Conversations inside a conversation: comments under channel posts and topics of forum groups,
and the list of who read or reacted to a message."""
import asyncio
from unittest import mock

import wx
from telethon.tl import types

import core.constants as c
import core.telegram_client as telegram_client
from tests.harness import (
    NOW, FakeChooser, FakeTelegramClient, Record, WindowTestCase, make_message, make_user, pump
)

ALI = make_user(1, "Ali")
MONA = make_user(5, "Mona")
# A channel this account only reads, and a group split into topics.
NEWS = types.Channel(id=3, title="News", photo=None, date=NOW, broadcast=True, access_hash=1)
FORUM = types.Channel(id=8, title="Builders", photo=None, date=NOW, megagroup=True, forum=True, access_hash=1)
# Where the comments on News are really written.
TALK = types.Channel(id=9, title="News talk", photo=None, date=NOW, megagroup=True, access_hash=1)
NEWS_ID = telegram_client.get_peer_id(NEWS)
TALK_ID = telegram_client.get_peer_id(TALK)
# The post's twin in the discussion group, which every comment answers.
TWIN = 77
FORUM_ID = telegram_client.get_peer_id(FORUM)


class ThreadsTest(WindowTestCase):
    chats = [(NEWS, 0, False), (FORUM, 0, False), (ALI, 0, False)]
    history = {
        NEWS_ID: [
            make_message(10, "big announcement", replies=Record(comments=True, replies=2)),
            make_message(11, "comments are off here"),
        ],
        FORUM_ID: [make_message(20, "mixed talk", sender=ALI)],
        1: [make_message(1, "hi", sender=ALI), make_message(2, "mine", outgoing=True)],
    }

    def setUp(self):
        super().setUp()
        FakeTelegramClient.threads = {
            (TALK_ID, TWIN): [
                make_message(501, "first!", sender=ALI, reply_to_msg_id=TWIN),
                make_message(502, "agreed", sender=MONA, reply_to_msg_id=TWIN, photo=True),
            ],
            (FORUM_ID, 30): [make_message(31, "use bricks", sender=ALI)],
            (FORUM_ID, 1): [make_message(21, "welcome", sender=ALI)],
        }
        FakeTelegramClient.discussions = {(NEWS_ID, 10): (TALK, TWIN)}
        FakeTelegramClient.topics = [
            Record(id=1, title="General", unread_count=0),
            Record(id=30, title="Materials", unread_count=4),
            Record(id=40),  # a deleted topic: an id and nothing else
        ]

    def rows(self):
        return [self.frame.messages_list.GetString(index) for index in range(self.frame.messages_list.GetCount())]

    def open_comments(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(0)
        self.frame.on_activate_message(None)
        self.assertTrue(pump(lambda: self.frame.message_view == c.MESSAGE_VIEW_COMMENTS and len(self.frame.messages) == 2))

    def open_topic(self, choice):
        self.open_chat(1)
        FakeChooser.selection = choice
        self.frame.on_topics_menu(None)
        self.assertTrue(pump(lambda: self.frame.message_view == c.MESSAGE_VIEW_TOPIC))

    def test_post_tells_its_comment_count_and_enter_opens_them(self):
        self.open_chat(0)
        self.assertIn(self.text(c.COMMENTS_FORMAT_KEY).format(text="", count=2), self.rows()[0])
        self.assertNotIn(self.text(c.COMMENTS_FORMAT_KEY).format(text="", count=0)[:6], self.rows()[1])
        self.open_comments()
        self.assertEqual([message["text"] for message in self.frame.messages], ["first!", "agreed"])
        self.assertIn("big announcement", self.frame.messages_list.GetName())
        self.assertIn("big announcement", self.spoken[-1])

    def test_subscriber_can_write_a_comment_though_not_a_post(self):
        self.open_chat(0)
        self.assertFalse(self.frame.message_input.IsEnabled())
        self.open_comments()
        self.assertTrue(self.frame.message_input.IsEnabled())
        self.frame.message_input.SetValue("well said")
        self.frame.on_send_message(None)
        # A comment is an answer to the post's twin in the discussion group.
        self.assertTrue(pump(lambda: self.calls("send") == [("send", TALK_ID, "well said", TWIN, None)]))
        # Still in the comments, with the new one at the end.
        self.assertTrue(pump(lambda: len(self.frame.messages) == 3 and self.frame.message_view == c.MESSAGE_VIEW_COMMENTS))

    def test_a_comment_can_be_answered_reacted_to_and_opened_like_any_message(self):
        self.open_comments()
        self.frame.messages_list.SetSelection(0)
        self.frame.on_message_context_menu(self.context_event(self.frame.messages_list))
        for key in (c.CONTEXT_REACT_KEY, c.CONTEXT_REPLY_KEY, c.CONTEXT_COPY_KEY):
            self.assertIn(self.text(key), self.menu_labels)
        # A guest in the discussion group pins nothing and deletes nobody else's words.
        for key in (c.CONTEXT_PIN_KEY, c.CONTEXT_DELETE_KEY):
            self.assertNotIn(self.text(key), self.menu_labels)

        self.frame.set_compose(reply_to=self.frame.messages[0])
        self.frame.message_input.SetValue("why first?")
        self.frame.on_send_message(None)
        self.assertTrue(pump(lambda: self.calls("send") == [("send", TALK_ID, "why first?", 501, None)]))

        FakeChooser.selection = 0
        self.frame.messages_list.SetSelection(0)
        self.frame.on_react_menu(None)
        self.assertTrue(pump(lambda: self.calls("SendReactionRequest")))
        reaction = self.calls("SendReactionRequest")[0][1]
        self.assertEqual((telegram_client.get_peer_id(reaction.peer), reaction.msg_id), (TALK_ID, 501))

    def test_attachment_of_a_comment_comes_from_the_discussion_group(self):
        self.open_comments()
        self.frame.messages_list.SetSelection(1)
        with mock.patch.object(wx, "LaunchDefaultApplication"):
            self.frame.on_activate_message(None)
            self.assertTrue(pump(lambda: (TALK_ID, 502) in self.frame.downloaded))
        self.assertEqual(self.calls("download")[0][1], 502)

    def test_files_go_under_the_post_too(self):
        self.open_comments()
        self.assertTrue(self.frame.can_send_now())
        FakeChooser.values = [""]
        self.frame.send_paths(["proof.pdf"])
        self.assertTrue(pump(lambda: len(self.calls("send_file")) == 1))
        self.assertEqual(self.calls("send_file")[0][1], TALK_ID)
        self.assertEqual(self.calls("send_file")[0][5], TWIN)

    def test_comment_arriving_while_the_post_is_open_shows_up(self):
        self.open_comments()

        def arrives(chat, message):
            async def value(result):
                return result
            event = Record(
                chat_id=telegram_client.get_peer_id(chat), message=message,
                get_sender=lambda: value(MONA), get_chat=lambda: value(chat), get_input_chat=lambda: value(None)
            )
            asyncio.run_coroutine_threadsafe(self.manager.client.handlers["NewMessage"](event), self.manager.loop)

        arrives(TALK, make_message(503, "me too", sender=MONA, reply_to_msg_id=TWIN))
        self.assertTrue(pump(lambda: [m["id"] for m in self.frame.messages] == [501, 502, 503]))
        # Something said in the same group under another post is not part of this conversation.
        arrives(TALK, make_message(504, "elsewhere", sender=MONA, reply_to_msg_id=78))
        # Nor is a new post in the channel itself.
        arrives(NEWS, make_message(12, "another post"))
        pump(timeout=0.3)
        self.assertEqual([m["id"] for m in self.frame.messages], [501, 502, 503])

    def test_escape_returns_to_the_channel_and_locks_writing_again(self):
        self.open_comments()
        self.assertTrue(self.frame.on_escape())
        self.assertTrue(pump(lambda: [m["text"] for m in self.frame.messages] == ["big announcement", "comments are off here"]))
        self.assertIsNone(self.frame.message_view)
        self.assertIsNone(self.frame.thread)
        self.assertFalse(self.frame.message_input.IsEnabled())
        self.assertEqual(
            self.frame.messages_list.GetName(), self.text(c.MESSAGES_OF_LABEL_FORMAT_KEY).format(chat="News")
        )

    def test_message_that_takes_no_comments_says_so(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(1)
        self.frame.on_comments_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NO_COMMENTS_KEY))

    def test_topics_are_listed_with_unread_counts_and_deleted_ones_left_out(self):
        self.open_topic(1)
        self.assertEqual(
            FakeChooser.last_choices,
            ["General", self.text(c.TOPIC_CHOICE_FORMAT_KEY).format(title="Materials", unread=4)]
        )
        self.assertTrue(pump(lambda: [m["text"] for m in self.frame.messages] == ["use bricks"]))

    def test_message_written_in_a_topic_lands_in_that_topic(self):
        self.open_topic(1)
        self.frame.message_input.SetValue("or wood")
        self.frame.on_send_message(None)
        self.assertTrue(pump(lambda: self.calls("send") == [("send", FORUM_ID, "or wood", 30, None)]))
        self.assertTrue(pump(lambda: len(self.frame.messages) == 2 and self.frame.message_view == c.MESSAGE_VIEW_TOPIC))
        # A reply inside the topic answers that message; it needs no pointer to the topic.
        self.frame.set_compose(reply_to=self.frame.messages[0])
        self.frame.message_input.SetValue("true")
        self.frame.on_send_message(None)
        self.assertTrue(pump(lambda: len(self.calls("send")) == 2))
        self.assertEqual(self.calls("send")[1][3], 31)

    def test_general_topic_takes_plain_messages(self):
        self.open_topic(0)
        self.frame.message_input.SetValue("hello all")
        self.frame.on_send_message(None)
        self.assertTrue(pump(lambda: self.calls("send") == [("send", FORUM_ID, "hello all", None, None)]))

    def test_files_polls_and_places_all_land_in_the_open_topic(self):
        self.open_topic(1)
        FakeChooser.values = [""]
        self.frame.send_paths(["plan.pdf"])
        self.assertTrue(pump(lambda: len(self.calls("send_file")) == 1))
        self.assertEqual(self.calls("send_file")[0][5], 30)

        # Each send reloads the topic; the next one waits for that.
        self.assertTrue(pump(lambda: not self.frame.is_busy))
        FakeChooser.values = ["Brick or wood?", "Brick\nWood"]
        self.frame.on_new_poll_menu(None)
        self.assertTrue(pump(lambda: self.calls("send")))
        self.assertEqual(self.calls("send")[0][3], 30)

        self.assertTrue(pump(lambda: not self.frame.is_busy))
        FakeChooser.values = ["30.0, 31.0"]
        self.frame.on_send_location_menu(None)
        self.assertTrue(pump(lambda: len(self.calls("send_file")) == 2))
        self.assertEqual(self.calls("send_file")[1][5], 30)

    def test_where_things_go_depends_on_what_is_open(self):
        self.open_topic(1)
        self.assertEqual((self.frame.peer(FORUM_ID), self.frame.thread_root()), (FORUM_ID, 30))
        self.open_comments()
        self.assertEqual((self.frame.peer(NEWS_ID), self.frame.thread_root()), (TALK_ID, TWIN))
        # Another chat is not affected by what is open in this one.
        self.assertEqual(self.frame.peer(1), 1)

    def test_ordinary_group_has_no_topics(self):
        self.open_chat(2)
        self.frame.on_topics_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NOT_FORUM_KEY))

    def shown_audience(self):
        shown = []
        self.frame.show_text = lambda title_key, text: shown.append(text)
        self.open_chat(2)
        self.frame.messages_list.SetSelection(1)
        self.frame.on_audience_menu(None)
        self.assertTrue(pump(lambda: shown))
        return shown[0]

    def test_audience_names_readers_and_reactions(self):
        FakeTelegramClient.public["mona"] = MONA
        FakeTelegramClient.audience = (
            Record(users=[ALI], chats=[], reactions=[
                Record(peer_id=types.PeerUser(1), reaction=types.ReactionEmoji(emoticon="👍")),
            ]),
            [Record(user_id=types.PeerUser(5)), Record(user_id=types.PeerUser(999))],
        )
        text = self.shown_audience()
        self.assertIn(self.text(c.AUDIENCE_READERS_FORMAT_KEY).format(names="Mona"), text)
        self.assertIn(self.text(c.AUDIENCE_REACTION_FORMAT_KEY).format(name="Ali", emoji="👍"), text)

    def test_audience_says_when_nobody_read_or_reacted(self):
        FakeTelegramClient.audience = (Record(users=[], chats=[], reactions=[]), [])
        text = self.shown_audience()
        self.assertIn(self.text(c.AUDIENCE_NO_READERS_KEY), text)
        self.assertIn(self.text(c.AUDIENCE_NO_REACTIONS_KEY), text)
