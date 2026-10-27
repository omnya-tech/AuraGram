"""The program's own small files: written all or nothing, and read back without failing on a damaged one."""
import json
import os
import tempfile
import unittest
from unittest import mock

import core.reminders
from core import files


class WriteJsonTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.path = os.path.join(self.folder, "settings.json")

    def read(self):
        with open(self.path, encoding="utf-8") as file:
            return json.load(file)

    def test_the_file_is_written_whole(self):
        files.write_json(self.path, {"a": 1}, indent=4)
        self.assertEqual(self.read(), {"a": 1})
        self.assertEqual(os.listdir(self.folder), ["settings.json"])

    def test_a_write_that_fails_halfway_leaves_the_file_as_it_was(self):
        files.write_json(self.path, {"accounts": [1, 2]})

        def full_disk(data, file, **arguments):
            file.write('{"accounts": [')
            raise OSError(28, "No space left on device")
        with mock.patch.object(files.json, "dump", full_disk):
            with self.assertRaises(OSError):
                files.write_json(self.path, {"accounts": [1, 2, 3]})
        self.assertEqual(self.read(), {"accounts": [1, 2]})
        # Nothing half-written is left beside it either.
        self.assertEqual(os.listdir(self.folder), ["settings.json"])


class RemindersFileTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "reminders.json")
        patch = mock.patch.object(core.reminders, "REMINDERS_FILE", self.path)
        patch.start()
        self.addCleanup(patch.stop)

    def load(self, text):
        with open(self.path, "w", encoding="utf-8") as file:
            file.write(text)
        return core.reminders.load()

    def reminder(self, due):
        return {"chat_id": 1, "chat_title": "A", "message_id": 2, "text": "hi", "due": due}

    def test_a_file_that_holds_no_list_gives_no_reminders(self):
        for text in ("7", '"text"', "{}", "null", "{broken"):
            # Each is logged, as it should be; caught here rather than printed among the test results.
            with self.assertLogs("core.reminders", level="WARNING"):
                self.assertEqual(self.load(text), [], text)

    def test_a_damaged_reminder_is_left_out_and_the_others_kept(self):
        good = self.reminder("2026-10-27T09:00:00+03:00")
        stored = [good, self.reminder("not a time"), self.reminder(5), self.reminder("2026-10-27T09:00:00"), "x"]
        self.assertEqual(self.load(json.dumps(stored)), [good])

    def test_saved_reminders_come_back(self):
        saved = [self.reminder("2026-10-28T09:00:00+03:00"), self.reminder("2026-10-27T09:00:00+03:00")]
        core.reminders.save(saved)
        self.assertEqual(core.reminders.load(), list(reversed(saved)))
