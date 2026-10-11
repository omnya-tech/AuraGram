"""A person's details, folders made and changed, everything marked read, faster voice messages, and reports."""
import os
import tempfile
import unittest
from unittest import mock

import numpy
import wx
from telethon.tl import types

import core.constants as c
import core.settings as s
import core.telegram_client as telegram_client
from core import audio
from tests.harness import (
    FakeChooser, FakeTelegramClient, WindowTestCase, make_channel, make_message, make_user, pump
)
from ui.chat_info_dialog import ChatInfoDialog

ALI = types.User(id=1, first_name="Ali", phone="201001112223", contact=True, access_hash=1)
MONA = make_user(2, "Mona")
TEAM = make_channel(4, "Team", group=True)
TEAM_ID = telegram_client.get_peer_id(TEAM)


def peer_ids(peers):
    return [telegram_client.get_peer_id(peer) for peer in peers]


class MoreToolsTest(WindowTestCase):
    chats = [(ALI, 3, False), (MONA, 0, False), (TEAM, 1, False)]
    history = {1: [make_message(1, "buy now!!!", sender=ALI), make_message(2, "really", sender=ALI)]}

    def requests(self, name):
        return [call[1] for call in self.calls(name)]

    def script(self, picks=(), ticks=()):
        """Answer the frame's one-of and several-of questions in turn, keeping what each one offered."""
        self.offered = []
        picks, ticks = list(picks), list(ticks)
        self.frame.pick = lambda prompt, choices: (self.offered.append(choices), picks.pop(0))[1]
        self.frame.pick_many = lambda prompt, choices, selected: (self.offered.append((choices, selected)), ticks.pop(0))[1]

    def test_person_shows_their_number_and_the_groups_shared_with_them(self):
        FakeTelegramClient.common_chats = [TEAM]
        dialog = ChatInfoDialog(self.frame, self.i18n, self.manager, self.frame.all_dialogs[0])
        self.addCleanup(dialog.Destroy)
        self.assertTrue(pump(lambda: dialog.info is not None))
        summary = dialog.summary.GetValue()
        self.assertIn(self.text(c.INFO_PHONE_FORMAT_KEY).format(phone="201001112223"), summary)
        self.assertIn(self.text(c.INFO_COMMON_CHATS_FORMAT_KEY).format(titles="Team"), summary)

    def rules(self, *names):
        offered = list(c.FOLDER_CATEGORIES) + list(c.FOLDER_EXCLUSIONS)
        return [offered.index(name) for name in names]

    def test_new_folder_gets_the_next_number_and_becomes_a_view(self):
        self.script(picks=[0], ticks=[self.rules(c.CATEGORY_GROUPS, "exclude_muted"), [0]])
        FakeChooser.values = ["Work"]
        self.frame.on_folders_menu(None)
        self.assertTrue(pump(lambda: self.requests("UpdateDialogFilterRequest")))
        folder = self.requests("UpdateDialogFilterRequest")[0].filter
        self.assertEqual((folder.id, folder.title.text), (c.FIRST_FOLDER_ID, "Work"))
        self.assertTrue(folder.groups and folder.exclude_muted)
        self.assertFalse(folder.contacts or folder.exclude_read)
        self.assertEqual(peer_ids(folder.include_peers), [1])
        self.assertTrue(pump(lambda: len(self.frame.views) == 4 and "Work" in self.frame.views[3].label))
        self.assertEqual(self.spoken[-1], self.text(c.MSG_FOLDERS_SAVED_KEY))

    def test_editing_keeps_what_the_form_did_not_show(self):
        FakeTelegramClient.folders = [types.DialogFilter(
            id=5, title=types.TextWithEntities("Old", []), contacts=True,
            pinned_peers=[types.InputPeerUser(2, 1)],
            # One chat that is in the list, and one this session has never loaded.
            include_peers=[types.InputPeerUser(1, 1), types.InputPeerUser(99, 1)],
            exclude_peers=[types.InputPeerUser(98, 1)]
        )]
        self.script(picks=[1, 0], ticks=[self.rules(c.CATEGORY_CONTACTS, c.CATEGORY_BOTS), [2]])
        FakeChooser.values = ["Close people"]
        self.frame.on_folders_menu(None)
        self.assertTrue(pump(lambda: self.requests("UpdateDialogFilterRequest")))
        # The form opened with what the folder had: its rule ticked, its chats ticked (pinned ones too).
        self.assertEqual(self.offered[2][1], self.rules(c.CATEGORY_CONTACTS))
        self.assertEqual(self.offered[3][1], [0, 1])
        folder = self.requests("UpdateDialogFilterRequest")[0].filter
        self.assertEqual((folder.id, folder.title.text), (5, "Close people"))
        self.assertTrue(folder.contacts and folder.bots)
        self.assertEqual(peer_ids(folder.pinned_peers), [2])
        self.assertEqual(peer_ids(folder.exclude_peers), [98])
        # Ali was unticked, the group ticked, and the unseen chat left where it was.
        self.assertEqual(sorted(peer_ids(folder.include_peers)), sorted([TEAM_ID, 99]))

    def test_folder_that_nothing_could_be_in_is_refused(self):
        self.script(picks=[0], ticks=[self.rules("exclude_read"), []])
        FakeChooser.values = ["Empty"]
        self.frame.on_folders_menu(None)
        self.assertTrue(pump(lambda: self.boxes[-1:] == [self.text(c.ERR_FOLDER_EMPTY_KEY)]))
        self.assertEqual(self.requests("UpdateDialogFilterRequest"), [])

    def test_deleting_the_folder_on_show_falls_back_to_a_view_that_exists(self):
        FakeTelegramClient.folders = [types.DialogFilter(
            id=5, title=types.TextWithEntities("Old", []), contacts=True,
            pinned_peers=[], include_peers=[], exclude_peers=[]
        )]
        self.manager.load_folders(self.frame.on_ui_thread(self.frame.show_folders))
        self.assertTrue(pump(lambda: len(self.frame.views) == 4))
        self.frame.cycle_view(-1)
        self.assertEqual(self.frame.view_index, 3)

        self.script(picks=[1, 1])
        self.frame.on_folders_menu(None)
        self.assertTrue(pump(lambda: len(self.frame.views) == 3))
        self.assertIsNone(self.requests("UpdateDialogFilterRequest")[0].filter)
        self.assertEqual(self.frame.view_index, 2)

    def test_every_unread_chat_is_marked_read_after_a_yes(self):
        self.box_answer = wx.NO
        self.frame.on_mark_all_read_menu(None)
        pump(timeout=0.2)
        self.assertEqual(self.calls("read"), [])
        self.assertIn("2", self.boxes[-1])

        self.box_answer = wx.YES
        self.frame.on_mark_all_read_menu(None)
        self.assertTrue(pump(lambda: sorted(self.calls("read")) == sorted([("read", 1), ("read", TEAM_ID)])))
        self.assertEqual([dialog["unread"] for dialog in self.frame.all_dialogs], [0, 0, 0])
        self.assertEqual(self.spoken[-1], self.text(c.MSG_ALL_READ_KEY))
        self.frame.on_mark_all_read_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NOTHING_UNREAD_KEY))

    def test_voice_speed_steps_round_is_kept_and_reaches_the_player(self):
        speeds = list(c.VOICE_SPEEDS)
        for expected in speeds[1:] + speeds[:1]:
            self.frame.on_voice_speed_menu(None)
            self.assertEqual(self.frame.settings.get(s.SETTING_VOICE_SPEED), expected)
            self.assertIn(self.text(expected), self.spoken[-1])
        self.frame.on_voice_speed_menu(None)
        self.assertEqual(s.Settings().get(s.SETTING_VOICE_SPEED), speeds[1])
        with mock.patch.object(self.frame.player, "play") as play:
            self.frame.play_voice("note.oga")
        self.assertEqual(play.call_args.kwargs["speed"], 1.5)

    def test_report_follows_the_questions_telegram_asks(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(0)
        FakeChooser.selection = 0
        self.frame.on_report_menu(None)
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.text(c.MSG_REPORTED_KEY)]))
        self.assertEqual([request.option for request in self.requests("ReportRequest")], [b"", b"spam"])
        self.assertEqual(self.requests("ReportRequest")[0].id, [1])
        self.assertEqual(FakeChooser.last_choices, ["Spam", "Other"])

    def test_reason_that_needs_explaining_asks_for_the_words(self):
        self.open_chat(0)
        self.frame.messages_list.SetSelection(1)
        FakeChooser.selection = 1
        FakeChooser.values = ["keeps sending adverts"]
        self.frame.on_report_menu(None)
        self.assertTrue(pump(lambda: len(self.requests("ReportRequest")) == 3))
        last = self.requests("ReportRequest")[2]
        self.assertEqual((last.option, last.message, last.id), (b"other", "keeps sending adverts", [2]))
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.text(c.MSG_REPORTED_KEY)]))


@unittest.skipUnless(audio.AVAILABLE, "needs the audio packages")
class VoiceSpeedTest(unittest.TestCase):
    def test_faster_playback_is_shorter_but_sounds_as_high(self):
        path = os.path.join(tempfile.mkdtemp(), "tone.oga")
        seconds = numpy.arange(audio.SAMPLE_RATE * 2) / audio.SAMPLE_RATE
        audio.encode_voice((numpy.sin(2 * numpy.pi * 440 * seconds) * 8000).astype("int16"), path)

        def pitch(samples):
            return int(numpy.argmax(numpy.abs(numpy.fft.rfft(samples[:audio.SAMPLE_RATE]))))

        normal, fast = audio.decode(path), audio.decode(path, 2.0)
        self.assertAlmostEqual(len(normal) / audio.SAMPLE_RATE, 2.0, delta=0.1)
        self.assertAlmostEqual(len(fast) / audio.SAMPLE_RATE, 1.0, delta=0.1)
        self.assertEqual(pitch(normal), 440)
        self.assertEqual(pitch(fast), 440)
