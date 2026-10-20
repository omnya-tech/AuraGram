"""Several accounts on one computer: where each is kept, and going from one to another."""
import unittest

import core.constants as c
import core.settings as s
from core import accounts
from tests.harness import FakeChooser, WindowTestCase


class AccountListTest(unittest.TestCase):
    def test_the_first_account_keeps_the_usual_session_and_the_others_get_numbers(self):
        self.assertEqual(accounts.session_path(0), c.SESSION_NAME)
        self.assertEqual(accounts.session_path(2), c.SESSION_NAME + "_2")

    def test_a_new_account_gets_a_number_none_has(self):
        self.assertEqual(accounts.next_id([], 0), 1)
        self.assertEqual(accounts.next_id([{"id": 0}, {"id": 3}], 0), 4)

    def test_signing_in_again_updates_the_name_and_signing_out_forgets_it(self):
        listed = accounts.remember([], 0, "Omnya", "+201000")
        listed = accounts.remember(listed, 1, "Work", "+966500")
        listed = accounts.remember(listed, 0, "Omnya Tech", "+201000")
        self.assertEqual([(account["id"], account["name"]) for account in listed], [(0, "Omnya Tech"), (1, "Work")])
        self.assertEqual(accounts.forget(listed, 0), [{"id": 1, "name": "Work", "phone": "+966500"}])


class AccountsMenuTest(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.switched = []
        self.frame.on_switch_account = self.switched.append
        self.frame.settings.set(s.SETTING_ACCOUNTS, [
            {"id": 0, "name": "Omnya", "phone": "+201000"}, {"id": 1, "name": "Work", "phone": "+966500"},
        ])

    def test_the_accounts_are_offered_with_the_one_in_use_marked(self):
        FakeChooser.selection = 1
        self.frame.on_accounts_menu(None)
        row = lambda name, phone: self.text(c.ACCOUNT_ROW_FORMAT_KEY).format(name=name, phone=phone)
        self.assertEqual(FakeChooser.last_choices, [
            self.text(c.ACCOUNT_CURRENT_FORMAT_KEY).format(row=row("Omnya", "+201000")),
            row("Work", "+966500"), self.text(c.ACCOUNT_ADD_KEY),
        ])
        self.assertEqual(self.switched, [1])

    def test_choosing_the_one_in_use_does_nothing_and_adding_asks_for_a_new_one(self):
        FakeChooser.selection = 0
        self.frame.on_accounts_menu(None)
        self.assertEqual(self.switched, [])
        FakeChooser.selection = 2
        self.frame.on_accounts_menu(None)
        self.assertEqual(self.switched, [None])

    def test_an_account_not_signed_in_yet_still_shows(self):
        self.frame.settings.set(s.SETTING_CURRENT_ACCOUNT, 5)
        FakeChooser.selection = 0
        self.frame.on_accounts_menu(None)
        self.assertIn(self.text(c.ACCOUNT_UNNAMED_KEY), FakeChooser.last_choices[2])

    def test_the_list_is_kept_and_a_bad_one_is_ignored(self):
        self.frame.settings.save()
        self.assertEqual(len(s.Settings().get(s.SETTING_ACCOUNTS)), 2)
        settings = s.Settings()
        settings.take({s.SETTING_ACCOUNTS: [{"id": "x"}], s.SETTING_CURRENT_ACCOUNT: -1})
        self.assertEqual(len(settings.get(s.SETTING_ACCOUNTS)), 2)
        self.assertEqual(settings.get(s.SETTING_CURRENT_ACCOUNT), 0)
