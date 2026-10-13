"""Files sent to the program from Windows' "Send to" menu: from the command line to the chosen chat."""
import ctypes
import os
import tempfile
import unittest
from unittest import mock

import core.constants as c
import core.share as share
from core.i18n import I18NManager
from tests.harness import FakeChooser, WindowTestCase, get_app, make_channel, make_message, make_user, pump
from ui.background import WM_HOTKEY, BackgroundWindow

ALI = make_user(1, "Ali")
MONA = make_user(2, "Mona")
NEWS = make_channel(3, "News")


class ShareNotesTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        patch = mock.patch.object(share, "SHARE_INBOX_DIR", os.path.join(self.folder, "inbox"))
        patch.start()
        self.addCleanup(patch.stop)

    def file(self, name):
        path = os.path.join(self.folder, name)
        with open(path, "w") as new_file:
            new_file.write("x")
        return path

    def test_only_files_are_taken_from_the_command_line(self):
        report = self.file("report.pdf")
        self.assertEqual(
            share.files_among([c.BACKGROUND_FLAG, report, self.folder, os.path.join(self.folder, "gone.txt")]),
            [report]
        )

    def test_what_one_copy_leaves_the_other_collects_once(self):
        self.assertEqual(share.collect(), [])
        first, second = self.file("one.txt"), self.file("two.txt")
        share.leave([first])
        share.leave([second, os.path.join(self.folder, "gone.txt")])
        self.assertEqual(sorted(share.collect()), [first, second])
        self.assertEqual(share.collect(), [])

    def test_a_damaged_note_is_passed_over(self):
        os.makedirs(share.SHARE_INBOX_DIR)
        with open(os.path.join(share.SHARE_INBOX_DIR, "bad.json"), "w") as note:
            note.write("{not json")
        kept = self.file("kept.txt")
        share.leave([kept])
        self.assertEqual(share.collect(), [kept])


class RunningCopyTest(unittest.TestCase):
    def test_the_running_copy_hears_that_files_were_left_for_it(self):
        get_app()
        heard = []
        window = BackgroundWindow(
            I18NManager("ar"), lambda: heard.append("show"), lambda: None, "", lambda: heard.append("files")
        )
        self.addCleanup(window.shut_down)
        # What a second copy posts, as ask_running_copy_to_take_files does once it finds the window.
        ctypes.windll.user32.PostMessageW(window.GetHandle(), WM_HOTKEY, c.SHARE_HOTKEY_ID, 0)
        self.assertTrue(pump(lambda: heard == ["files"]))
        ctypes.windll.user32.PostMessageW(window.GetHandle(), WM_HOTKEY, c.SHOW_HOTKEY_ID, 0)
        self.assertTrue(pump(lambda: heard == ["files", "show"]))


class ShareWindowTest(WindowTestCase):
    chats = [(ALI, 0, False), (MONA, 0, False), (NEWS, 0, False)]
    history = {1: [make_message(1, "hello", sender=ALI)]}

    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, FakeChooser, "selections", [])

    def sent(self):
        return self.calls("send_file")

    def test_files_go_to_the_chat_that_is_chosen_without_entering_it(self):
        FakeChooser.selections = [1]
        FakeChooser.values = ["look"]
        self.frame.share_files(["notes.pdf"])
        self.assertEqual(FakeChooser.last_message.count("notes.pdf"), 1)
        self.assertTrue(pump(lambda: len(self.sent()) == 1))
        self.assertEqual(self.sent()[0], ("send_file", 2, "notes.pdf", "look", False, None))
        self.assertIsNone(self.frame.current_dialog_id)
        self.assertTrue(pump(lambda: not self.frame.is_busy))
        self.assertEqual(self.spoken[-1], self.text(c.MSG_FILE_SENT_KEY))

    def test_several_chats_get_the_same_files_one_after_another_with_one_caption(self):
        FakeChooser.selections = [0, 1]
        FakeChooser.values = ["look"]
        self.frame.share_files(["notes.pdf", "more.pdf"])
        self.assertTrue(pump(lambda: len(self.sent()) == 2 and not self.frame.is_busy))
        self.assertEqual(
            [call[1:5] for call in self.sent()],
            [(1, ["notes.pdf", "more.pdf"], "look", False), (2, ["notes.pdf", "more.pdf"], "look", False)]
        )
        # Asked once what goes with them, and told once that they went.
        self.assertEqual(FakeChooser.values, [])
        self.assertEqual(self.spoken[-1], self.text(c.MSG_SHARED_TO_CHATS_FORMAT_KEY).format(count=2))
        self.assertEqual(self.frame.all_dialogs[0]["id"], 2)

    def test_ticking_no_chat_sends_nothing(self):
        FakeChooser.selections = []
        self.frame.share_files(["notes.pdf"])
        pump(timeout=0.1)
        self.assertEqual(self.sent(), [])
        self.assertFalse(self.frame.is_busy)

    def test_only_chats_this_account_may_write_in_are_offered(self):
        FakeChooser.confirmed = False
        self.frame.share_files(["notes.pdf"])
        # A channel somebody else owns takes nothing from a subscriber.
        self.assertEqual(FakeChooser.last_choices, ["Ali", "Mona"])
        pump(timeout=0.1)
        self.assertEqual(self.sent(), [])

    def test_files_for_another_chat_are_not_an_answer_in_the_open_one(self):
        self.open_chat(0)
        self.frame.set_compose(reply_to=self.frame.messages[0])
        FakeChooser.selections = [1]
        FakeChooser.values = [""]
        self.frame.share_files(["notes.pdf"])
        self.assertTrue(pump(lambda: len(self.sent()) == 1))
        self.assertEqual(self.sent()[0][1], 2)
        self.assertIsNone(self.sent()[0][5])
        # The answer being written stays for what is sent in the open chat.
        self.assertIsNotNone(self.frame.reply_to)

    def test_files_wait_for_the_chat_list_and_for_a_transfer_to_end(self):
        chats, self.frame.all_dialogs = self.frame.all_dialogs, []
        FakeChooser.last_message = None
        self.frame.share_files(["early.pdf"])
        self.assertIsNone(FakeChooser.last_message)
        self.assertEqual(self.frame.shared_paths, ["early.pdf"])
        FakeChooser.selections = [0]
        FakeChooser.values = [""]
        self.frame.show_dialogs(chats)
        self.assertTrue(pump(lambda: len(self.sent()) == 1))
        self.assertEqual(self.sent()[0][1:3], (1, "early.pdf"))
        self.assertEqual(self.frame.shared_paths, [])

        self.assertTrue(pump(lambda: not self.frame.is_busy))
        self.frame.is_busy = True
        self.frame.share_files(["late.pdf"])
        self.assertEqual(self.spoken[-1], self.text(c.MSG_SHARE_BUSY_KEY))
        self.frame.is_busy = False
        pump(timeout=0.1)
        self.assertEqual(len(self.sent()), 1)
