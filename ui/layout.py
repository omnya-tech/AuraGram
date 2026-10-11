import wx
from ui.themes import apply_theme
import os
from core.constants import (
    ICON_FILE, TEXT_DIRECTION_KEY, TEXT_DIRECTION_RTL, LARGE_TEXT_SCALE, FILE_KINDS, FILE_KIND_OTHER_FORMAT_KEY,
    FILE_SIZE_UNITS, FILE_SIZE_FORMAT_KEY
)

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

def file_kind(i18n, name):
    """What a file is, going by its name: "PDF document", "compressed file"; empty if the name tells nothing."""
    extension = os.path.splitext(name)[1].lower()
    for kind_key, extensions in FILE_KINDS:
        if extension in extensions:
            return i18n.get_string(kind_key)
    if not extension:
        return ""
    return i18n.get_string(FILE_KIND_OTHER_FORMAT_KEY).format(extension=extension[1:].upper())


def file_size(i18n, size):
    """A number of bytes as people say it: "2.3 megabytes"."""
    number, unit = float(size), 0
    while number >= 1024 and unit < len(FILE_SIZE_UNITS) - 1:
        number, unit = number / 1024, unit + 1
    shown = "%d" % number if unit == 0 or number >= 100 else ("%.1f" % number).rstrip("0").rstrip(".")
    return i18n.get_string(FILE_SIZE_FORMAT_KEY).format(number=shown, unit=i18n.get_string(FILE_SIZE_UNITS[unit]))


def duration_text(seconds):
    """Seconds as minutes and seconds: 0:42, 3:05."""
    return "%d:%02d" % divmod(int(round(seconds)), 60)


def reading_font(large):
    """The font for text that is read at length: chat rows, messages, the message being written."""
    font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
    if large:
        font.SetFractionalPointSize(font.GetFractionalPointSize() * LARGE_TEXT_SCALE)
    return font

def is_on_a_screen(rectangle):
    """Whether a saved window position still lands on a connected monitor."""
    return wx.Display.GetFromPoint(rectangle.GetTopLeft()) != wx.NOT_FOUND


class OptionalTabStop:
    """Mixed into a control the Tab key may pass over. It stays on screen for the
    mouse and its job stays on the menu bar; it is only no longer a stop on the
    way from the chats to the message being written."""

    skipped_by_tab = False

    def AcceptsFocusFromKeyboard(self):
        return not self.skipped_by_tab and super().AcceptsFocusFromKeyboard()


class OptionalChoice(OptionalTabStop, wx.Choice):
    pass


class OptionalButton(OptionalTabStop, wx.Button):
    pass


class ReadOnlyText(wx.TextCtrl):
    """Wrapping, scrollable text for the eyes and the mouse. The Tab key skips it,
    so keyboard and screen reader users do not land on a second copy of what the
    list they are in already says."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, style=wx.TE_MULTILINE | wx.TE_READONLY, **kwargs)

    def AcceptsFocusFromKeyboard(self):
        return False
