import ctypes
import wx
from core.constants import THEME_SYSTEM, THEME_DARK, THEME_SEPIA, THEME_HIGH_CONTRAST

# Colours per theme: the window itself, and the places text is read or typed.
# The system theme has none: it leaves every control exactly as Windows draws it.
THEME_COLOURS = {
    THEME_SYSTEM: None,
    THEME_DARK: {
        "window": "#1E1E1E", "text": "#E6E6E6", "field": "#2B2B2B", "field_text": "#F2F2F2",
        "button": "#3A3A3A", "dark_title_bar": True,
    },
    THEME_SEPIA: {
        "window": "#F4ECD8", "text": "#3B2F1E", "field": "#FBF6E9", "field_text": "#2A2014",
        "button": "#E6D9B8", "dark_title_bar": False,
    },
    THEME_HIGH_CONTRAST: {
        "window": "#000000", "text": "#FFFFFF", "field": "#000000", "field_text": "#FFFF00",
        "button": "#000000", "dark_title_bar": True,
    },
}
# Controls that hold text to read or edit, and so take the "field" colours.
FIELD_CONTROLS = (wx.TextCtrl, wx.ListBox, wx.Choice)
DWMWA_USE_IMMERSIVE_DARK_MODE = 20

_current = THEME_SYSTEM

def set_theme(name):
    """Choose the theme that windows opened from now on, and apply_theme, will use."""
    global _current
    _current = name if name in THEME_COLOURS else THEME_SYSTEM

def current_theme():
    return _current

def apply_theme(window):
    """Colour a window and everything inside it with the current theme.

    Menus, scroll bars and the selection highlight are drawn by Windows and keep
    its colours; choosing a dark Windows theme is what changes those.
    """
    # Scheduled calls can arrive after their window was closed.
    if not window:
        return
    colours = THEME_COLOURS[_current]
    _paint(window, colours)
    if isinstance(window, wx.TopLevelWindow):
        _set_dark_title_bar(window, bool(colours and colours["dark_title_bar"]))
    window.Refresh()

def chosen_colours():
    """(background, text) for the one chosen item among several, such as the current tab; None
    under Windows' own colours, where the control's pressed look already tells it apart."""
    colours = THEME_COLOURS[_current]
    if colours is None:
        return None
    # The theme's two strongest colours swapped: as far from its neighbours as the theme allows.
    return wx.Colour(colours["text"]), wx.Colour(colours["window"])

def _paint(control, colours):
    if colours is None or isinstance(control, wx.StatusBar):
        # wx.NullColour hands the control back to its Windows default. The status bar
        # always keeps it: Windows draws its text dark whatever colour is asked for,
        # so a dark background would make the text disappear.
        background = foreground = wx.NullColour
    elif isinstance(control, FIELD_CONTROLS):
        background, foreground = wx.Colour(colours["field"]), wx.Colour(colours["field_text"])
    elif isinstance(control, (wx.Button, wx.ToggleButton)):
        background, foreground = wx.Colour(colours["button"]), wx.Colour(colours["text"])
    else:
        background, foreground = wx.Colour(colours["window"]), wx.Colour(colours["text"])
    control.SetBackgroundColour(background)
    control.SetForegroundColour(foreground)
    for child in control.GetChildren():
        # A dialog opened from this window is themed on its own when it is created.
        if not isinstance(child, wx.TopLevelWindow):
            _paint(child, colours)

def _set_dark_title_bar(window, dark):
    """Ask Windows 10/11 for a dark title bar; older systems just ignore the request."""
    try:
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            window.GetHandle(), DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass

def contrast_ratio(first, second):
    """How far apart two colours are in brightness, by the WCAG formula: 1 (same) to 21 (black on white)."""
    def luminance(colour):
        channels = []
        for value in wx.Colour(colour).Get()[:3]:
            value /= 255
            channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)
