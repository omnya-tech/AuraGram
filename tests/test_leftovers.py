"""The last pieces: recovery email, moving or deleting the account, translation, stories,
what a row says about a message's past, and telling the other side that one is typing."""
import asyncio
from unittest import mock

import wx
from telethon.tl import types

import core.constants as c
import core.settings as s
from tests.harness import (
    NOW, FakeChooser, FakeTelegramClient, Record, WindowTestCase, make_message, make_user, pump
)
from ui.settings_dialog import SettingsDialog

ALI = make_user(1, "Ali")
MONA = make_user(2, "Mona")


class LeftoversTest(WindowTestCase):
    chats = [(ALI, 0, False), (MONA, 0, False)]
    history = {1: [
        make_message(1, "bonjour", sender=ALI),
        make_message(2, sender=ALI, photo=True),
        make_message(3, "passed on", sender=ALI, forward=Record(from_name="Hidden Hand", sender=None, chat=None)),
        make_message(4, "fixed typo", sender=ALI, edit_date=NOW),
        make_message(5, "news", sender=ALI, post=True, views=120, edit_date=NOW, edit_hide=True),
    ]}

    def settings(self):
        dialog = SettingsDialog(self.frame, self.i18n, self.frame.settings, self.manager)
        self.addCleanup(dialog.Destroy)
        self.assertTrue(pump(lambda: dialog.profile is not None))
        return dialog

    def requests(self, name):
        return [call[1] for call in self.calls(name)]

    def two_step(self, dialog, values):
        FakeChooser.values = list(values)
        with mock.patch.object(wx, "PasswordEntryDialog", FakeChooser):
            dialog.on_two_step(None)
            pump(timeout=0.5)

    def test_recovery_email_is_confirmed_with_the_code_from_the_mail(self):
        self.two_step(self.settings(), ["secret", "secret", "", "me@example.org", "123456"])
        self.assertEqual(self.calls("2fa_email"), [("2fa_email", "me@example.org")])
        self.assertEqual(self.boxes[-1], self.text(c.MSG_TWO_STEP_SAVED_KEY))

    def test_wrong_or_missing_mail_code_keeps_the_password_and_says_the_email_is_not_set(self):
        self.two_step(self.settings(), ["secret", "secret", "", "me@example.org", "000000"])
        self.assertEqual(self.boxes[-1], self.text(c.ERR_EMAIL_UNCONFIRMED_KEY))
        self.assertEqual(FakeTelegramClient.two_step_password, "secret")
        self.assertEqual(self.calls("2fa_email"), [])

    def test_account_moves_to_a_new_number_after_its_code(self):
        dialog = self.settings()
        FakeChooser.values = ["+201000000001", "55555"]
        dialog.on_change_phone(None)
        self.assertTrue(pump(lambda: self.requests("ChangePhoneRequest")))
        request = self.requests("ChangePhoneRequest")[0]
        self.assertEqual((request.phone_number, request.phone_code_hash, request.phone_code),
                         ("+201000000001", "change-hash", "55555"))
        self.assertTrue(pump(lambda: self.boxes[-1:] == [self.text(c.MSG_PHONE_CHANGED_KEY)]))

    def test_number_that_already_has_an_account_is_refused(self):
        dialog = self.settings()
        FakeChooser.values = ["+taken"]
        dialog.on_change_phone(None)
        self.assertTrue(pump(lambda: self.boxes[-1:] == [self.text(c.ERR_PHONE_TAKEN_KEY)]))
        self.assertEqual(self.requests("ChangePhoneRequest"), [])

    def test_account_is_deleted_only_after_the_question_and_the_word(self):
        dialog = self.settings()
        cancelled = self.text(c.MSG_DELETE_ACCOUNT_CANCELLED_KEY)
        self.box_answer = wx.NO
        dialog.on_delete_account(None)
        self.assertEqual(self.spoken[-1], cancelled)

        self.box_answer = wx.YES
        FakeChooser.values = ["yes"]
        dialog.on_delete_account(None)
        pump(timeout=0.3)
        self.assertEqual(self.spoken.count(cancelled), 2)
        self.assertEqual(self.requests("DeleteAccountRequest"), [])
        self.assertFalse(dialog.account_deleted)

        FakeChooser.values = [self.text(c.DELETE_ACCOUNT_WORD_KEY)]
        dialog.on_delete_account(None)
        self.assertTrue(pump(lambda: dialog.account_deleted))
        self.assertEqual(len(self.requests("DeleteAccountRequest")), 1)

    def test_message_is_translated_into_the_interface_language(self):
        shown = []
        self.frame.show_text = lambda title_key, text: shown.append(text)
        self.open_chat(0)
        self.frame.messages_list.SetSelection(0)
        self.frame.on_translate_menu(None)
        self.assertTrue(pump(lambda: shown == ["translated #1"]))
        self.assertEqual(self.requests("TranslateTextRequest")[0].to_lang, c.DEFAULT_LANG)

        self.frame.messages_list.SetSelection(1)
        self.frame.on_translate_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NOTHING_TO_TRANSLATE_KEY))

    def test_story_is_chosen_by_person_then_opened_and_counted_as_seen(self):
        self.frame.on_stories_menu(None)
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.text(c.MSG_NO_STORIES_KEY)]))

        FakeTelegramClient.stories = Record(users=[ALI], chats=[], peer_stories=[Record(
            peer=types.PeerUser(1), stories=[
                Record(id=5, media=types.MessageMediaPhoto(), caption="sunset", date=NOW),
                Record(id=6),  # known to Telegram by number only: nothing to open
            ]
        )])
        FakeChooser.selection = 0
        with mock.patch.object(wx, "LaunchDefaultApplication") as launch:
            self.frame.on_stories_menu(None)
            self.assertTrue(pump(lambda: launch.called))
        self.assertIn("sunset", FakeChooser.last_choices[0])
        self.assertEqual(len(FakeChooser.last_choices), 1)
        self.assertEqual(self.requests("ReadStoriesRequest")[0].max_id, 5)
        self.assertFalse(self.frame.is_busy)

    def test_picture_is_posted_as_a_story_for_the_chosen_audience(self):
        FakeChooser.values = ["good morning"]
        FakeChooser.selection = 1
        self.frame.post_story("sunrise.jpg")
        self.assertTrue(pump(lambda: self.requests("SendStoryRequest")))
        story = self.requests("SendStoryRequest")[0]
        self.assertEqual((story.media.file, story.caption, story.period), ("uploaded:sunrise.jpg", "good morning", c.STORY_SECONDS))
        self.assertEqual([type(rule).__name__ for rule in story.privacy_rules], ["InputPrivacyValueAllowContacts"])
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.text(c.MSG_STORY_POSTED_KEY)]))
        self.assertFalse(self.frame.is_busy)

    def test_backing_out_of_the_story_caption_posts_nothing(self):
        FakeChooser.confirmed = False
        self.frame.post_story("sunrise.jpg")
        pump(timeout=0.2)
        self.assertEqual(self.requests("SendStoryRequest"), [])

    def test_rows_tell_a_message_was_forwarded_edited_or_how_many_saw_it(self):
        self.open_chat(0)
        rows = [self.frame.messages_list.GetString(index) for index in range(5)]
        self.assertIn(self.text(c.FORWARDED_FORMAT_KEY).format(name="Hidden Hand", text="passed on"), rows[2])
        self.assertIn(self.text(c.EDITED_FORMAT_KEY).format(text="fixed typo"), rows[3])
        views = self.text(c.VIEWS_FORMAT_KEY).format(count=120)
        self.assertIn("news. " + views, rows[4])

        # The numbers can be put ahead of the message instead, to be heard first.
        self.frame.settings.set(s.SETTING_MESSAGE_STATS, c.MESSAGE_STATS_BEFORE)
        self.frame.render_messages(4)
        row = self.frame.messages_list.GetString(4)
        self.assertTrue(row.startswith(views + ". "))
        self.assertEqual(row.count(views), 1)
        # A message with no numbers is untouched by the choice.
        self.assertEqual(self.frame.messages_list.GetString(3), rows[3])
        # A post stamped only because its reactions changed was not edited.
        self.assertFalse(self.frame.messages[4]["edited"])
        self.assertEqual(rows[0].count("bonjour"), 1)
        self.assertIsNone(self.frame.messages[0]["forwarded_from"])

    def test_typing_is_told_once_in_a_while_and_not_while_editing(self):
        self.open_chat(0)
        self.frame.message_input.SetValue("h")
        for _ in range(3):
            self.frame.tell_typing()
        self.assertTrue(pump(lambda: len(self.requests("SetTypingRequest")) == 1))
        pump(timeout=0.2)
        self.assertEqual(len(self.requests("SetTypingRequest")), 1)

        self.open_chat(1)
        self.frame.editing = {"id": 1, "text": "x"}
        self.frame.message_input.SetValue("changing")
        self.frame.tell_typing()
        pump(timeout=0.2)
        self.assertEqual(len(self.requests("SetTypingRequest")), 1)
        self.frame.editing = None

    def test_draft_changed_on_another_device_arrives_while_the_app_is_open(self):
        self.open_chat(1)

        def draft(peer_id, text):
            update = Record(peer=types.PeerUser(peer_id), draft=Record(message=text))
            asyncio.run_coroutine_threadsafe(self.manager.client.handlers["Raw"](update), self.manager.loop)

        draft(1, "typed on the phone")
        self.assertTrue(pump(lambda: self.frame.drafts.get(1) == "typed on the phone"))
        draft(1, "")
        self.assertTrue(pump(lambda: 1 not in self.frame.drafts))
        # The open chat's field is left alone: the user may be typing in it.
        self.frame.message_input.SetValue("my own words")
        draft(2, "from elsewhere")
        pump(timeout=0.2)
        self.assertNotIn(2, self.frame.drafts)
        self.assertEqual(self.frame.message_input.GetValue(), "my own words")
