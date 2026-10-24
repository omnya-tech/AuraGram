"""A poll Telegram would refuse is caught before it is sent, with the text kept to fix; one it refuses anyway is said plainly."""
from unittest import mock

import wx

import core.constants as c
from telethon.errors import PollQuestionInvalidError
from tests.harness import FakeChooser, FakeTelegramClient, WindowTestCase, make_channel, make_user, pump

NEWS = make_channel(3, "News", admin_rights=mock.Mock(post_messages=True))


class PollTest(WindowTestCase):
    chats = [(NEWS, 0, False)]

    def setUp(self):
        super().setUp()
        self.open_chat(0)
        self.asked = []
        original = FakeChooser.__init__

        def remember(chooser, parent, message, caption="", choices=None, *args, **kwargs):
            # What each box offered to start with: the text typed before, after a refusal.
            self.asked.append(kwargs.get("value"))
            original(chooser, parent, message, caption, choices, *args, **kwargs)
        patch = mock.patch.object(FakeChooser, "__init__", remember)
        patch.start()
        self.addCleanup(patch.stop)

    def sent(self):
        return pump(lambda: self.calls("send"), timeout=0.5) and self.calls("send")

    def test_a_question_too_long_is_said_with_its_length_and_kept_to_shorten(self):
        long_question = "س" * 300
        FakeChooser.values = [long_question, "Short question?", "Yes\nNo"]
        # Offered to send it as a message first; No, to shorten it here instead.
        self.box_answer = wx.NO
        self.frame.on_new_poll_menu(None)
        self.assertEqual(self.boxes, [
            self.text(c.MSG_POLL_QUESTION_AS_MESSAGE_FORMAT_KEY).format(length=300, limit=c.POLL_QUESTION_MAX),
            self.text(c.ERR_POLL_QUESTION_LONG_FORMAT_KEY).format(length=300, limit=c.POLL_QUESTION_MAX),
        ])
        # Asked again with what was written, not with an empty field.
        self.assertEqual(self.asked[:2], ["", long_question])
        self.assertTrue(self.sent())

    def test_an_option_too_long_or_twice_is_said_and_the_options_kept(self):
        options_long = "Yes\n" + "x" * 120
        options_twice = "Yes\nyes"
        FakeChooser.values = ["Which?", options_long, options_twice, "Yes\nNo"]
        self.frame.on_new_poll_menu(None)
        self.assertEqual(self.boxes, [
            self.text(c.ERR_POLL_OPTION_LONG_FORMAT_KEY).format(option="x" * 120, length=120, limit=c.POLL_OPTION_MAX),
            self.text(c.ERR_POLL_OPTION_TWICE_FORMAT_KEY).format(option="yes"),
        ])
        self.assertEqual(self.asked[1:4], ["", options_long, options_twice])
        self.assertTrue(self.sent())

    def test_an_emoji_counts_as_telegram_counts_it(self):
        from ui.composer import telegram_length
        self.assertEqual(telegram_length("سؤال"), 4)
        self.assertEqual(telegram_length("👍"), 2)

    def test_a_poll_telegram_refuses_anyway_is_said_plainly(self):
        async def refuse(*args, **kwargs):
            raise PollQuestionInvalidError(request=None)
        FakeChooser.values = ["Which?", "Yes\nNo"]
        with mock.patch.object(FakeTelegramClient, "send_message", refuse):
            self.frame.on_new_poll_menu(None)
            self.assertTrue(pump(lambda: self.boxes))
        self.assertEqual(self.boxes, [self.text(c.ERR_POLL_QUESTION_KEY)])

    def test_a_long_question_can_go_first_as_a_message_with_the_poll_under_it(self):
        long_question = "ما رأيكم في " + "التفاصيل " * 40
        FakeChooser.values = [long_question, "Which?", "Yes\nNo"]
        self.frame.on_new_poll_menu(None)
        self.assertTrue(pump(lambda: len(self.calls("send")) == 2))
        message, poll = self.calls("send")
        # The question in full, then the poll answering it, with the short question offered to start with.
        self.assertEqual(message[2], long_question.strip())
        sent_id = max(m.id for m in FakeTelegramClient.history[message[1]])
        self.assertEqual(poll[3], sent_id)
        self.assertEqual(self.asked[1], self.text(c.POLL_SHORT_QUESTION_KEY))


class PollSettingsTest(WindowTestCase):
    chats = [(make_channel(4, "Team", group=True, creator=True), 0, False), (NEWS, 0, False)]

    def setUp(self):
        super().setUp()
        self.open_chat(0)

    def poll_sent(self):
        self.assertTrue(pump(lambda: self.calls("poll")))
        return self.calls("poll")[-1][2]

    def settings_text(self, *keys):
        return [self.text(key) for key in keys]

    def test_a_group_poll_offers_its_settings_with_anonymous_ticked(self):
        FakeChooser.values = ["Lunch?", "Pizza\nSoup"]
        offered = []
        with mock.patch.object(self.frame, "pick_many",
                               lambda prompt, choices, selected: offered.append((list(choices), selected)) or [1]):
            self.frame.on_new_poll_menu(None)
        self.assertEqual(offered, [(self.settings_text(
            c.POLL_SETTING_ANONYMOUS, c.POLL_SETTING_MULTIPLE, c.POLL_SETTING_QUIZ), [0])])
        media = self.poll_sent()
        # Anonymous unticked, several answers ticked: who voted what is shown, and more than one may be chosen.
        self.assertTrue(media.poll.public_voters)
        self.assertTrue(media.poll.multiple_choice)
        self.assertFalse(media.poll.quiz)
        self.assertIsNone(media.correct_answers)

    def test_a_quiz_takes_its_right_answer_and_explanation(self):
        FakeChooser.values = ["2 + 2?", "3\n4\n5", "Two pairs make four."]
        FakeChooser.selection = 1
        with mock.patch.object(self.frame, "pick_many", lambda prompt, choices, selected: [0, 2]):
            self.frame.on_new_poll_menu(None)
        media = self.poll_sent()
        self.assertTrue(media.poll.quiz)
        self.assertIsNone(media.poll.public_voters)
        self.assertEqual(media.correct_answers, [bytes([1])])
        self.assertEqual(media.solution, "Two pairs make four.")
        self.assertTrue(pump(lambda: self.spoken and self.spoken[-1] == self.text(c.MSG_QUIZ_SENT_KEY)))

    def test_a_quiz_with_several_answers_is_refused_and_the_settings_asked_again(self):
        FakeChooser.values = ["2 + 2?", "3\n4", ""]
        answers = iter([[1, 2], [2]])
        with mock.patch.object(self.frame, "pick_many", lambda prompt, choices, selected: next(answers)):
            self.frame.on_new_poll_menu(None)
        self.assertEqual(self.boxes, [self.text(c.ERR_POLL_QUIZ_MULTIPLE_KEY)])
        media = self.poll_sent()
        self.assertTrue(media.poll.quiz)
        self.assertIsNone(media.solution)

    def test_a_channel_poll_is_anonymous_without_asking(self):
        self.frame.close_chat()
        self.open_chat(1)
        FakeChooser.values = ["Lunch?", "Pizza\nSoup"]
        offered = []
        with mock.patch.object(self.frame, "pick_many",
                               lambda prompt, choices, selected: offered.append(list(choices)) or []):
            self.frame.on_new_poll_menu(None)
        self.assertEqual(offered, [self.settings_text(c.POLL_SETTING_MULTIPLE, c.POLL_SETTING_QUIZ)])
        self.assertIsNone(self.poll_sent().poll.public_voters)

    def test_a_quiz_reads_as_one_with_its_right_answer_and_explanation_once_answered(self):
        text = self.frame.poll_text({
            "question": "2 + 2?", "closed": False, "multiple": False, "quiz": True, "explanation": "Two pairs.",
            "options": [
                {"text": "3", "voters": 1, "chosen": True, "correct": False},
                {"text": "4", "voters": 2, "chosen": False, "correct": True},
            ],
        })
        self.assertTrue(text.startswith(self.text(c.QUIZ_FORMAT_KEY).split("{")[0]))
        self.assertIn(self.text(c.POLL_CORRECT_KEY), text)
        self.assertTrue(text.endswith("Two pairs."))
