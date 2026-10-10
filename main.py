import wx
from core.constants import (
    API_ID, API_HASH, DEFAULT_LANG, APP_TITLE_KEY,
    ERR_NO_CONFIG_KEY, STEP_DONE
)
from core.i18n import I18NManager
from core.telegram_client import TelegramManager
from ui.login_frame import LoginFrame
from ui.main_frame import MainFrame

class MainApplication(wx.App):
    def OnInit(self):
        self.i18n = I18NManager(DEFAULT_LANG)
        self.telegram_manager = None
        if not API_ID or not API_HASH:
            wx.MessageBox(
                self.i18n.get_string(ERR_NO_CONFIG_KEY), self.i18n.get_string(APP_TITLE_KEY),
                wx.OK | wx.ICON_ERROR
            )
            return False

        self.telegram_manager = TelegramManager(self.on_telegram_response)
        self.login_frame = LoginFrame(self.i18n, self.telegram_manager)
        self.login_frame.Show()
        # Started only now: its callback needs the app and the frame to exist.
        self.telegram_manager.start()
        return True

    def on_telegram_response(self, step, error_key=None):
        wx.CallAfter(self._process_telegram_response, step, error_key)

    def _process_telegram_response(self, step, error_key):
        if not self.login_frame:
            return
        if step == STEP_DONE:
            # Open the main window first so the app never has zero windows.
            self.main_frame = MainFrame(self.i18n, self.telegram_manager, self.log_out)
            self.main_frame.Show()
            self.login_frame.Destroy()
            if error_key:
                self.main_frame.show_error(error_key)
            return
        self.login_frame.set_step(step)
        if error_key:
            self.login_frame.show_error(error_key)

    def log_out(self):
        # The login window waits in its busy state until Telegram confirms.
        self.login_frame = LoginFrame(self.i18n, self.telegram_manager)
        self.login_frame.Show()
        # Close(), not Destroy(): the window stops playback and recording on its way out.
        self.main_frame.Close()
        self.telegram_manager.set_message_listener(None)
        self.telegram_manager.log_out()

    def OnExit(self):
        if self.telegram_manager:
            self.telegram_manager.stop()
        return super().OnExit()

if __name__ == '__main__':
    app = MainApplication()
    app.MainLoop()
