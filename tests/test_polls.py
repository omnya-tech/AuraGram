"""A poll Telegram would refuse is caught before it is sent, with the text kept to fix; one it refuses anyway is said plainly."""
from unittest import mock

import wx

import core.constants as c
from telethon.errors import PollQuestionInvalidError
import core.settings as s
import core.telegram_client as telegram_client
import ui.composer
from telethon.tl import types
from tests.harness import FakeChooser, FakeTelegramClient, WindowTestCase, make_channel, make_message, make_user, pump

NEWS = make_channel(3, "News", admin_rights=mock.Mock(post_messages=True))


class PollTest(WindowTestCase):
    chats = [(NEWS, 0, False)]

    def setUp(self):
        super().setUp()
        FakePollSettings.chosen = dict(DEFAULT_SETTINGS)
        patch = mock.patch.object(ui.composer, "PollSettingsDialog", FakePollSettings)
        patch.start()
        self.addCleanup(patch.stop)
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


# What the stand-in settings window answers unless a test says otherwise: an anonymous poll, nothing else.
DEFAULT_SETTINGS = {"anonymous": True, "multiple": False, "shuffle": False, "hide_results": False,
                    "no_revote": False, "close_after": 0, "quiz_answer": None, "explanation": ""}


class FakePollSettings:
    """Stands in for the poll settings window; `chosen` is what it answers, None for Cancel."""

    chosen = None
    opened = []

    def __init__(self, parent, i18n, options, defaults, in_channel=False):
        FakePollSettings.opened.append((list(options), dict(defaults), in_channel))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ShowModal(self):
        return wx.ID_OK if FakePollSettings.chosen is not None else wx.ID_CANCEL

    def settings(self):
        return dict(FakePollSettings.chosen)

    def remembered(self):
        kept = {name: value for name, value in FakePollSettings.chosen.items() if isinstance(value, bool)}
        kept["quiz"] = FakePollSettings.chosen["quiz_answer"] is not None
        kept["close_after"] = FakePollSettings.chosen["close_after"]
        return kept


def poll_message(message_id, question, options, public=False, closed=False, outgoing=True):
    """A poll as Telegram sends it, for the window to read and act on."""
    poll = types.Poll(
        id=1, hash=0, question=types.TextWithEntities(question, []), closed=closed, public_voters=public,
        answers=[types.PollAnswer(types.TextWithEntities(text, []), bytes([index])) for index, text in enumerate(options)],
    )
    return make_message(message_id, outgoing=outgoing, poll=types.MessageMediaPoll(poll=poll, results=types.PollResults()))


class PollSettingsTest(WindowTestCase):
    chats = [(make_channel(4, "Team", group=True, creator=True), 0, False), (NEWS, 0, False)]
    history = {
        telegram_client.get_peer_id(make_channel(4, "Team", group=True, creator=True)): [
            poll_message(1, "Lunch?", ["Pizza", "Soup"], public=True),
            poll_message(2, "Secret?", ["Yes", "No"], public=False, outgoing=False),
        ],
    }

    def setUp(self):
        super().setUp()
        FakePollSettings.opened = []
        FakePollSettings.chosen = dict(DEFAULT_SETTINGS)
        FakePollSettings.chosen = dict(DEFAULT_SETTINGS)
        patch = mock.patch.object(ui.composer, "PollSettingsDialog", FakePollSettings)
        patch.start()
        self.addCleanup(patch.stop)
        self.open_chat(0)

    def poll_sent(self):
        self.assertTrue(pump(lambda: self.calls("poll")))
        return self.calls("poll")[-1][2]

    def test_every_setting_reaches_telegram(self):
        FakeChooser.values = ["Lunch?", "Pizza\nSoup"]
        FakePollSettings.chosen.update(anonymous=False, multiple=True, shuffle=True, hide_results=True,
                                       no_revote=True, close_after=300)
        self.frame.on_new_poll_menu(None)
        poll = self.poll_sent().poll
        self.assertTrue(poll.public_voters)
        self.assertTrue(poll.multiple_choice)
        self.assertTrue(poll.shuffle_answers)
        self.assertTrue(poll.hide_results_until_close)
        self.assertTrue(poll.revoting_disabled)
        self.assertEqual(poll.close_period, 300)
        self.assertFalse(poll.quiz)

    def test_a_quiz_takes_its_right_answer_and_explanation(self):
        FakeChooser.values = ["2 + 2?", "3\n4\n5"]
        FakePollSettings.chosen.update(quiz_answer=1, explanation="Two pairs make four.")
        self.frame.on_new_poll_menu(None)
        media = self.poll_sent()
        self.assertTrue(media.poll.quiz)
        self.assertEqual(media.correct_answers, [bytes([1])])
        self.assertEqual(media.solution, "Two pairs make four.")
        self.assertTrue(pump(lambda: self.spoken and self.spoken[-1] == self.text(c.MSG_QUIZ_SENT_KEY)))

    def test_the_last_settings_are_offered_again_for_the_next_poll(self):
        FakeChooser.values = ["Lunch?", "Pizza\nSoup"]
        FakePollSettings.chosen.update(anonymous=False, close_after=60)
        self.frame.on_new_poll_menu(None)
        self.poll_sent()
        FakeChooser.values = ["Dinner?", "Rice\nBread"]
        self.frame.on_new_poll_menu(None)
        defaults = FakePollSettings.opened[-1][1]
        self.assertFalse(defaults["anonymous"])
        self.assertEqual(defaults["close_after"], 60)
        # And from one start of the program to the next.
        self.assertFalse(s.Settings().get(s.SETTING_POLL_DEFAULTS)["anonymous"])

    def test_cancelling_the_settings_sends_nothing(self):
        FakeChooser.values = ["Lunch?", "Pizza\nSoup"]
        FakePollSettings.chosen = None
        self.frame.on_new_poll_menu(None)
        pump(timeout=0.3)
        self.assertEqual(self.calls("poll"), [])

    def test_a_channel_poll_is_anonymous_and_the_window_says_so(self):
        self.frame.close_chat()
        self.open_chat(1)
        FakeChooser.values = ["Lunch?", "Pizza\nSoup"]
        FakePollSettings.chosen.update(anonymous=False)
        self.frame.on_new_poll_menu(None)
        self.assertTrue(FakePollSettings.opened[-1][2])
        self.assertIsNone(self.poll_sent().poll.public_voters)

    def test_who_voted_is_shown_for_each_option(self):
        FakeTelegramClient.poll_votes = [(make_user(7, "Ali"), [bytes([0])]), (make_user(8, "Mona"), [bytes([0])])]
        self.frame.messages_list.SetSelection(self.frame.message_offset())
        shown = []
        with mock.patch.object(self.frame, "show_text", lambda title_key, text: shown.append((title_key, text))):
            self.frame.on_poll_voters_menu(None)
            self.assertTrue(pump(lambda: shown))
        title, text = shown[0]
        self.assertEqual(title, c.VOTERS_TITLE_KEY)
        separator = self.text(c.FILE_LABEL_SEPARATOR_KEY)
        self.assertIn(self.text(c.VOTERS_OPTION_FORMAT_KEY).format(option="Pizza", count=2, names=separator.join(["Ali", "Mona"])), text)
        self.assertIn(self.text(c.VOTERS_OPTION_FORMAT_KEY).format(option="Soup", count=0, names=self.text(c.VOTERS_NOBODY_KEY)), text)

    def test_an_anonymous_poll_says_who_voted_cannot_be_known(self):
        self.frame.messages_list.SetSelection(self.frame.message_offset() + 1)
        # Offered all the same, so it is never looked for in vain.
        self.frame.on_message_context_menu(self.context_event(self.frame.messages_list))
        self.assertIn(self.text(c.CONTEXT_POLL_VOTERS_KEY), self.menu_labels)
        self.frame.on_poll_voters_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_POLL_ANONYMOUS_KEY))
        self.assertEqual(self.calls("GetPollVotesRequest"), [])

    def test_ones_own_poll_can_be_closed_after_a_yes(self):
        self.frame.messages_list.SetSelection(self.frame.message_offset())
        self.box_answer = wx.NO
        self.frame.on_close_poll_menu(None)
        pump(timeout=0.2)
        self.assertEqual(self.calls("EditMessageRequest"), [])
        self.box_answer = wx.YES
        self.frame.on_close_poll_menu(None)
        self.assertTrue(pump(lambda: self.frame.messages[0]["poll"]["closed"]))
        self.assertEqual(self.spoken[-1], self.text(c.MSG_POLL_CLOSED_DONE_KEY))
        # Closed, it says so rather than asking again.
        self.frame.on_close_poll_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_POLL_CLOSED_KEY))

    def test_each_option_says_its_share_of_the_voters_and_the_poll_how_many_voted(self):
        poll = {
            "question": "Lunch?", "closed": False, "multiple": False, "total": 5,
            "options": [
                {"text": "Pizza", "voters": 2, "chosen": True},
                {"text": "Soup", "voters": 3, "chosen": False},
            ],
        }
        text = self.frame.poll_text(poll)
        self.assertIn(self.text(c.POLL_PERCENT_FORMAT_KEY).format(percent=40), text)
        self.assertIn(self.text(c.POLL_PERCENT_FORMAT_KEY).format(percent=60), text)
        self.assertTrue(text.endswith(self.text(c.POLL_TOTAL_FORMAT_KEY).format(text="", total=5)))
        # Before voting Telegram hides the counts, so there is nothing to share out.
        for option in poll["options"]:
            option["voters"] = None
        poll["total"] = None
        text = self.frame.poll_text(poll)
        self.assertNotIn(self.text(c.POLL_PERCENT_FORMAT_KEY).format(percent=40), text)
        self.assertNotIn(self.text(c.POLL_TOTAL_FORMAT_KEY).format(text="", total=5).strip(), text)

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


class PollSettingsWindowTest(WindowTestCase):
    """The window itself: what it offers, what it refuses, and what it gives back."""

    def window(self, in_channel=False, defaults=None):
        from ui.poll_settings_dialog import PollSettingsDialog
        dialog = PollSettingsDialog(self.frame, self.i18n, ["3", "4"], defaults or {"anonymous": True}, in_channel)
        self.addCleanup(dialog.Destroy)
        return dialog

    def test_anonymous_is_always_there_and_in_a_channel_fixed_on(self):
        dialog = self.window()
        self.assertTrue(dialog.boxes["anonymous"].GetValue())
        self.assertTrue(dialog.boxes["anonymous"].IsEnabled())
        in_channel = self.window(in_channel=True, defaults={"anonymous": False})
        self.assertTrue(in_channel.boxes["anonymous"].GetValue())
        self.assertFalse(in_channel.boxes["anonymous"].IsEnabled())
        self.assertEqual(in_channel.boxes["anonymous"].GetLabel(), self.text(c.POLL_SETTING_ANONYMOUS_CHANNEL_KEY))
        # The channel's rule leaves the default for other chats as it was.
        self.assertNotIn("anonymous", in_channel.remembered())

    def test_the_quiz_parts_show_only_for_a_quiz_and_its_mistakes_are_caught(self):
        dialog = self.window()
        self.assertFalse(dialog.answer_choice.IsShown())
        dialog.boxes["quiz"].SetValue(True)
        dialog.show_quiz_parts()
        self.assertTrue(dialog.answer_choice.IsShown())
        dialog.boxes["multiple"].SetValue(True)
        self.assertEqual(dialog.problem(), self.text(c.ERR_POLL_QUIZ_MULTIPLE_KEY))
        dialog.boxes["multiple"].SetValue(False)
        dialog.explanation_input.SetValue("x" * 250)
        self.assertEqual(dialog.problem(), self.text(c.ERR_POLL_EXPLANATION_LONG_FORMAT_KEY).format(
            length=250, limit=c.POLL_EXPLANATION_MAX))
        dialog.explanation_input.SetValue("Two pairs.")
        dialog.answer_choice.SetSelection(1)
        dialog.close_choice.SetSelection(2)
        self.assertIsNone(dialog.problem())
        chosen = dialog.settings()
        self.assertEqual((chosen["quiz_answer"], chosen["explanation"]), (1, "Two pairs."))
        self.assertEqual(chosen["close_after"], c.POLL_CLOSE_CHOICES[2][0])
