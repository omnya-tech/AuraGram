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
    authorized = True
    # What was done to the line, in order.
    steps = []

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
        FlakyClient.steps.append("connect")
        self.connected = True

    async def disconnect(self):
        FlakyClient.steps.append("disconnect")
        self.connected = False

    async def is_user_authorized(self):
        return FlakyClient.authorized

    async def __call__(self, request):
        if not FlakyClient.reachable:
            # What Telethon ends up doing once its own retries run out.
            self.connected = False
            raise ConnectionError("connection lost")


class ConnectionWatchTest(unittest.TestCase):
    def setUp(self):
        FlakyClient.reachable = True
        FlakyClient.connects = 0
        FlakyClient.steps = []
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
        # What Telethon left running from the dropped line is stopped before connecting again.
        self.assertEqual(FlakyClient.steps[0], "connect")
        second = FlakyClient.steps.index("connect", 1)
        self.assertIn("disconnect", FlakyClient.steps[1:second])

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


class FirstConnectionTest(unittest.TestCase):
    """At a start with Windows the network is often not up yet: a signed-in account then waits for it,
    out of sight, instead of failing into the sign-in window."""

    def setUp(self):
        FlakyClient.reachable = False
        FlakyClient.connects = 0
        FlakyClient.steps = []
        self.answers = []
        for patch in (
            mock.patch.object(telegram_client, "TelegramClient", FlakyClient),
            mock.patch.object(telegram_client, "CONNECTION_WATCH_SECONDS", 0.01),
            mock.patch.object(telegram_client, "CONNECT_RETRY_SECONDS", 0.01),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def start(self, wait_for_network):
        manager = telegram_client.TelegramManager(lambda step, error_key=None: self.answers.append((step, error_key)))
        manager.wait_for_network = wait_for_network
        manager.start()
        self.addCleanup(manager.stop)
        return manager

    def test_started_with_windows_it_waits_for_the_network_and_then_signs_in(self):
        self.start(wait_for_network=True)
        pump(timeout=0.2)
        self.assertEqual(self.answers, [])
        FlakyClient.reachable = True
        self.assertTrue(pump(lambda: self.answers == [(c.STEP_DONE, None)]))

    def test_opened_by_hand_it_says_at_once_that_telegram_cannot_be_reached(self):
        # The failure is logged, as it should be; caught here rather than printed among the test results.
        with self.assertLogs("core.telegram_client", level="ERROR"):
            self.start(wait_for_network=False)
            self.assertTrue(pump(lambda: self.answers == [(c.STEP_PHONE, c.ERR_CONNECTION_KEY)]))

    def test_stopping_while_it_waits_ends_the_waiting(self):
        manager = self.start(wait_for_network=True)
        pump(timeout=0.1)
        manager.stop()
        FlakyClient.reachable = True
        pump(timeout=0.2)
        self.assertEqual(self.answers, [])


class DamagedSessionTest(unittest.TestCase):
    """A session file that cannot be opened is set aside, and signing in starts over, rather than the
    program waiting for ever on a Telegram thread that has died."""

    def test_a_damaged_session_is_set_aside_and_signing_in_asked_for(self):
        import os
        import tempfile
        session = os.path.join(tempfile.mkdtemp(), "account")
        with open(session + ".session", "wb") as file:
            file.write(b"not a database" * 50)
        answers = []
        with mock.patch.object(telegram_client, "CONNECTION_WATCH_SECONDS", 0.01),                 self.assertLogs("core.telegram_client", level="ERROR"):
            manager = telegram_client.TelegramManager(lambda step, error_key=None: answers.append(step), session)
            # Nothing is asked of Telegram itself: the new session is never connected.
            with mock.patch.object(telegram_client.TelegramManager, "_connect_async", lambda self: asyncio_sleep()):
                manager.start()
                self.addCleanup(manager.stop)
                self.assertTrue(pump(lambda: manager.client is not None, timeout=5))
        names = os.listdir(os.path.dirname(session))
        self.assertTrue(any(name.startswith("account.session.broken-") for name in names), names)


async def asyncio_sleep():
    import asyncio
    await asyncio.sleep(0)


class SignedInOfflineTest(unittest.TestCase):
    """An account signed in on this computer opens without the network, and is asked to sign in again
    only if Telegram, once reached, says the session was ended elsewhere."""

    def setUp(self):
        FlakyClient.reachable = False
        FlakyClient.authorized = True
        self.answers = []
        for patch in (
            mock.patch.object(telegram_client, "TelegramClient", FlakyClient),
            mock.patch.object(telegram_client, "CONNECTION_WATCH_SECONDS", 0.01),
            mock.patch.object(telegram_client, "CONNECT_RETRY_SECONDS", 0.01),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(setattr, FlakyClient, "authorized", True)
        manager = telegram_client.TelegramManager(lambda step, error_key=None: self.answers.append((step, error_key)))
        manager.known_signed_in = True
        manager.start()
        self.addCleanup(manager.stop)

    def test_it_opens_at_once_and_says_nothing_more_once_connected(self):
        self.assertTrue(pump(lambda: self.answers == [(c.STEP_DONE, None)]))
        FlakyClient.reachable = True
        pump(timeout=0.2)
        self.assertEqual(self.answers, [(c.STEP_DONE, None)])

    def test_a_session_ended_elsewhere_asks_to_sign_in_once_reached(self):
        FlakyClient.authorized = False
        self.assertTrue(pump(lambda: self.answers == [(c.STEP_DONE, None)]))
        FlakyClient.reachable = True
        self.assertTrue(pump(lambda: self.answers == [(c.STEP_DONE, None), (c.STEP_PHONE, None)]))
