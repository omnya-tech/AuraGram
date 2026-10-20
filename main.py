import sys
from core import share
from core.constants import CHECK_FLAG, QUIT_FLAG
from ui.background import ask_running_copy_to_show, ask_running_copy_to_take_files, running_copy_window

def hand_over_to_running_copy(arguments):
    """Bring forward the copy already running, handing it any files to send; False if none is running.

    Done before anything heavy is loaded: a click on the desktop icon while the program
    waits in the background then answers at once, instead of after loading Telegram and audio.
    """
    if CHECK_FLAG in arguments or QUIT_FLAG in arguments or not running_copy_window():
        return False
    paths = share.files_among(arguments)
    if paths:
        share.leave(paths)
        return ask_running_copy_to_take_files()
    return ask_running_copy_to_show()

if __name__ == '__main__' and hand_over_to_running_copy(sys.argv[1:]):
    sys.exit(0)

import logging
import logging.handlers
import threading
import wx
from core.config import load_credentials, read_bundled, save_credentials
from core.constants import (
    APP_NAME, DEFAULT_LANG, STEP_DONE, BACKGROUND_FLAG,
    QUIT_WAIT_SECONDS, CONNECT_CHECK_SECONDS, BUNDLED_CONFIG_FILE, LOG_FILE, LOG_MAX_BYTES, APP_VERSION, IS_FROZEN,
    SHORTCUT_SHOW_WINDOW, SOUND_START, MSG_UNEXPECTED_ERROR_KEY, MAIN_FRAME_PRELOAD_MS, STEP_PHONE,
    MSG_ACCOUNT_SWITCHED_FORMAT_KEY
)
from core.i18n import I18NManager
from core import diagnostics, proxy, shortcuts, sounds
from core.settings import (
    SETTING_ANNOUNCE_CONNECTION, SETTING_START_SOUND, SETTING_THEME, SETTING_LANGUAGE, SETTING_ACCOUNTS,
    SETTING_CURRENT_ACCOUNT, Settings
)
from core import accounts
from core.speech import speak
from ui.layout import use_interface_language
from ui.themes import set_theme
from core.telegram_client import TelegramManager
from ui.api_setup_dialog import ApiSetupDialog
from ui.background import BackgroundWindow, ask_running_copy_to_quit, connection_news_key
from ui.login_frame import LoginFrame

def load_audio():
    from core import audio
    return audio

def load_main_frame():
    """The main window's class. It and all it needs (audio, every dialog) are loaded beside the
    connection to Telegram rather than before it, so the first window is up sooner."""
    from ui.main_frame import MainFrame
    return MainFrame

class MainApplication(wx.App):
    def OnInit(self):
        self.telegram_manager = None
        self.background = None
        self.main_frame = None
        # The account to go back to if signing in to a new one is given up; None when none is being added.
        self.account_before = None
        # The account to go to once signing out of this one is done; None for a sign-out that ends at the login.
        self.account_after = None
        self.login_frame = None
        self.connection_state = None
        # Two copies would fight over the same Telegram session file.
        self.instance_checker = wx.SingleInstanceChecker(APP_NAME + "-" + wx.GetUserId())
        # Files to send, when started from Windows' "Send to" menu.
        self.shared_paths = share.files_among(sys.argv[1:])
        if self.instance_checker.IsAnotherRunning():
            if self.shared_paths:
                share.leave(self.shared_paths)
                ask_running_copy_to_take_files()
            else:
                ask_running_copy_to_show()
            return False

        self.settings = Settings()
        # The whole interface loads in the saved language.
        self.i18n = I18NManager(self.settings.get(SETTING_LANGUAGE))
        use_interface_language(self.settings.get(SETTING_LANGUAGE))
        # Before any window exists, so the very first one already opens in the chosen colours.
        set_theme(self.settings.get(SETTING_THEME))
        if not self.ensure_credentials():
            return False

        # Started with Windows: stay out of the way unless signing in is needed.
        self.start_hidden = BACKGROUND_FLAG in sys.argv
        self.background = BackgroundWindow(
            self.i18n, self.show_window, self.quit, shortcuts.current(self.settings)[SHORTCUT_SHOW_WINDOW],
            self.take_shared_files
        )
        diagnostics.on_unexpected_error = lambda: wx.CallAfter(self.tell_unexpected_error)
        self.start_account()
        # While Telegram answers: the audio libraries on a thread of their own (they have nothing
        # to do with wx), the main window's code once the first window has been drawn. A second
        # import of the same module waits for the first to finish, so neither can come too early.
        threading.Thread(target=load_audio, daemon=True).start()
        wx.CallLater(MAIN_FRAME_PRELOAD_MS, load_main_frame)
        return True

    def start_account(self):
        """Connect as the account in use, from its own session: straight in if it is signed in, else the login."""
        # A manager left behind by a switch may still answer late: only the newest one is listened to.
        self.account_generation = getattr(self, "account_generation", 0) + 1
        generation = self.account_generation
        self.telegram_manager = TelegramManager(
            lambda step, error_key=None: self.on_telegram_response(step, error_key, generation),
            accounts.session_path(self.settings.get(SETTING_CURRENT_ACCOUNT))
        )
        # Messages are translated into the interface language.
        self.telegram_manager.translate_lang = self.settings.get(SETTING_LANGUAGE)
        self.telegram_manager.proxy = proxy.from_settings(self.settings)
        self.telegram_manager.set_connection_listener(self.on_connection_change)
        self.show_login()
        # Started only now: its callback needs the app and the frame to exist.
        self.telegram_manager.start()

    def switch_account(self, account_id):
        """Go to another account on this computer, or to a new one (None), leaving this one signed in."""
        current = self.settings.get(SETTING_CURRENT_ACCOUNT)
        if account_id is None:
            self.account_before = current
            account_id = accounts.next_id(self.settings.get(SETTING_ACCOUNTS), current)
        else:
            self.account_before = None
        self.settings.set(SETTING_CURRENT_ACCOUNT, account_id)
        self.settings.save()
        self.leave_account()
        self.start_account()

    def leave_account(self):
        """Close what belongs to the account in use: its window, its login window, its connection."""
        if self.main_frame:
            self.telegram_manager.set_message_listener(None)
            self.main_frame.quit()
            self.main_frame = None
        if self.login_frame:
            self.login_frame.Destroy()
            self.login_frame = None
        self.telegram_manager.stop()

    def on_login_closed(self, event):
        # Adding an account and thinking better of it: back to the one before, still signed in.
        if self.account_before is not None:
            account_id, self.account_before = self.account_before, None
            self.settings.set(SETTING_CURRENT_ACCOUNT, account_id)
            self.settings.save()
            wx.CallAfter(self.restart_account)
            return
        self.quit()

    def restart_account(self):
        self.leave_account()
        self.start_account()

    def remember_account(self, me):
        """Keep the name and number of the account just signed in, for the list of accounts."""
        if not me:
            return
        account_id = self.settings.get(SETTING_CURRENT_ACCOUNT)
        self.settings.set(SETTING_ACCOUNTS, accounts.remember(
            self.settings.get(SETTING_ACCOUNTS), account_id, me["name"], me["phone"]
        ))
        self.settings.save()

    def ensure_credentials(self):
        """Ask for the Telegram API id and hash on first run; False if the user backs out."""
        api_id, api_hash = load_credentials()
        if api_id and api_hash:
            return True
        with ApiSetupDialog(self.i18n) as setup_dialog:
            if setup_dialog.ShowModal() != wx.ID_OK:
                return False
            save_credentials(*setup_dialog.credentials)
        return True

    def show_login(self):
        # The login window starts in its busy state until Telegram says what is needed.
        self.login_frame = LoginFrame(self.i18n, self.telegram_manager, self.settings)
        # Closing it without signing in leaves nothing to keep running for, unless an account was being added.
        self.login_frame.Bind(wx.EVT_CLOSE, self.on_login_closed)
        if not self.start_hidden:
            self.login_frame.Show()

    def on_telegram_response(self, step, error_key=None, generation=None):
        wx.CallAfter(self._process_telegram_response, step, error_key, generation)

    def _process_telegram_response(self, step, error_key, generation=None):
        if not self.login_frame or (generation is not None and generation != self.account_generation):
            return
        if step == STEP_PHONE and self.account_after is not None:
            # Signed out of one account of several: on to another of them, already signed in.
            account_id, self.account_after = self.account_after, None
            self.settings.set(SETTING_CURRENT_ACCOUNT, account_id)
            self.settings.save()
            wx.CallAfter(self.restart_account)
            return
        if step == STEP_DONE:
            self.account_before = None
            # Open the main window first so the app never has zero windows.
            self.main_frame = load_main_frame()(
                self.i18n, self.telegram_manager, self.settings, self.log_out, self.quit,
                self.background.set_hotkey, self.switch_account
            )
            main_frame = self.main_frame
            self.telegram_manager.load_me(lambda me, error_key: wx.CallAfter(self.on_me, main_frame, me))
            if not self.start_hidden:
                self.main_frame.Show()
                # The app's own chime: only when its window really opens, never on a silent start with Windows.
                if self.settings.get(SETTING_START_SOUND):
                    sounds.play(SOUND_START)
                self.main_frame.check_updates_once()
                # After the window is up: a shortcut another program holds is news worth a question.
                wx.CallAfter(self.main_frame.check_shortcuts_once)
                # And, the first time, how much the app should say.
                wx.CallAfter(self.main_frame.ask_speech_level_once)
            self.login_frame.Destroy()
            if error_key:
                self.main_frame.show_error(error_key)
            self.hand_over_shared_files()
        else:
            # Signing in needs the user, even when asked to start in the background.
            self.login_frame.Show()
            self.login_frame.set_step(step)
            if error_key:
                self.login_frame.show_error(error_key)
        # Only the very first window honours the background start.
        self.start_hidden = False

    def tell_unexpected_error(self):
        """A command failed in a way nothing foresaw: say so, instead of leaving the user to wonder."""
        if self.main_frame:
            self.main_frame.notify(MSG_UNEXPECTED_ERROR_KEY)

    def on_connection_change(self, state):
        wx.CallAfter(self._show_connection_state, state)

    def _show_connection_state(self, state):
        # Gone once the program is on its way out.
        if not self.background:
            return
        self.background.tray.set_connection_state(state)
        news_key = connection_news_key(self.connection_state, state)
        self.connection_state = state
        if news_key and self.settings.get(SETTING_ANNOUNCE_CONNECTION):
            speak(self.i18n.get_string(news_key))

    def show_window(self):
        """Bring the app forward: from the global shortcut, the tray icon, or a second launch."""
        if self.main_frame:
            self.main_frame.bring_forward()
        elif self.login_frame:
            self.login_frame.Show()
            self.login_frame.Raise()

    def take_shared_files(self):
        """Another copy was started with files to send and left them for this one."""
        self.shared_paths += share.collect()
        self.show_window()
        self.hand_over_shared_files()

    def hand_over_shared_files(self):
        # Until someone is signed in the files wait: there is nobody to send them as.
        if self.main_frame and self.shared_paths:
            paths, self.shared_paths = self.shared_paths, []
            self.main_frame.share_files(paths)

    def on_me(self, main_frame, me):
        self.remember_account(me)
        if me and main_frame and len(self.settings.get(SETTING_ACCOUNTS)) > 1:
            # With several, which one is in use is worth saying.
            main_frame.announce(self.i18n.get_string(MSG_ACCOUNT_SWITCHED_FORMAT_KEY).format(name=me["name"]))

    def log_out(self):
        current = self.settings.get(SETTING_CURRENT_ACCOUNT)
        others = [account["id"] for account in self.settings.get(SETTING_ACCOUNTS) if account["id"] != current]
        self.settings.set(SETTING_ACCOUNTS, accounts.forget(self.settings.get(SETTING_ACCOUNTS), current))
        self.settings.save()
        # With other accounts here, signing out of this one goes on to the next of them.
        self.account_after = others[0] if others else None
        self.show_login()
        self.main_frame.quit()
        self.telegram_manager.set_message_listener(None)
        self.telegram_manager.log_out()

    def quit(self):
        """End the program for real, wherever it was asked from."""
        if self.main_frame:
            self.main_frame.quit()
        if self.login_frame:
            self.login_frame.Destroy()
        if self.background:
            self.background.shut_down()
            self.background = None

    def OnExit(self):
        if self.telegram_manager:
            self.telegram_manager.stop()
        return super().OnExit()

def self_check():
    """Used by the build script on the finished program: are the bundled pieces all there?

    Returns 0 if so, otherwise the sum of: 1 for missing files (texts, icon, tones),
    2 for voice messages unavailable, 4 for screen reader output unavailable,
    8 for no API id and hash packed in (the program will ask each user for them),
    16 for failing to connect to Telegram with them.
    """
    import os
    from core import audio, speech
    from core.constants import ICON_FILE, SOUNDS_DIR, SOUND_NAMES, LEGAL_FILE_NAMES, RESOURCE_DIR
    files = [ICON_FILE] + [
        os.path.join(SOUNDS_DIR, name + ".wav") for name in SOUND_NAMES
    ] + [os.path.join(RESOURCE_DIR, name) for name in LEGAL_FILE_NAMES]
    problems = 0
    if not I18NManager(DEFAULT_LANG).strings or not all(os.path.exists(path) for path in files):
        problems += 1
    if not audio.AVAILABLE:
        problems += 2
    if not speech.is_available():
        problems += 4
    if not read_bundled(BUNDLED_CONFIG_FILE)[0]:
        problems += 8
    elif not can_reach_telegram():
        problems += 16
    return problems

def can_reach_telegram():
    """Connect to Telegram the way signing in does, then hang up: no code is requested, no account touched.

    Uses a throwaway session in a temporary folder, never the user's own.
    """
    import asyncio
    import os
    import tempfile
    from telethon import TelegramClient
    api_id, api_hash = load_credentials()

    async def probe():
        client = TelegramClient(os.path.join(tempfile.mkdtemp(), "probe"), api_id, api_hash)
        try:
            await asyncio.wait_for(client.connect(), CONNECT_CHECK_SECONDS)
            return client.is_connected()
        finally:
            await client.disconnect()

    try:
        return asyncio.run(probe())
    except Exception:
        return False

# How Telethon starts each line about a failed try at reconnecting.
RETRY_LOG_PREFIX = "Attempt "

def start_logging():
    """Keep a small file of errors beside the user's settings.

    The built program has no console, so without this a failure leaves no trace
    beyond the short message shown on screen.
    """
    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=1, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.WARNING)
    logging.getLogger("core").setLevel(logging.INFO)
    # Telethon writes a line for every try while the network is down, several a minute, which pushed
    # everything else out of the log; the app logs going offline and back online itself.
    logging.getLogger("telethon.network.mtprotosender").addFilter(
        lambda record: not record.getMessage().startswith(RETRY_LOG_PREFIX)
    )
    logging.getLogger("core").info(
        "AuraGram %s started (%s)", APP_VERSION, "installed" if IS_FROZEN else "from source"
    )

if __name__ == '__main__':
    if CHECK_FLAG in sys.argv:
        sys.exit(self_check())
    if QUIT_FLAG in sys.argv:
        # Exit code 0 tells the installer the program is closed and its files are free.
        sys.exit(0 if ask_running_copy_to_quit(QUIT_WAIT_SECONDS) else 1)
    start_logging()
    diagnostics.catch_unexpected_errors()
    app = MainApplication()
    app.MainLoop()
