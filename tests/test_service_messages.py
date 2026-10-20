"""Messages from Telegram itself (who joined, who left, what was pinned) are said in words."""
import unittest

from telethon.tl import types

import core.constants as c
from core.telegram_client import TelegramManager
from tests.harness import Record, WindowTestCase, make_channel, make_message, make_user

MOHAMED = make_user(5, "Mohamed Ali")
SARA = make_user(6, "Sara")
AHMED = make_user(7, "Ahmed")
TEAM = make_channel(31, "Omnya Community", group=True)


def service(action, sender=MOHAMED, entities=()):
    return Record(action=action, action_entities=list(entities)), sender


class DescribeTest(unittest.TestCase):
    def describe(self, action, sender=MOHAMED, entities=()):
        message, sender = service(action, sender, entities)
        return TelegramManager._describe_service(None, message, sender)

    def test_joining_and_adding_and_leaving(self):
        self.assertEqual(self.describe(types.MessageActionChatAddUser(users=[5]), entities=[MOHAMED]),
                         (c.SERVICE_JOINED_KEY, {}))
        self.assertEqual(self.describe(types.MessageActionChatAddUser(users=[6, 7]), entities=[SARA, AHMED]),
                         (c.SERVICE_ADDED_FORMAT_KEY, {"names": ["Sara", "Ahmed"]}))
        self.assertEqual(self.describe(types.MessageActionChatDeleteUser(user_id=5), entities=[MOHAMED]),
                         (c.SERVICE_LEFT_KEY, {}))
        self.assertEqual(self.describe(types.MessageActionChatDeleteUser(user_id=6), entities=[SARA]),
                         (c.SERVICE_REMOVED_FORMAT_KEY, {"names": ["Sara"]}))

    def test_other_kinds_and_those_not_known(self):
        self.assertEqual(self.describe(types.MessageActionChatJoinedByLink(inviter_id=1)),
                         ("SERVICE_JOINED_BY_LINK", {"title": ""}))
        self.assertEqual(self.describe(types.MessageActionChatEditTitle(title="New name")),
                         ("SERVICE_EDIT_TITLE_FORMAT", {"title": "New name"}))
        self.assertEqual(self.describe(types.MessageActionPinMessage())[0], "SERVICE_PIN")
        self.assertEqual(self.describe(types.MessageActionGroupCall(call=None))[0], c.SERVICE_CALL_STARTED_KEY)
        self.assertEqual(self.describe(types.MessageActionGroupCall(call=None, duration=60))[0], c.SERVICE_CALL_ENDED_KEY)
        self.assertEqual(self.describe(types.MessageActionEmpty()), (c.MEDIA_SERVICE_KEY, {}))
        self.assertIsNone(TelegramManager._describe_service(None, Record(action=None), MOHAMED))

    def test_a_new_large_group_is_said_to_be_a_group(self):
        # Telegram makes both with the same action; the chat says which it is.
        made = types.MessageActionChannelCreate(title="omnya team")
        group = Record(action=made, action_entities=[], chat=make_channel(40, "omnya team", group=True))
        channel = Record(
            action=types.MessageActionChannelCreate(title="omnya news"), action_entities=[],
            chat=make_channel(41, "omnya news")
        )
        self.assertEqual(TelegramManager._describe_service(None, group, MOHAMED),
                         (c.SERVICE_GROUP_CREATE_FORMAT_KEY, {"title": "omnya team"}))
        self.assertEqual(TelegramManager._describe_service(None, channel, MOHAMED),
                         ("SERVICE_CHANNEL_CREATE_FORMAT", {"title": "omnya news"}))

    def test_what_telegram_says_happened_carries_no_read_mark(self):
        manager = TelegramManager.__new__(TelegramManager)
        manager.read_outbox = {40: 99}
        made = Record(id=1, out=True, chat_id=40, action=types.MessageActionChannelCreate(title="x"))
        written = Record(id=2, out=True, chat_id=40, action=None)
        self.assertIsNone(manager._is_read(made))
        self.assertTrue(manager._is_read(written))

    def test_every_kind_has_its_words(self):
        from core.i18n import I18NManager
        keys = set(c.SERVICE_KEYS.values()) | {
            c.SERVICE_JOINED_KEY, c.SERVICE_ADDED_FORMAT_KEY, c.SERVICE_LEFT_KEY, c.SERVICE_REMOVED_FORMAT_KEY,
            c.SERVICE_CALL_STARTED_KEY, c.SERVICE_CALL_ENDED_KEY, c.SERVICE_NAMES_SEPARATOR_KEY,
            c.SERVICE_GROUP_CREATE_FORMAT_KEY,
        }
        for language in c.LANGUAGES:
            strings = I18NManager(language).strings
            self.assertEqual([key for key in keys if key not in strings], [], language)


class ServiceRowTest(WindowTestCase):
    chats = [(TEAM, 0, False)]
    history = {-1000000000031: [
        make_message(1, sender=MOHAMED, action=types.MessageActionChatAddUser(users=[6, 7]), action_entities=[SARA, AHMED]),
        make_message(2, sender=MOHAMED, action=types.MessageActionChatJoinedByLink(inviter_id=1), action_entities=[]),
    ]}

    def test_the_row_says_who_did_what(self):
        self.open_chat(0)
        rows = [self.frame.messages_list.GetString(index) for index in range(2)]
        added = self.text(c.SERVICE_ADDED_FORMAT_KEY).format(
            names=self.text(c.SERVICE_NAMES_SEPARATOR_KEY).join(["Sara", "Ahmed"])
        )
        self.assertIn("Mohamed Ali: " + added, rows[0])
        self.assertIn("Mohamed Ali: " + self.text("SERVICE_JOINED_BY_LINK"), rows[1])
        self.assertNotIn(self.text(c.MEDIA_SERVICE_KEY), rows[0])

    def test_said_from_outside_the_group_it_names_who_did_it(self):
        joined = self.text("SERVICE_JOINED_BY_LINK")
        self.frame.report_message("Omnya Community", {
            "service": ("SERVICE_JOINED_BY_LINK", {"title": ""}), "sender": "Mohamed Ali", "text": "", "detail": "",
            "poll": None, "media": c.MEDIA_SERVICE_KEY, "file": None,
        })
        self.assertEqual(self.spoken[-1], "Omnya Community: Mohamed Ali: " + joined)
