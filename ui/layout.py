import wx
from ui.themes import apply_theme
from core.constants import ICON_FILE, TEXT_DIRECTION_KEY, TEXT_DIRECTION_RTL, LARGE_TEXT_SCALE

def prepare_window(window, i18n):
    """Give a window the app's icon and the reading direction of the interface language.

    Call it before creating the window's controls: they take the direction from
    their parent as they are made, which is what mirrors the whole layout.
    """
    if i18n.get_string(TEXT_DIRECTION_KEY) == TEXT_DIRECTION_RTL:
        window.SetLayoutDirection(wx.Layout_RightToLeft)
    window.SetIcon(wx.Icon(ICON_FILE))
    # The colours go on once the constructor has made the controls there are to colour.
    wx.CallAfter(apply_theme, window)

def reading_font(large):
    """The font for text that is read at length: chat rows, messages, the message being written."""
    font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
    if large:
        font.SetFractionalPointSize(font.GetFractionalPointSize() * LARGE_TEXT_SCALE)
    return font

def is_on_a_screen(rectangle):
    """Whether a saved window position still lands on a connected monitor."""
    return wx.Display.GetFromPoint(rectangle.GetTopLeft()) != wx.NOT_FOUND


class ReadOnlyText(wx.TextCtrl):
    """Wrapping, scrollable text for the eyes and the mouse. The Tab key skips it,
    so keyboard and screen reader users do not land on a second copy of what the
    list they are in already says."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, style=wx.TE_MULTILINE | wx.TE_READONLY, **kwargs)

    def AcceptsFocusFromKeyboard(self):
        return False
