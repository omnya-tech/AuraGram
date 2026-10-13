import logging
import logging.handlers
import sys
import wx
from core.config import load_credentials, read_sealed, save_credentials
from core.constants import (
    APP_NAME, DEFAULT_LANG, APP_TITLE_KEY, STEP_DONE, BACKGROUND_FLAG, CHECK_FLAG, QUIT_FLAG,
    QUIT_WAIT_SECONDS, CONNECT_CHECK_SECONDS, BUNDLED_CONFIG_FILE, LOG_FILE, LOG_MAX_BYTES, APP_VERSION, IS_FROZEN,
    SHOW_HOTKEY_TEXT, ERR_HOTKEY_TAKEN_FORMAT_KEY, SOUND_START, MSG_UNEXPECTED_ERROR_KEY
)
from core.i18n import I18NManager
from core import diagnostics, proxy, sounds
from core.settings import SETTING_ANNOUNCE_CONNECTION, SETTING_START_SOUND, SETTING_THEME, SETTING_LANGUAGE, Settings
from core.speech import speak
from ui.themes import set_theme
from core.telegram_client import TelegramManager
from ui.api_setup_dialog import ApiSetupDialog
from ui.background import BackgroundWindow, ask_running_copy_to_quit, ask_running_copy_to_show, connection_news_key
from ui.login_frame import LoginFrame
from ui.main_frame import MainFrame

class MainApplication(wx.App):
    def OnInit(self):
        self.telegram_manager = None
        self.background = None
        self.main_frame = None
        self.login_frame = None
        self.connection_state = None
        # Two copies would fight over the same Telegram session file.
        self.instance_checker = wx.SingleInstanceChecker(APP_NAME + "-" + wx.GetUserId())
        if self.instance_checker.IsAnotherRunning():
            ask_running_copy_to_show()
            return False

        self.settings = Settings()
        # The whole interface loads in the saved language.
        self.i18n = I18NManager(self.settings.get(SETTING_LANGUAGE))
        # Before any window exists, so the very first one already opens in the chosen colours.
        set_theme(self.settings.get(SETTING_THEME))
        if not self.ensure_credentials():
            return False

        # Started with Windows: stay out of the way unless signing in is needed.
        self.start_hidden = BACKGROUND_FLAG in sys.argv
        self.background = BackgroundWindow(self.i18n, self.show_window, self.quit)
        self.telegram_manager = TelegramManager(self.on_telegram_response)
        # Messages are translated into the interface language.
        self.telegram_manager.translate_lang = self.settings.get(SETTING_LANGUAGE)
        self.telegram_manager.proxy = proxy.from_settings(self.settings)
        diagnostics.on_unexpected_error = lambda: wx.CallAfter(self.tell_unexpected_error)
        self.telegram_manager.set_connection_listener(self.on_connection_change)
        self.show_login()
        # Started only now: its callback needs the app and the frame to exist.
        self.telegram_manager.start()
        if not self.background.has_hotkey and not self.start_hidden:
            wx.MessageBox(
                self.i18n.get_string(ERR_HOTKEY_TAKEN_FORMAT_KEY).format(hotkey=SHOW_HOTKEY_TEXT),
                self.i18n.get_string(APP_TITLE_KEY), wx.OK | wx.ICON_INFORMATION
            )
        return True

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
        # Closing it without signing in leaves nothing to keep running for.
        self.login_frame.Bind(wx.EVT_CLOSE, lambda event: self.quit())
        if not self.start_hidden:
            self.login_frame.Show()

    def on_telegram_response(self, step, error_key=None):
        wx.CallAfter(self._process_telegram_response, step, error_key)

    def _process_telegram_response(self, step, error_key):
        if not self.login_frame:
            return
        if step == STEP_DONE:
            # Open the main window first so the app never has zero windows.
            self.main_frame = MainFrame(
                self.i18n, self.telegram_manager, self.settings, self.log_out, self.quit
            )
            if not self.start_hidden:
                self.main_frame.Show()
                # The app's own chime: only when its window really opens, never on a silent start with Windows.
                if self.settings.get(SETTING_START_SOUND):
                    sounds.play(SOUND_START)
                self.main_frame.check_updates_once()
            self.login_frame.Destroy()
            if error_key:
                self.main_frame.show_error(error_key)
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

    def log_out(self):
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
    if not read_sealed(BUNDLED_CONFIG_FILE)[0]:
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
