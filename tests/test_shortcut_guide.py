"""The shortcuts guide: shown in the app, and saved as a web page or as text."""
import html
import os
import tempfile
from unittest import mock

import wx

import core.constants as c
import core.shortcuts as shortcuts
from core import shortcut_guide
from tests.harness import WindowTestCase, make_user

ALI = make_user(1, "Ali")


class ShortcutGuideTest(WindowTestCase):
    chats = [(ALI, 0, False)]

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp()

    def read(self, path, encoding="utf-8"):
        with open(path, encoding=encoding) as guide_file:
            return guide_file.read()

    def test_the_web_page_has_a_heading_and_a_table_for_each_menu(self):
        path = self.frame.write_shortcuts_guide(os.path.join(self.folder, "guide"), ".html")
        self.assertTrue(path.endswith(".html"))
        page = self.read(path)
        self.assertIn('dir="rtl"', page)
        self.assertIn('lang="ar"', page)
        intro, sections = self.frame.shortcuts_guide()
        for title, rows in sections:
            self.assertIn("<h2>%s</h2>" % html.escape(title), page)
        self.assertIn("<kbd>F1</kbd>", page)
        self.assertIn(html.escape(self.text(c.MENU_REPLY_KEY)), page)
        self.assertEqual(page.count("<table>"), len(sections))
        self.assertIn(self.text(c.MSG_GUIDE_EXPORTED_FORMAT_KEY).format(path=path), self.spoken)

    def test_the_text_file_is_what_the_window_shows(self):
        path = self.frame.write_shortcuts_guide(os.path.join(self.folder, "guide.txt"), ".html")
        self.assertTrue(path.endswith("guide.txt"))
        with open(path, "rb") as raw:
            # So Notepad reads Arabic as Arabic.
            self.assertTrue(raw.read(3) == b"\xef\xbb\xbf")
        self.assertEqual(self.read(path, "utf-8-sig"), self.frame.shortcuts_text())

    def test_a_changed_shortcut_is_in_the_guide_as_it_is_now(self):
        table = shortcuts.defaults()
        table[c.MENU_REPLY_KEY] = "Ctrl+Alt+F7"
        shortcuts.store(self.frame.settings, table)
        self.frame.apply_shortcuts()
        page = self.read(self.frame.write_shortcuts_guide(os.path.join(self.folder, "guide"), ".html"))
        self.assertIn("<kbd>Ctrl+Alt+F7</kbd>", page)

    def test_export_asks_where_and_saves_the_kind_chosen(self):
        target = os.path.join(self.folder, "mine")

        class Saving:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def ShowModal(self):
                return wx.ID_OK

            def GetPath(self):
                return target

            def GetFilterIndex(self):
                return 1

        with mock.patch.object(wx, "FileDialog", Saving):
            self.frame.on_export_shortcuts_menu(None)
        self.assertTrue(os.path.exists(target + ".txt"))

    def test_html_is_escaped(self):
        page = shortcut_guide.to_html("T", "a <b>", [("Menu", [("Ctrl+<", "x & y")])], "en", "ltr", "Key", "Command")
        self.assertIn("a &lt;b&gt;", page)
        self.assertIn("<kbd>Ctrl+&lt;</kbd>", page)
        self.assertIn("x &amp; y", page)
