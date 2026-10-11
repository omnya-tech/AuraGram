import ctypes
import time
import wx
import wx.adv
from core.constants import (
    BACKGROUND_WINDOW_TITLE, SHOW_HOTKEY_ID, ICON_FILE,
    TRAY_OPEN_KEY, TRAY_EXIT_KEY, TRAY_TOOLTIP_KEY, TRAY_STATUS_FORMAT_KEY,
    CONNECTION_CONNECTING, CONNECTION_STATE_KEYS, CONNECTION_OFFLINE,
    MSG_CONNECTION_LOST_KEY, MSG_CONNECTION_BACK_KEY
)

WM_HOTKEY = 0x0312
WM_CLOSE = 0x0010
ASFW_ANY = -1

def ask_running_copy_to_show():
    """From a second copy of the program: bring the first one's window forward.

    Returns False if the first copy's hidden window could not be found.
    """
    user32 = ctypes.windll.user32
    window = user32.FindWindowW(None, BACKGROUND_WINDOW_TITLE)
    if not window:
        return False
    # Windows lets only the foreground program hand the foreground to another.
    user32.AllowSetForegroundWindow(ASFW_ANY)
    # Same message the global shortcut produces, so both take the same path.
    user32.PostMessageW(window, WM_HOTKEY, SHOW_HOTKEY_ID, 0)
    return True


def ask_running_copy_to_quit(wait_seconds):
    """From a second copy started with --quit: close the running one and wait until it is gone.

    Returns True if no copy is left running, False if one is still there after the wait.
    """
    user32 = ctypes.windll.user32
    window = user32.FindWindowW(None, BACKGROUND_WINDOW_TITLE)
    if not window:
        return True
    # Closing the hidden window is the program's own exit path: it signs off from Telegram first.
    user32.PostMessageW(window, WM_CLOSE, 0, 0)
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if not user32.FindWindowW(None, BACKGROUND_WINDOW_TITLE):
            return True
        time.sleep(0.2)
    return False


def connection_news_key(previous, state):
    """The text worth saying aloud for a change of connection state, or None.

    Being online is the normal case and says nothing by itself: the news is
    the line going down, and its coming back after that.
    """
    if state == CONNECTION_OFFLINE:
        return MSG_CONNECTION_LOST_KEY
    return MSG_CONNECTION_BACK_KEY if previous == CONNECTION_OFFLINE else None


class TrayIcon(wx.adv.TaskBarIcon):
    def __init__(self, i18n, on_show, on_quit):
        super().__init__()
        self.i18n = i18n
        self.on_show = on_show
        self.on_quit = on_quit
        self.icon = wx.Icon(ICON_FILE)
        self.set_connection_state(CONNECTION_CONNECTING)
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_UP, lambda event: self.on_show())

    def set_connection_state(self, state):
        """Say on the icon whether Telegram is reachable: its tooltip is what a screen reader reads."""
        self.status_text = self.i18n.get_string(TRAY_STATUS_FORMAT_KEY).format(
            app=self.i18n.get_string(TRAY_TOOLTIP_KEY), status=self.i18n.get_string(CONNECTION_STATE_KEYS[state])
        )
        self.SetIcon(self.icon, self.status_text)

    def CreatePopupMenu(self):
        menu = wx.Menu()
        # Not a command, only the state, for whoever opens the menu without hearing the tooltip.
        menu.Append(wx.ID_ANY, self.status_text).Enable(False)
        menu.AppendSeparator()
        open_item = menu.Append(wx.ID_ANY, self.i18n.get_string(TRAY_OPEN_KEY))
        exit_item = menu.Append(wx.ID_ANY, self.i18n.get_string(TRAY_EXIT_KEY))
        menu.Bind(wx.EVT_MENU, lambda event: self.on_show(), open_item)
        menu.Bind(wx.EVT_MENU, lambda event: self.on_quit(), exit_item)
        return menu


class BackgroundWindow(wx.Frame):
    """Never shown. Keeps the program alive while its windows are hidden, and
    owns the two ways back in: the tray icon and the global shortcut."""

    def __init__(self, i18n, on_show, on_quit):
        super().__init__(None, title=BACKGROUND_WINDOW_TITLE)
        self.tray = TrayIcon(i18n, on_show, on_quit)
        # Ctrl+Alt+Shift+A. False if another program already holds the combination.
        self.has_hotkey = self.RegisterHotKey(
            SHOW_HOTKEY_ID, wx.MOD_CONTROL | wx.MOD_ALT | wx.MOD_SHIFT, ord("A")
        )
        self.Bind(wx.EVT_HOTKEY, lambda event: on_show(), id=SHOW_HOTKEY_ID)
        # Nobody can click this window shut; a close request comes from --quit
        # (the installer) or from Windows shutting down, and both mean: exit.
        self.Bind(wx.EVT_CLOSE, lambda event: on_quit())

    def shut_down(self):
        if self.has_hotkey:
            self.UnregisterHotKey(SHOW_HOTKEY_ID)
        self.tray.RemoveIcon()
        self.tray.Destroy()
        self.Destroy()
