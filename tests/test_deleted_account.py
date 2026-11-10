"""A deleted account is named as Telegram's apps name it, wherever a name is shown, not left blank."""
import unittest

from telethon.tl import types

import core.constants as c
from core import tg_shared
from core.i18n import I18NManager
from tests.harness import WindowTestCase, make_message, make_user

GONE = types.User(id=8, deleted=True, access_hash=1)
ALI = make_user(1, "Ali")


class DisplayNameTest(unittest.TestCase):
    def tearDown(self):
        tg_shared.set_language(c.DEFAULT_LANG)

    def test_a_deleted_account_is_named_so_in_the_interface_language(self):
        for language in ("ar", "en"):
            tg_shared.set_language(language)
            self.assertEqual(tg_shared.display_name(GONE), I18NManager(language).get_string(c.DELETED_ACCOUNT_KEY))
        # Anyone else keeps their own name.
        self.assertEqual(tg_shared.display_name(ALI), "Ali")


class DeletedAccountWindowTest(WindowTestCase):
    chats = [(GONE, 0, False), (ALI, 0, False)]
    history = {8: [make_message(1, "hello", sender=GONE)], 1: [make_message(1, "hi", sender=GONE)]}

    def test_its_chat_and_its_messages_say_deleted_account(self):
        deleted = self.text(c.DELETED_ACCOUNT_KEY)
        self.assertEqual(self.frame.dialogs[0]["title"], deleted)
        self.assertTrue(self.frame.dialogs_list.GetString(0).startswith(deleted))
        self.open_chat(1)
        self.assertTrue(self.frame.messages_list.GetString(0).startswith(deleted + ":"))
