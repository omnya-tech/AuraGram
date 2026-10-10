import sys
import wx
from core.config import load_credentials, save_credentials
from core.constants import (
    APP_NAME, DEFAULT_LANG, APP_TITLE_KEY, STEP_DONE, BACKGROUND_FLAG, CHECK_FLAG, QUIT_FLAG,
    QUIT_WAIT_SECONDS,
    SHOW_HOTKEY_TEXT, ERR_HOTKEY_TAKEN_FORMAT_KEY
)
from core.i18n import I18NManager
from core.settings import Settings
from core.telegram_client import TelegramManager
from ui.api_setup_dialog import ApiSetupDialog
from ui.background import BackgroundWindow, ask_running_copy_to_quit, ask_running_copy_to_show
from ui.login_frame import LoginFrame
from ui.main_frame import MainFrame

class MainApplication(wx.App):
    def OnInit(self):
        self.telegram_manager = None
        self.background = None
        self.main_frame = None
        self.login_frame = None
        # Two copies would fight over the same Telegram session file.
        self.instance_checker = wx.SingleInstanceChecker(APP_NAME + "-" + wx.GetUserId())
        if self.instance_checker.IsAnotherRunning():
            ask_running_copy_to_show()
            return False

        self.i18n = I18NManager(DEFAULT_LANG)
        self.settings = Settings()
        if not self.ensure_credentials():
            return False

        # Started with Windows: stay out of the way unless signing in is needed.
        self.start_hidden = BACKGROUND_FLAG in sys.argv
        self.background = BackgroundWindow(self.i18n, self.show_window, self.quit)
        self.telegram_manager = TelegramManager(self.on_telegram_response)
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
        self.login_frame = LoginFrame(self.i18n, self.telegram_manager)
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
    2 for voice messages unavailable, 4 for screen reader output unavailable.
    """
    import os
    from core import audio, speech
    from core.constants import ICON_FILE, SOUNDS_DIR, SOUND_MESSAGE, SOUND_MESSAGE_IN_CHAT, SOUND_SENT
    files = [ICON_FILE] + [
        os.path.join(SOUNDS_DIR, name + ".wav") for name in (SOUND_MESSAGE, SOUND_MESSAGE_IN_CHAT, SOUND_SENT)
    ]
    problems = 0
    if not I18NManager(DEFAULT_LANG).strings or not all(os.path.exists(path) for path in files):
        problems += 1
    if not audio.AVAILABLE:
        problems += 2
    if not speech.is_available():
        problems += 4
    return problems

if __name__ == '__main__':
    if CHECK_FLAG in sys.argv:
        sys.exit(self_check())
    if QUIT_FLAG in sys.argv:
        # Exit code 0 tells the installer the program is closed and its files are free.
        sys.exit(0 if ask_running_copy_to_quit(QUIT_WAIT_SECONDS) else 1)
    app = MainApplication()
    app.MainLoop()
