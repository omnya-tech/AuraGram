import ctypes
import wx
import wx.adv
from core.constants import (
    BACKGROUND_WINDOW_TITLE, SHOW_HOTKEY_ID, ICON_FILE,
    TRAY_OPEN_KEY, TRAY_EXIT_KEY, TRAY_TOOLTIP_KEY
)

WM_HOTKEY = 0x0312
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


class TrayIcon(wx.adv.TaskBarIcon):
    def __init__(self, i18n, on_show, on_quit):
        super().__init__()
        self.i18n = i18n
        self.on_show = on_show
        self.on_quit = on_quit
        self.SetIcon(wx.Icon(ICON_FILE), i18n.get_string(TRAY_TOOLTIP_KEY))
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_UP, lambda event: self.on_show())

    def CreatePopupMenu(self):
        menu = wx.Menu()
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

    def shut_down(self):
        if self.has_hotkey:
            self.UnregisterHotKey(SHOW_HOTKEY_ID)
        self.tray.RemoveIcon()
        self.tray.Destroy()
        self.Destroy()
