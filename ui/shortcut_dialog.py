import wx
from core import shortcuts
from core.speech import speak
from ui.layout import prepare_window
from core.constants import (
    SHORTCUT_CAPTURE_TITLE_KEY, SHORTCUT_CAPTURE_NOTE_FORMAT_KEY, SHORTCUT_CAPTURE_FIELD_KEY,
    ERR_SHORTCUT_EMPTY_KEY, ERR_SHORTCUT_KEY_KEY
)

# Held on the way to a shortcut; pressing one of them alone is not yet anything to report.
MODIFIER_KEYS = (wx.WXK_CONTROL, wx.WXK_ALT, wx.WXK_SHIFT, wx.WXK_WINDOWS_LEFT, wx.WXK_WINDOWS_RIGHT)
# Left to do what they always do in a dialog.
DIALOG_KEYS = (wx.WXK_TAB, wx.WXK_ESCAPE)

class ShortcutDialog(wx.Dialog):
    """Asks for a shortcut by having it pressed, not typed: what the keyboard sends is what is kept.

    Each press is shown in the field and spoken, so it can be checked by ear before accepting.
    """

    def __init__(self, parent, i18n, command_label, command):
        super().__init__(parent, title=i18n.get_string(SHORTCUT_CAPTURE_TITLE_KEY))
        prepare_window(self, i18n)
        self.i18n = i18n
        self.command = command
        # The shortcut pressed last, if it is one the command may have.
        self.shortcut = ""
        sizer = wx.BoxSizer(wx.VERTICAL)
        note = wx.StaticText(self, label=i18n.get_string(SHORTCUT_CAPTURE_NOTE_FORMAT_KEY).format(command=command_label))
        note.Wrap(420)
        sizer.Add(note, flag=wx.ALL, border=10)
        sizer.Add(wx.StaticText(self, label=i18n.get_string(SHORTCUT_CAPTURE_FIELD_KEY)), flag=wx.LEFT|wx.RIGHT, border=10)
        self.field = wx.TextCtrl(self, style=wx.TE_READONLY, size=(420, -1))
        sizer.Add(self.field, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        sizer.Add(self.CreateButtonSizer(wx.OK|wx.CANCEL), flag=wx.EXPAND|wx.ALL, border=10)
        self.SetSizerAndFit(sizer)
        self.CenterOnParent()
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
        self.field.SetFocus()

    def on_char_hook(self, event):
        key = event.GetKeyCode()
        plain = not event.HasAnyModifiers()
        if key in MODIFIER_KEYS:
            return
        if plain and key in DIALOG_KEYS:
            event.Skip()
        elif plain and key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE) \
                and (self.shortcut or wx.Window.FindFocus() is not self.field):
            # Accepting what was pressed, or pressing one of the two buttons.
            event.Skip()
        else:
            self.take(shortcuts.from_key_event(event))

    def take(self, text):
        """A shortcut was pressed: keep it if the command may have it, and say why not otherwise."""
        reason = shortcuts.refusal(text, self.command) if text else ERR_SHORTCUT_KEY_KEY
        if reason:
            self.shortcut = ""
            self.field.ChangeValue("")
            speak(self.i18n.get_string(reason).format(shortcut=text))
            return
        self.shortcut = text
        self.field.ChangeValue(text)
        speak(text)

    def on_ok(self, event):
        if self.shortcut:
            event.Skip()
        else:
            speak(self.i18n.get_string(ERR_SHORTCUT_EMPTY_KEY))
            self.field.SetFocus()
