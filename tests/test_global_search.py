"""Searching all of Telegram: loosely, in a window of its own, with more on asking."""
import unittest
from unittest import mock

import wx
from telethon.tl import types

import core.constants as c
from core import global_search
from tests.harness import NOW, FakeTelegramClient, WindowTestCase, make_user, pump
from ui.global_search_dialog import GlobalSearchDialog

ALI = make_user(1, "Ali")


def channel(channel_id, title, members=None):
    return types.Channel(
        id=channel_id, title=title, photo=None, date=NOW, broadcast=True, left=True, access_hash=1,
        participants_count=members
    )


class QueriesTest(unittest.TestCase):
    def test_each_round_asks_more_loosely_and_never_twice(self):
        asked = [global_search.queries("أحمد سامي", round_number) for round_number in range(global_search.ROUNDS)]
        self.assertIn("أحمد سامي", asked[0])
        self.assertIn("احمد سامي", asked[0])
        self.assertIn("سامي", asked[1])
        self.assertIn("أحم", asked[2])
        everything = [query for round_queries in asked for query in round_queries]
        self.assertEqual(len(everything), len(set(everything)))
        self.assertEqual(global_search.queries("أحمد", global_search.ROUNDS), [])

    def test_nearest_first_then_the_biggest(self):
        found = [
            {"title": "Daily news digest", "members": 50},
            {"title": "News", "members": 10},
            {"title": "Newsroom", "members": 5000},
            {"title": "Other", "username": "news_now", "members": 1},
        ]
        titles = [chat["title"] for chat in global_search.ranked(found, "news")]
        self.assertEqual(titles, ["News", "Newsroom", "Other", "Daily news digest"])

    def test_arabic_is_near_with_or_without_hamza_and_marks(self):
        self.assertEqual(global_search.nearness({"title": "أحمد"}, "احمد"), 1.0)
        self.assertEqual(global_search.nearness({"title": "مُصْطَفى"}, "مصطفي"), 1.0)


class SearchWindowTest(WindowTestCase):
    chats = [(ALI, 0, False)]

    def setUp(self):
        super().setUp()
        FakeTelegramClient.public.update(
            news=channel(51, "News", 10), newsroom=channel(52, "Newsroom", 900),
            # Found only by the start of the word: "new".
            new_age=channel(53, "New age"),
        )
        self.dialog = GlobalSearchDialog(self.frame, self.i18n, self.manager, self.frame.add_joined_chat)
        self.addCleanup(self.dialog.Destroy)

    def search(self, text):
        self.dialog.search_input.SetValue(text)
        self.dialog.search()
        self.assertTrue(pump(lambda: not self.dialog.busy and self.dialog.round > 0))

    def titles(self):
        return [chat["title"] for chat in self.dialog.results]

    def test_results_stay_out_of_the_chat_list(self):
        self.search("news")
        self.assertEqual(self.titles(), ["News", "Newsroom"])
        self.assertIn("900", self.dialog.results_list.GetString(1))
        self.assertEqual([dialog["title"] for dialog in self.frame.all_dialogs], ["Ali"])

    def test_show_more_searches_more_loosely_and_adds_to_the_list(self):
        self.search("news")
        self.dialog.search_more()
        self.assertTrue(pump(lambda: not self.dialog.busy))
        while self.dialog.more_button.IsEnabled():
            self.dialog.search_more()
            self.assertTrue(pump(lambda: not self.dialog.busy))
        self.assertIn("New age", self.titles())
        self.assertEqual(self.titles()[:2], ["News", "Newsroom"])
        self.assertEqual(len(self.titles()), len(set(self.titles())))

    def test_joining_from_the_window_puts_the_chat_in_the_list(self):
        self.search("newsroom")
        self.dialog.results_list.SetSelection(0)
        self.dialog.join_result()
        self.assertTrue(pump(lambda: self.frame.find_known_dialog(self.dialog.results[0]["id"]) is not None))
        joined = self.frame.find_known_dialog(self.dialog.results[0]["id"])
        self.assertTrue(joined["joined"])
        self.assertIn(self.text(c.SEARCH_ROW_JOINED_KEY), self.dialog.results_list.GetString(0))

    def choose_filter(self, name):
        self.dialog.filter_choice.SetSelection(list(c.SEARCH_FILTERS).index(name))
        self.dialog.on_filter_changed()

    def test_the_kind_chosen_narrows_what_was_found_at_once(self):
        FakeTelegramClient.public["news_bot"] = make_user(70, "News bot", bot=True)
        FakeTelegramClient.public["newsgroup"] = types.Channel(
            id=54, title="News group", photo=None, date=NOW, megagroup=True, broadcast=False, left=True, access_hash=1
        )
        self.search("news")
        self.assertEqual(set(self.titles()), {"News", "Newsroom", "News bot", "News group"})
        self.choose_filter("SEARCH_FILTER_GROUPS")
        self.assertEqual(self.titles(), ["News group"])
        self.choose_filter("SEARCH_FILTER_BOTS")
        self.assertEqual(self.titles(), ["News bot"])
        self.choose_filter("SEARCH_FILTER_PEOPLE")
        self.assertEqual(self.titles(), [])
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NO_RESULTS_OF_KIND_KEY))
        self.choose_filter("SEARCH_FILTER_ALL")
        self.assertEqual(len(self.titles()), 4)

    def test_a_kind_chosen_before_searching_looks_further_until_it_finds_one(self):
        self.choose_filter("SEARCH_FILTER_CHANNELS")
        self.dialog.search_input.SetValue("new")
        self.dialog.search()
        self.assertTrue(pump(lambda: not self.dialog.busy and self.dialog.round > 0))
        self.assertTrue(self.titles())
        self.assertTrue(all(chat["category"] == c.CATEGORY_BROADCASTS for chat in self.dialog.results))

    def test_a_person_cannot_be_joined(self):
        FakeTelegramClient.public["zed"] = make_user(9, "Zed", contact=False)
        self.search("zed")
        self.dialog.results_list.SetSelection(0)
        self.dialog.join_result()
        self.assertEqual(self.spoken[-1], self.text(c.MSG_CANNOT_JOIN_PERSON_KEY))

    def test_enter_on_a_result_opens_it(self):
        self.search("news")
        self.dialog.results_list.SetSelection(1)
        with mock.patch.object(self.dialog, "EndModal") as end:
            event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
            event.SetKeyCode(wx.WXK_RETURN)
            with mock.patch.object(wx.Window, "FindFocus", return_value=self.dialog.results_list):
                self.dialog.on_char_hook(event)
        end.assert_called_once_with(wx.ID_OK)
        self.assertEqual(self.dialog.chosen["title"], "Newsroom")
