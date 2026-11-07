"""The clipboard, when another program holds it for a moment, or for longer: tried again, quietly,
and if it stays taken, the user is told in the app's own words instead of wx's English error box."""
import unittest
from unittest import mock

import wx

import core.constants as c
from tests.harness import WindowTestCase, get_app, make_message, make_user
from ui import clipboard

ALI = make_user(1, "Ali")


class BusyClipboard:
    """wx's clipboard as another program holds it for the first `busy` tries, refusing its data
    `refuse_data` times once open."""

    def __init__(self, busy, refuse_data=0, files=()):
        self.busy = busy
        self.refuse_data = refuse_data
        self.files = files
        self.opened = 0

    def Open(self):
        self.opened += 1
        return self.opened > self.busy

    def Close(self):
        pass

    def IsSupported(self, data_format):
        return data_format.GetType() == wx.DF_FILENAME and bool(self.files)

    def GetData(self, data):
        if self.refuse_data:
            self.refuse_data -= 1
            return False
        for path in self.files:
            data.AddFile(path)
        return True


class ClipboardTest(unittest.TestCase):
    def setUp(self):
        get_app()
        sleep = mock.patch.object(clipboard.time, "sleep")
        self.slept = sleep.start()
        self.addCleanup(sleep.stop)

    def held_for(self, tries):
        """Another program holds the clipboard for the first `tries` tries."""
        answers = [False] * tries
        real = clipboard.try_open
        patch = mock.patch.object(clipboard, "try_open", lambda: answers.pop(0) if answers else real())
        patch.start()
        self.addCleanup(patch.stop)

    def test_text_goes_on_and_comes_back(self):
        self.assertTrue(clipboard.put_text("سلام hello\nline two"))
        self.assertEqual(clipboard.get_text(), "سلام hello\nline two")

    def test_held_for_a_moment_it_is_tried_again_until_it_is_free(self):
        self.held_for(3)
        self.assertTrue(clipboard.put_text("after a wait"))
        self.assertEqual(self.slept.call_count, 3)
        self.assertEqual(clipboard.get_text(), "after a wait")

    def test_held_all_along_it_gives_up(self):
        self.held_for(99)
        self.assertFalse(clipboard.put_text("never"))
        self.assertIsNone(clipboard.get_text())
        self.assertEqual(self.slept.call_count, 2 * (clipboard.TRIES - 1))

    def test_files_are_read_through_wx_patiently_and_without_its_error_box(self):
        board = BusyClipboard(busy=2, refuse_data=1, files=["C:\\a.pdf"])
        read = lambda board: list(files.GetFilenames()) if board.GetData(files := wx.FileDataObject()) else None
        with mock.patch.object(wx, "TheClipboard", board), \
                mock.patch.object(wx, "LogNull", wraps=wx.LogNull) as quiet:
            self.assertEqual(clipboard.use(read), ["C:\\a.pdf"])
        quiet.assert_called()
        # Twice taken, once refused the data, then read.
        self.assertEqual(board.opened, 4)
        with mock.patch.object(wx, "TheClipboard", BusyClipboard(busy=99)):
            self.assertIsNone(clipboard.use(read))


class ClipboardInTheWindowTest(WindowTestCase):
    chats = [(ALI, 0, False)]
    history = {1: [make_message(1, "hello there", sender=ALI)]}

    def setUp(self):
        super().setUp()
        sleep = mock.patch.object(clipboard.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        self.open_chat(0)
        self.frame.messages_list.SetSelection(0)

    def test_a_copy_is_said_and_can_be_pasted(self):
        self.frame.on_copy_message(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_COPIED_KEY))
        self.assertEqual(clipboard.get_text(), "hello there")

    def test_a_copy_that_cannot_get_in_says_so(self):
        with mock.patch.object(clipboard, "try_open", lambda: False):
            self.frame.on_copy_message(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_CLIPBOARD_BUSY_KEY))

    def test_a_paste_that_cannot_get_in_leaves_the_field_to_windows(self):
        with mock.patch.object(wx, "TheClipboard", BusyClipboard(busy=99)):
            self.assertFalse(self.frame.paste_files())
