"""How a right-to-left row is drawn: its numbers alike and in their order, a file's name kept apart, and
none of the marks that do it in the words the rest of the program, type-ahead and screen readers read."""
import unittest

import wx

from tests.harness import get_app
from ui import avatars
from ui.chat_rows import ChatRows, LEFT_TO_RIGHT_MARK, RIGHT_TO_LEFT_MARK, for_right_to_left


class RowDrawingTest(unittest.TestCase):
    def test_each_number_is_marked_whole_and_closed(self):
        drawn = for_right_to_left("رسالة صوتية، 0:12، 29.3 كيلوبايت، 19:52")
        for number in ("0:12", "29.3", "19:52"):
            self.assertIn(LEFT_TO_RIGHT_MARK + number + RIGHT_TO_LEFT_MARK, drawn)
        # A number is marked once, not each of its digits.
        self.assertEqual(drawn.count(LEFT_TO_RIGHT_MARK), 3)

    def test_a_file_name_is_closed_but_a_size_is_no_file_name(self):
        drawn = for_right_to_left("مستند، التقرير.pdf، 8.6 ميجابايت")
        self.assertIn("التقرير.pdf" + RIGHT_TO_LEFT_MARK, drawn)
        self.assertNotIn("8.6" + RIGHT_TO_LEFT_MARK + RIGHT_TO_LEFT_MARK, drawn)

    def test_the_words_read_back_are_the_words_written(self):
        get_app()
        frame = wx.Frame(None)
        self.addCleanup(frame.Destroy)
        frame.SetLayoutDirection(wx.Layout_RightToLeft)
        rows = ChatRows(frame)
        text = "أنت: [التقرير.pdf، 244 كيلوبايت]، 19:52"
        rows.Set([text])
        rows.SetString(0, text + " 2")
        rows.Insert(text, 1)
        self.assertEqual(rows.GetStrings(), [text + " 2", text])
        # What Windows is given to draw carries the marks.
        self.assertIn(LEFT_TO_RIGHT_MARK, rows.GetItemText(1))

    def test_left_to_right_rows_are_left_as_written(self):
        get_app()
        frame = wx.Frame(None)
        self.addCleanup(frame.Destroy)
        rows = ChatRows(frame)
        rows.Set(["report.pdf, 244 KB, 19:52"])
        self.assertEqual(rows.GetItemText(0), "report.pdf, 244 KB, 19:52")


class DeletedPictureTest(unittest.TestCase):
    def test_a_deleted_account_has_its_own_grey_picture(self):
        get_app()
        pictures = avatars.ChatPictures("unused", 32)
        deleted = pictures.index_for({"id": 5, "title": "حساب محذوف", "deleted": True})
        other = pictures.index_for({"id": 6, "title": "حساب محذوف"})
        self.assertNotEqual(deleted, other)
        self.assertEqual(pictures.indexes[5][1], avatars.DELETED_COLOUR)
