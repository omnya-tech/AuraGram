import wx
from ui.themes import apply_theme, chosen_colours
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


class OptionalButton(OptionalTabStop, wx.Button):
    pass


class TabButton(OptionalTabStop, wx.ToggleButton):
    """One tab of a ViewTabs strip."""

    is_current = False

    def AcceptsFocusFromKeyboard(self):
        # The strip is one stop for Tab, on the tab that is showing; the arrows reach the others.
        return self.is_current and super().AcceptsFocusFromKeyboard()


class ViewTabs(wx.Panel):
    """A row of tabs, one of them current: what a drop-down list says one entry at a time, all in sight.

    For the eyes and the mouse every choice is there to see and one click away. For the
    keyboard it is a single stop: Tab lands on the current tab, the arrows move to its
    neighbours, and a screen reader names each with whether it is the one pressed.
    `on_change()` is called when the user, not the program, picks another tab.
    """

    PREVIOUS_KEYS = (wx.WXK_UP, wx.WXK_NUMPAD_UP)
    NEXT_KEYS = (wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN)
    LEFT_KEYS = (wx.WXK_LEFT, wx.WXK_NUMPAD_LEFT)
    RIGHT_KEYS = (wx.WXK_RIGHT, wx.WXK_NUMPAD_RIGHT)

    def __init__(self, parent, labels, on_change, tooltip=""):
        super().__init__(parent)
        self.on_change = on_change
        self.tooltip = tooltip
        self.buttons = []
        self.selection = 0
        self._skipped_by_tab = False
        # No stretching of the last tab to the end of the row: each is as wide as its name.
        self.SetSizer(wx.WrapSizer(wx.HORIZONTAL, wx.REMOVE_LEADING_SPACES))
        self.Set(labels)

    @property
    def skipped_by_tab(self):
        return self._skipped_by_tab

    @skipped_by_tab.setter
    def skipped_by_tab(self, skipped):
        self._skipped_by_tab = skipped
        for button in self.buttons:
            button.skipped_by_tab = skipped

    def AcceptsFocusFromKeyboard(self):
        return any(button.AcceptsFocusFromKeyboard() for button in self.buttons)

    def Set(self, labels):
        """Replace the tabs with one per label, keeping the place of the current one where it still exists."""
        sizer = self.GetSizer()
        sizer.Clear(delete_windows=True)
        self.buttons = []
        for label in labels:
            button = TabButton(self, label=label)
            button.skipped_by_tab = self._skipped_by_tab
            button.SetToolTip(self.tooltip)
            button.Bind(wx.EVT_TOGGLEBUTTON, self.on_click)
            sizer.Add(button, flag=wx.RIGHT | wx.BOTTOM, border=4)
            self.buttons.append(button)
        self.SetSelection(min(self.selection, len(self.buttons) - 1))
        self.GetParent().Layout()

    def GetSelection(self):
        return self.selection

    def SetSelection(self, index):
        self.selection = index
        # Every tab in the theme's plain button colours first; they may also have just been made.
        apply_theme(self)
        chosen = chosen_colours()
        for position, button in enumerate(self.buttons):
            current = position == index
            button.is_current = current
            button.SetValue(current)
            # A theme's own colours flatten the pressed look, so the current tab is told
            # apart twice over: in bold, and in the theme's colours the other way round.
            font = button.GetFont()
            font.SetWeight(wx.FONTWEIGHT_BOLD if current else wx.FONTWEIGHT_NORMAL)
            button.SetFont(font)
            if current and chosen is not None:
                button.SetBackgroundColour(chosen[0])
                button.SetForegroundColour(chosen[1])
        self.Layout()
        self.Refresh()

    def choose(self, index):
        """Go to a tab as the user asks, by mouse or by key."""
        changed = index != self.selection
        # Also puts a click on the current tab back: a tab cannot be un-pressed, only left for another.
        self.SetSelection(index)
        if changed:
            self.on_change()

    def on_click(self, event):
        self.choose(self.buttons.index(event.GetEventObject()))

    def handle_key(self, event, focused):
        """Move to the neighbouring tab for an arrow pressed on one of the tabs; False if the key was not for here."""
        if focused not in self.buttons or event.HasAnyModifiers():
            return False
        key = event.GetKeyCode()
        # Left and right go the way the eyes see them, which in a right-to-left window is the other way round.
        mirrored = self.GetLayoutDirection() == wx.Layout_RightToLeft
        if key in self.NEXT_KEYS or key in (self.LEFT_KEYS if mirrored else self.RIGHT_KEYS):
            step = 1
        elif key in self.PREVIOUS_KEYS or key in (self.RIGHT_KEYS if mirrored else self.LEFT_KEYS):
            step = -1
        else:
            return False
        self.choose((self.selection + step) % len(self.buttons))
        self.buttons[self.selection].SetFocus()
        return True


class ReadOnlyText(wx.TextCtrl):
    """Wrapping, scrollable text for the eyes and the mouse. The Tab key skips it,
    so keyboard and screen reader users do not land on a second copy of what the
    list they are in already says."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, style=wx.TE_MULTILINE | wx.TE_READONLY, **kwargs)

    def AcceptsFocusFromKeyboard(self):
        return False
