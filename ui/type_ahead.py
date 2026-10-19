"""Going to an item of a list by typing the start of its name, as in Windows' own lists.

Letters typed close together make one word to look for; the same letter again and again goes
from one item that starts with it to the next. Arabic is matched the way people type it: with
or without its marks, with any form of alef, and with ة and ه, ى and ي taken as the same.
"""
import time
import unicodedata
import wx
from core.constants import TYPE_AHEAD_PAUSE_SECONDS

# Letters that people type one for the other.
SAME_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي"})
TATWEEL = "ـ"


def fold(text):
    """Text as it is compared: no case, no marks over or under the letters, one form for each letter."""
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char) and char != TATWEEL)
    return text.translate(SAME_LETTERS).lstrip()


class TypeAhead:
    """Typing to go to an item of one list box (or check list box).

    `row_text(index)` gives what an item is known by, when that is not simply its row: a chat's
    row may start with "Channel:" though it is the chat's name that is typed.
    """

    def __init__(self, list_box, row_text=None):
        self.list_box = list_box
        self.known_by = row_text
        self.typed = ""
        self.last_typed = 0.0
        list_box.Bind(wx.EVT_CHAR, self.on_char)

    def row_text(self, index):
        # A row with nothing behind it (one that says the list is loading, say) is known by what it says.
        if self.known_by is not None:
            try:
                return self.known_by(index)
            except (IndexError, KeyError):
                pass
        return self.list_box.GetString(index)

    def is_typing(self):
        """Whether a word is being typed right now, so a space belongs to it."""
        return bool(self.typed) and time.monotonic() - self.last_typed < TYPE_AHEAD_PAUSE_SECONDS

    def on_char(self, event):
        code = event.GetUnicodeKey()
        if event.ControlDown() or event.AltDown() or code == wx.WXK_NONE or code < 32:
            event.Skip()
            return
        char = chr(code)
        if char == " " and not self.is_typing():
            # Space on its own keeps what the list does with it: ticking a box, playing a sound.
            event.Skip()
            return
        if not self.is_typing():
            self.typed = ""
        self.typed += char
        self.last_typed = time.monotonic()
        self.go_to(self.find(self.typed))

    def find(self, typed):
        """The item the typing points to; wx.NOT_FOUND if none starts that way."""
        count = self.list_box.GetCount()
        if not count:
            return wx.NOT_FOUND
        current = max(self.list_box.GetSelection(), 0)
        wanted = fold(typed)
        if len(set(wanted)) == 1:
            # One letter, maybe pressed again: on to the next item with it, round to the top.
            wanted = wanted[0]
            start = current + 1
        else:
            # A word: the item that starts with it, the current one first.
            start = current
        for offset in range(count):
            index = (start + offset) % count
            if fold(self.row_text(index)).startswith(wanted):
                return index
        return wx.NOT_FOUND

    def go_to(self, index):
        if index == wx.NOT_FOUND:
            wx.Bell()
            return
        self.list_box.SetSelection(index)
        # As if moved to with the arrows: what follows the selection (a preview) follows it here too.
        event = wx.CommandEvent(wx.wxEVT_LISTBOX, self.list_box.GetId())
        event.SetEventObject(self.list_box)
        event.SetInt(index)
        self.list_box.ProcessWindowEvent(event)


def attach_to_lists(window):
    """Give every list box inside a window (such as one of wx's choice dialogs) typing to go to an item."""
    found = []
    for child in window.GetChildren():
        if isinstance(child, wx.ListBox):
            found.append(TypeAhead(child))
        found.extend(attach_to_lists(child))
    return found
