"""What Telegram's own apps show around a conversation: read marks, who is online or typing, bot buttons."""
import asyncio
import datetime
from unittest import mock

import wx
from telethon.tl import types

import core.constants as c
import core.settings as s
import ui.message_actions
from tests.harness import FakeChooser, FakeTelegramClient, Record, WindowTestCase, make_message, make_user, pump

ALI = make_user(1, "Ali")
ALI.status = types.UserStatusOffline(was_online=datetime.datetime(2026, 1, 2, 3, 4, tzinfo=datetime.timezone.utc))
BOT = make_user(7, "Helper", bot=True)


class Button:
    """A bot's button: remembers being pressed, and answers like a bot would."""

    def __init__(self, text, url=None, answer=None):
        self.text = text
        self.url = url
        self.answer = answer
        self.presses = 0

    async def click(self):
        self.presses += 1
        return types.messages.BotCallbackAnswer(cache_time=0, message=self.answer)


YES = Button("Yes", answer="Saved")
SITE = Button("Site", url="https://example.org/page")


class ConversationSignalsTest(WindowTestCase):
    chats = [(ALI, 0, False), (BOT, 0, False)]
    history = {
        1: [
            make_message(1, "hello", sender=ALI, chat_id=1),
            make_message(2, "seen by now", outgoing=True, chat_id=1),
            make_message(3, "still waiting", outgoing=True, chat_id=1),
        ],
        7: [make_message(1, "Keep it?", sender=BOT, chat_id=7, buttons=[[YES, SITE]])],
    }

    def fire(self, handler, event):
        asyncio.run_coroutine_threadsafe(self.manager.client.handlers[handler](event), self.manager.loop)

    def row(self, index):
        return self.frame.messages_list.GetString(index)

    def test_my_messages_say_whether_they_were_read(self):
        FakeTelegramClient.read_outbox = 2
        self.open_chat(0)
        read, unread = self.text(c.MESSAGE_READ_FORMAT_KEY).format(text=""), self.text(c.MESSAGE_UNREAD_FORMAT_KEY).format(text="")
        self.assertTrue(self.row(1).endswith(read))
        self.assertTrue(self.row(2).endswith(unread))
        # Somebody else's message carries no mark at all.
        self.assertFalse(self.row(0).endswith(read) or self.row(0).endswith(unread))

        self.fire("MessageRead", Record(chat_id=1, max_id=3))
        self.assertTrue(pump(lambda: self.row(2).endswith(read)))

    def test_no_marks_where_telegram_does_not_say(self):
        self.open_chat(0)
        self.assertEqual([message["read"] for message in self.frame.messages], [None, None, None])

    def test_last_seen_is_part_of_the_name_of_the_message_list(self):
        self.open_chat(0)
        label = self.frame.messages_list.GetName()
        self.assertIn("Ali", label)
        self.assertIn(self.text(c.STATUS_LAST_SEEN_FORMAT_KEY).format(time="")[:8], label)

        self.fire("UserUpdate", Record(status=types.UserStatusOnline(expires=None), user_id=1))
        online = self.text("STATUS_ONLINE")
        self.assertTrue(pump(lambda: online in self.frame.messages_list.GetName()))
        self.assertEqual(self.frame.messages_label.GetLabel(), self.frame.messages_list.GetName())

    def test_bots_and_groups_show_no_status(self):
        self.open_chat(1)
        self.assertEqual(
            self.frame.messages_list.GetName(), self.text(c.MESSAGES_OF_LABEL_FORMAT_KEY).format(chat="Helper")
        )

    def test_typing_shows_in_the_status_bar_and_is_spoken_unless_turned_off(self):
        self.open_chat(0)
        typing = self.text(c.MSG_TYPING_FORMAT_KEY).format(chat="Ali")
        event = Record(status=None, typing=True, is_private=True, chat_id=1)
        self.frame.settings.set(s.SETTING_ANNOUNCE_TYPING, False)
        self.fire("UserUpdate", event)
        self.assertTrue(pump(lambda: self.frame.GetStatusBar().GetStatusText() == typing))
        self.assertNotIn(typing, self.spoken)

        self.frame.settings.set(s.SETTING_ANNOUNCE_TYPING, True)
        self.frame.SetStatusText("")
        self.fire("UserUpdate", event)
        self.assertTrue(pump(lambda: typing in self.spoken))
        # Telegram repeats the notice while the typing goes on; once is enough to hear.
        self.fire("UserUpdate", event)
        pump(timeout=0.2)
        self.assertEqual(self.spoken.count(typing), 1)

        self.frame.clear_typing(typing)
        self.assertEqual(self.frame.GetStatusBar().GetStatusText(), "")

    def test_recording_and_sending_a_file_are_said_too(self):
        self.open_chat(0)
        for event, key in (
            (Record(status=None, recording=True, audio=True, is_private=True, chat_id=1), "MSG_RECORDING_VOICE_FORMAT"),
            (Record(status=None, recording=True, round=True, is_private=True, chat_id=1), "MSG_RECORDING_VIDEO_FORMAT"),
            (Record(status=None, uploading=True, document=True, is_private=True, chat_id=1), "MSG_SENDING_FILE_FORMAT"),
        ):
            said = self.text(key).format(chat="Ali")
            self.fire("UserUpdate", event)
            self.assertTrue(pump(lambda: said in self.spoken), key)

    def test_stopping_clears_what_the_status_bar_said(self):
        self.open_chat(0)
        typing = self.text(c.MSG_TYPING_FORMAT_KEY).format(chat="Ali")
        self.fire("UserUpdate", Record(status=None, typing=True, is_private=True, chat_id=1))
        self.assertTrue(pump(lambda: self.frame.GetStatusBar().GetStatusText() == typing))
        self.fire("UserUpdate", Record(status=None, cancel=True, is_private=True, chat_id=1))
        self.assertTrue(pump(lambda: self.frame.GetStatusBar().GetStatusText() == ""))

    def test_a_cancel_leaves_other_news_on_the_status_bar(self):
        self.open_chat(0)
        self.frame.SetStatusText("something else")
        self.fire("UserUpdate", Record(status=None, cancel=True, is_private=True, chat_id=1))
        pump(timeout=0.2)
        self.assertEqual(self.frame.GetStatusBar().GetStatusText(), "something else")

    def test_in_a_group_the_member_is_named(self):
        self.open_chat(0)

        async def get_user():
            return make_user(9, "Mona")
        # A group's member typing, told as if in the open chat so the window shows it.
        event = Record(status=None, typing=True, is_private=False, chat_id=1, get_user=get_user)
        self.fire("UserUpdate", event)
        said = self.text(c.MSG_TYPING_FORMAT_KEY).format(chat="Mona")
        self.assertTrue(pump(lambda: said in self.spoken))

    def test_typing_in_another_chat_is_ignored(self):
        self.open_chat(1)
        ready = self.frame.GetStatusBar().GetStatusText()
        self.fire("UserUpdate", Record(status=None, typing=True, is_private=True, chat_id=1))
        pump(timeout=0.2)
        self.assertEqual(self.frame.GetStatusBar().GetStatusText(), ready)

    def test_bot_buttons_are_read_out_and_can_be_pressed(self):
        self.open_chat(1)
        self.assertIn("Yes، Site", self.row(0))
        self.frame.messages_list.SetSelection(0)
        FakeChooser.selection = 0
        presses = YES.presses
        # Enter on the message is enough: it has nothing else to open.
        self.frame.on_activate_message(None)
        self.assertEqual(FakeChooser.last_choices, ["Yes", "Site"])
        self.assertTrue(pump(lambda: YES.presses == presses + 1))
        self.assertTrue(pump(lambda: self.spoken and self.spoken[-1] == "Saved"))

    def test_link_button_opens_only_after_the_user_agrees(self):
        self.open_chat(1)
        self.frame.messages_list.SetSelection(0)
        FakeChooser.selection = 1
        with mock.patch.object(ui.message_actions.webbrowser, "open") as open_link:
            self.box_answer = wx.NO
            self.frame.on_buttons_menu(None)
            self.assertTrue(pump(lambda: len(self.boxes) == 1))
            self.assertIn(SITE.url, self.boxes[0])
            open_link.assert_not_called()

            self.box_answer = wx.YES
            self.frame.on_buttons_menu(None)
            self.assertTrue(pump(lambda: open_link.called))
            open_link.assert_called_once_with(SITE.url)
        self.assertEqual(SITE.presses, 0)

    def test_message_without_buttons_says_so(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(0)
        self.frame.on_buttons_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NO_BUTTONS_KEY))
