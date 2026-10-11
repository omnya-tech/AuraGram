"""Knowing whether Telegram is reachable, and saying so on the tray icon."""
import unittest
from unittest import mock

import core.constants as c
import core.telegram_client as telegram_client
from core.i18n import I18NManager
from tests.harness import get_app, pump
from ui.background import TrayIcon


class FlakyClient:
    """Telegram over a line the test can cut: `reachable` is whether anything gets through."""

    reachable = True
    connects = 0

    def __init__(self, *args, **kwargs):
        self.connected = False

    def add_event_handler(self, handler, event):
        pass

    def is_connected(self):
        return self.connected

    async def connect(self):
        if not FlakyClient.reachable:
            raise ConnectionError("no route")
        FlakyClient.connects += 1
        self.connected = True

    async def disconnect(self):
        self.connected = False

    async def is_user_authorized(self):
        return True

    async def __call__(self, request):
        if not FlakyClient.reachable:
            # What Telethon ends up doing once its own retries run out.
            self.connected = False
            raise ConnectionError("connection lost")


class ConnectionWatchTest(unittest.TestCase):
    def setUp(self):
        FlakyClient.reachable = True
        FlakyClient.connects = 0
        self.states = []
        for patch in (
            mock.patch.object(telegram_client, "TelegramClient", FlakyClient),
            mock.patch.object(telegram_client, "CONNECTION_WATCH_SECONDS", 0.01),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.manager = telegram_client.TelegramManager(lambda step, error_key=None: None)
        self.manager.set_connection_listener(self.states.append)
        self.manager.start()
        self.addCleanup(self.manager.stop)

    def test_reports_only_changes_and_reconnects_when_the_line_is_back(self):
        self.assertTrue(pump(lambda: self.states == [c.CONNECTION_ONLINE]))
        # Several checks pass while nothing changes: still one report.
        pump(timeout=0.1)
        self.assertEqual(self.states, [c.CONNECTION_ONLINE])

        FlakyClient.reachable = False
        self.assertTrue(pump(lambda: self.states == [c.CONNECTION_ONLINE, c.CONNECTION_OFFLINE]))

        FlakyClient.reachable = True
        self.assertTrue(pump(lambda: self.states[-1] == c.CONNECTION_ONLINE and len(self.states) == 3))
        self.assertEqual(FlakyClient.connects, 2)

    def test_stopping_does_not_connect_again(self):
        self.assertTrue(pump(lambda: self.states == [c.CONNECTION_ONLINE]))
        self.manager.stop()
        self.assertFalse(self.manager.client.is_connected())
        self.assertEqual(FlakyClient.connects, 1)


class TrayStatusTest(unittest.TestCase):
    def setUp(self):
        get_app()
        self.i18n = I18NManager("ar")
        self.tray = TrayIcon(self.i18n, lambda: None, lambda: None)
        self.addCleanup(self.tray.Destroy)
        self.addCleanup(self.tray.RemoveIcon)

    def status(self, state):
        return "AuraGram: " + self.i18n.get_string(c.CONNECTION_STATE_KEYS[state])

    def test_starts_as_connecting_then_follows_the_connection(self):
        self.assertEqual(self.tray.status_text, self.status(c.CONNECTION_CONNECTING))
        for state in (c.CONNECTION_ONLINE, c.CONNECTION_OFFLINE):
            self.tray.set_connection_state(state)
            self.assertEqual(self.tray.status_text, self.status(state))

    def test_every_state_has_its_own_text(self):
        texts = {self.i18n.get_string(key) for key in c.CONNECTION_STATE_KEYS.values()}
        self.assertEqual(len(texts), len(c.CONNECTION_STATE_KEYS))
        self.assertNotIn("", texts)

    def test_menu_opens_with_the_state_as_a_line_that_cannot_be_chosen(self):
        self.tray.set_connection_state(c.CONNECTION_OFFLINE)
        menu = self.tray.CreatePopupMenu()
        self.addCleanup(menu.Destroy)
        first = menu.GetMenuItems()[0]
        self.assertEqual(first.GetItemLabelText(), self.status(c.CONNECTION_OFFLINE))
        self.assertFalse(first.IsEnabled())
