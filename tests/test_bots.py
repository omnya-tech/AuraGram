"""Using other people's bots: starting one, with what its link carried, its commands, its latest
buttons from anywhere in the chat, and buttons that ask for your number or your place."""
from unittest import mock

import wx
from telethon.tl import types

import core.constants as c
from tests.harness import FakeChooser, FakeTelegramClient, Record, WindowTestCase, make_message, make_user, pump

FRESH = make_user(7, "Fresh bot", bot=True)
HELPER = make_user(8, "Helper", bot=True)


class Button:
    """A bot's button, of the kind Telegram says, remembering how it was pressed."""

    def __init__(self, text, kind=None):
        self.text = text
        self.url = None
        self.button = Record(type=kind or types.ButtonTypeDefault())
        self.presses = []

    async def click(self, **shared):
        self.presses.append(shared)
        return None


class BotTest(WindowTestCase):
    chats = [(FRESH, 0, False), (HELPER, 0, False)]

    def setUp(self):
        self.phone = Button("Share my number", types.ButtonTypeRequestPhone())
        self.place = Button("Where am I", types.ButtonTypeRequestGeoLocation())
        self.menu = Button("Menu")
        type(self).history = {8: [
            make_message(1, "Pick one", sender=HELPER, chat_id=8, buttons=[[self.menu, self.phone, self.place]]),
            make_message(2, "Anything else?", sender=HELPER, chat_id=8),
        ]}
        super().setUp()

    def requests(self, name):
        return [call[1] for call in self.calls(name)]

    def sent(self):
        return [call[2] for call in self.calls("send")]

    def test_a_bot_never_started_offers_start_and_enter_sends_it(self):
        self.open_chat(0)
        rows = self.frame.messages_list.GetItems()
        self.assertEqual(rows, [self.text(c.BOT_START_ROW_KEY)])
        self.assertEqual(self.frame.messages_list.GetSelection(), 0)
        self.frame.on_activate_message(None)
        self.assertTrue(pump(lambda: self.sent() == [c.BOT_START_COMMAND]))
        self.assertTrue(pump(lambda: self.text(c.MSG_BOT_STARTED_KEY) in self.spoken))

    def test_a_start_link_starts_the_bot_with_what_it_carried(self):
        FakeTelegramClient.public = {"freshbot": FRESH}
        self.frame.on_link_resolved({"chat": dict(self.frame.dialogs[0], start_param="ref42"), "invite": None})
        self.assertTrue(pump(lambda: self.frame.current_dialog_id == self.frame.dialogs[0]["id"]))
        self.frame.on_bot_start_menu(None)
        self.assertTrue(pump(lambda: self.requests("StartBotRequest")))
        self.assertEqual(self.requests("StartBotRequest")[0].start_param, "ref42")
        self.assertEqual(self.sent(), [])

    def test_the_link_itself_is_read_for_its_start(self):
        FakeTelegramClient.public = {"freshbot": FRESH}
        found = []
        self.manager.resolve_link("https://t.me/freshbot?start=ref42", lambda result, error_key: found.append(result))
        self.assertTrue(pump(lambda: found))
        self.assertEqual(found[0]["chat"]["start_param"], "ref42")

    def test_commands_are_listed_and_the_chosen_one_is_sent(self):
        commands = [types.BotCommand("help", "What I can do"), types.BotCommand("lang", "")]
        answer = Record(users=[HELPER], full_user=Record(about="", bot_info=Record(user_id=8, commands=commands)))
        real_call = FakeTelegramClient.__call__

        async def call(client, request):
            if type(request).__name__ == "GetFullUserRequest":
                client.calls.append(("GetFullUserRequest", request))
                return answer
            return await real_call(client, request)
        self.open_chat(1)
        self.frame.message_input.SetValue("half a thought")
        FakeChooser.selection = 0
        with mock.patch.object(FakeTelegramClient, "__call__", call):
            self.frame.on_bot_commands_menu(None)
            self.assertTrue(pump(lambda: self.sent()))
        self.assertEqual(FakeChooser.last_choices, [
            self.text(c.BOT_COMMAND_FORMAT_KEY).format(command="/help", description="What I can do"), "/lang",
        ])
        self.assertEqual(self.sent(), ["/help"])
        # What was being typed is still there.
        self.assertEqual(self.frame.message_input.GetValue(), "half a thought")

    def test_the_latest_buttons_are_found_from_anywhere_in_the_chat(self):
        self.open_chat(1)
        # On the newest message, which has no buttons of its own.
        self.frame.messages_list.SetSelection(1)
        FakeChooser.selection = 0
        self.frame.on_bot_keyboard_menu(None)
        self.assertEqual(FakeChooser.last_choices, ["Menu", "Share my number", "Where am I"])
        self.assertTrue(pump(lambda: self.menu.presses == [{}]))

    def test_the_number_goes_to_the_bot_only_after_a_yes(self):
        self.open_chat(1)
        FakeChooser.selection = 1
        self.box_answer = wx.NO
        self.frame.on_bot_keyboard_menu(None)
        self.assertTrue(pump(lambda: self.boxes and self.text(c.MSG_CONFIRM_SHARE_PHONE_KEY) in self.boxes[-1]))
        pump(timeout=0.2)
        self.assertEqual(self.phone.presses, [])
        self.box_answer = wx.YES
        self.frame.on_bot_keyboard_menu(None)
        self.assertTrue(pump(lambda: self.phone.presses == [{"share_phone": True}]))

    def test_a_place_is_asked_for_and_given_the_way_telethon_takes_it(self):
        self.open_chat(1)
        FakeChooser.selection = 2
        FakeChooser.values = ["30.04, 31.23"]
        self.frame.on_bot_keyboard_menu(None)
        self.assertTrue(pump(lambda: self.place.presses == [{"share_geo": (31.23, 30.04)}]))


class InlineResult:
    """What an inline bot answers with: remembers being sent, and where."""

    def __init__(self, title="", description="", kind="article"):
        self.title, self.description, self.type = title, description, kind
        self.sent_to = []

    async def click(self, entity=None, reply_to=None):
        self.sent_to.append(entity)


class InlineBotTest(WindowTestCase):
    chats = [(make_user(1, "Ali"), 0, False)]

    def setUp(self):
        super().setUp()
        self.gif_bot = types.User(id=50, first_name="GIF", username="gif", bot=True, bot_inline_placeholder="Search", access_hash=1)
        self.friend = types.User(id=51, first_name="Sami", username="samiali", access_hash=1)
        FakeTelegramClient.public = {"gif": self.gif_bot, "samiali": self.friend}
        self.cat = InlineResult(kind="gif")
        self.news = InlineResult("Cats", "All about cats")
        FakeTelegramClient.inline_results = {"gif": [self.cat, self.news]}
        self.open_chat(0)

    def sent(self):
        return [call[2] for call in self.calls("send")]

    def test_a_bot_is_asked_and_the_chosen_result_is_sent(self):
        self.frame.message_input.SetValue("@gif cats")
        FakeChooser.selection = 1
        self.frame.on_send_message(None)
        self.assertTrue(pump(lambda: self.news.sent_to))
        self.assertEqual(self.calls("inline_query"), [("inline_query", "gif", "cats")])
        self.assertEqual(FakeChooser.last_choices, [
            self.text(c.INLINE_RESULT_UNTITLED_FORMAT_KEY).format(kind=self.text("INLINE_KIND_gif"), number=1),
            self.text(c.INLINE_RESULT_FORMAT_KEY).format(title="Cats", description="All about cats"),
        ])
        self.assertTrue(pump(lambda: self.frame.message_input.GetValue() == ""))
        self.assertEqual(self.sent(), [])

    def test_cancelling_leaves_the_words_to_change(self):
        self.frame.message_input.SetValue("@gif cats")
        FakeChooser.confirmed = False
        self.frame.on_send_message(None)
        self.assertTrue(pump(lambda: self.calls("inline_query")))
        pump(timeout=0.2)
        self.assertEqual(self.frame.message_input.GetValue(), "@gif cats")
        self.assertEqual((self.cat.sent_to, self.news.sent_to, self.sent()), ([], [], []))

    def test_a_person_named_at_the_start_is_just_a_message(self):
        self.frame.message_input.SetValue("@samiali see you at five")
        self.frame.on_send_message(None)
        self.assertTrue(pump(lambda: self.sent() == ["@samiali see you at five"]))
