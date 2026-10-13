"""Loading more of the chat list: the user is told it started, how far it is while they wait on its row, and that it ended."""
import core.constants as c
from tests.harness import FakeTelegramClient, WindowTestCase, make_user, pump

PAGE = [(make_user(number, "Person %d" % number), 0, False) for number in range(1, c.DIALOGS_LIMIT + 1)]
SECOND_PAGE = [(make_user(number, "Later %d" % number), 0, False) for number in range(1000, 1000 + c.DIALOGS_LIMIT)]
REST = [(make_user(number, "Last %d" % number), 0, False) for number in range(2000, 2050)]


class LoadMoreTest(WindowTestCase):
    chats = PAGE

    def load_more_row(self):
        return len(self.frame.dialogs)

    def press_enter_on_load_more(self):
        self.frame.dialogs_list.SetSelection(self.load_more_row())
        self.spoken.clear()
        self.frame.on_open_dialog(None)

    def progress(self, percent):
        return self.text(c.MSG_MORE_DIALOGS_PROGRESS_FORMAT_KEY).format(percent=percent)

    def loaded(self, count):
        return self.text(c.MSG_MORE_DIALOGS_LOADED_FORMAT_KEY).format(count=count)

    def test_start_progress_and_end_are_told_to_someone_waiting_on_the_row(self):
        FakeTelegramClient.chats = PAGE + SECOND_PAGE + REST
        self.press_enter_on_load_more()
        self.assertEqual(self.spoken, [self.text(c.MSG_LOADING_MORE_DIALOGS_KEY)])
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.loaded(c.DIALOGS_LIMIT)]))
        # Half way through the two pages; the end is the "loaded" line, not "100%".
        self.assertEqual(self.spoken[1:], [self.progress(50), self.loaded(c.DIALOGS_LIMIT)])
        self.assertEqual(len(self.frame.dialogs), 2 * c.DIALOGS_LIMIT)
        # The user is put on the first of the new chats.
        self.assertEqual(self.frame.dialogs_list.GetSelection(), c.DIALOGS_LIMIT)

    def test_one_step_away_the_progress_is_not_spoken_but_the_end_still_is(self):
        FakeTelegramClient.chats = PAGE + SECOND_PAGE + REST
        self.press_enter_on_load_more()
        self.frame.dialogs_list.SetSelection(self.load_more_row() - 1)
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.loaded(c.DIALOGS_LIMIT)]))
        self.assertNotIn(self.progress(50), self.spoken)
        # And the user stays on the chat they moved to.
        self.assertEqual(self.frame.dialogs_list.GetSelection(), c.DIALOGS_LIMIT - 1)

    def test_last_page_says_how_many_came_and_takes_the_row_away(self):
        FakeTelegramClient.chats = PAGE + REST
        self.press_enter_on_load_more()
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.loaded(len(REST))]))
        self.assertEqual(self.frame.dialogs_list.GetCount(), c.DIALOGS_LIMIT + len(REST))

    def test_nothing_more_to_load_is_said_plainly(self):
        self.press_enter_on_load_more()
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.text(c.MSG_NO_MORE_DIALOGS_KEY)]))
        self.assertFalse(self.frame.has_more_dialogs)

    def test_a_second_enter_while_loading_asks_for_nothing_more(self):
        FakeTelegramClient.chats = PAGE + SECOND_PAGE + REST
        self.press_enter_on_load_more()
        self.frame.on_open_dialog(None)
        self.assertEqual(self.frame.dialogs_limit, 2 * c.DIALOGS_LIMIT)
        self.assertTrue(pump(lambda: self.frame.loading_more_from is None))
