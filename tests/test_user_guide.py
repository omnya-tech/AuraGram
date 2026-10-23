"""The user guide: every command is in it, in each language, with the user's shortcuts as they are."""
import os
import tempfile
import unittest
from unittest import mock

import core.constants as c
import core.shortcuts as shortcuts
from core import user_guide
from tests.harness import WindowTestCase


def template(language):
    with open(user_guide.template_path(language), encoding="utf-8") as file:
        return file.read()


class GuideTextTest(unittest.TestCase):
    def test_every_command_is_explained_in_every_language_and_nothing_else_is_named(self):
        commands = set(shortcuts.COMMANDS)
        for language in c.LANGUAGES:
            named = user_guide.placeholders(template(language))
            self.assertEqual(named - commands, set(), language)
            # A command added to the app without a word in the guide is caught here.
            self.assertEqual(commands - named, set(), language)

    def test_shortcuts_are_written_in_where_commands_are_named(self):
        page = user_guide.fill(
            "<p>{{VERSION}}: {{MENU_REPLY}} or {{MENU_EDIT}}</p>", {c.MENU_REPLY_KEY: "Ctrl+R", c.MENU_EDIT_KEY: ""}, "none"
        )
        self.assertEqual(page, '<p>%s: <kbd>Ctrl+R</kbd> or <span class="none">(none)</span></p>' % c.APP_VERSION)

    def test_a_language_without_its_own_guide_gets_the_default_one(self):
        self.assertEqual(user_guide.template_path("xx"), user_guide.template_path(c.DEFAULT_LANG))


class GuideWindowTest(WindowTestCase):
    def test_f1_opens_the_guide_and_shift_f1_the_shortcuts(self):
        table = shortcuts.defaults()
        # A shortcut the user changed: the guide still names the app's own, and says they can be changed.
        changed = dict(table, **{c.MENU_REPLY_KEY: "Ctrl+Alt+F7"})
        shortcuts.store(self.frame.settings, changed)
        self.assertEqual(table[c.MENU_USER_GUIDE_KEY], "F1")
        self.assertEqual(table[c.MENU_SHORTCUTS_KEY], "Shift+F1")
        folder = tempfile.mkdtemp()
        opened = []
        with mock.patch.object(user_guide, "DATA_DIR", folder), \
                mock.patch.object(user_guide.write, "__defaults__", (folder,)), \
                mock.patch.object(os, "startfile", opened.append, create=True):
            self.frame.on_user_guide_menu(None)
        self.assertEqual(len(opened), 1)
        with open(opened[0], encoding="utf-8") as file:
            page = file.read()
        self.assertIn("<kbd>%s</kbd>" % table[c.MENU_REPLY_KEY], page)
        self.assertNotIn("Ctrl+Alt+F7", page)
        self.assertNotIn("{{", page)
        self.assertEqual(os.path.dirname(opened[0]), folder)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_GUIDE_OPENED_KEY))
