import logging

from core.constants import (
    UNAVAILABLE_KEY_STARTS, WAITING_KEYS, RESULT_KEYS, NAVIGATION_KEYS, FEEDBACK_UNAVAILABLE, FEEDBACK_WAITING,
    FEEDBACK_RESULT, FEEDBACK_NAVIGATION, FEEDBACK_CONFIRM,
)
try:
    from accessible_output2.outputs.auto import Auto
    _auto = Auto()
except Exception:
    # The library is optional: without it the app simply stays silent.
    _auto = None

logger = logging.getLogger(__name__)

# JAWS's main window, there while JAWS runs.
JAWS_WINDOW_CLASS = "JFWUI2"
JAWS_COM_NAME = "FreedomSci.JawsApi"


class JawsFallback:
    """JAWS reached through its own COM interface, for when accessible_output2 finds no screen reader
    though JAWS runs: it looks for JAWS only once, as the app starts, and the code it generates for
    COM can fail to load in the built program. This asks Windows each time, and generates nothing."""

    def __init__(self):
        self.api = None
        self.failed = False

    def is_running(self):
        try:
            import win32gui
            return win32gui.FindWindow(JAWS_WINDOW_CLASS, None) != 0
        except Exception:
            return False

    def _api(self):
        if self.api is None:
            import win32com.client
            self.api = win32com.client.Dispatch(JAWS_COM_NAME)
        return self.api

    def _call(self, action):
        try:
            action(self._api())
        except Exception:
            # Asked again next time: JAWS may have been restarting. Said once in the log, not at every remark.
            self.api = None
            if not self.failed:
                self.failed = True
                logger.warning("JAWS runs but could not be reached through its COM interface", exc_info=True)

    def speak(self, text, interrupt=False):
        self._call(lambda api: api.SayString(text, interrupt))

    def braille(self, text):
        # Passed inside a JAWS script call, where a double quote would end the string early and a
        # backslash is no escape (as accessible_output2 found too): single quotes stand for them.
        quoted = text.replace('"', "'")
        self._call(lambda api: api.RunFunction('BrailleString("%s")' % quoted))


_jaws = JawsFallback()


def is_available():
    """Whether the screen reader library loaded at all (not whether a screen reader is running)."""
    return _auto is not None

def _screen_reader():
    output = _auto.get_first_available_output() if _auto is not None else None
    # Skip the system voice fallback so users without a screen reader hear nothing.
    if output is not None and not output.is_system_output():
        return output
    return _jaws if _jaws.is_running() else None

def speak(text, interrupt=False):
    """Announce text through the running screen reader, if there is one.

    `interrupt` cuts off whatever it is saying; otherwise the text waits its turn.
    """
    try:
        output = _screen_reader()
        if output is not None:
            output.speak(text, interrupt=interrupt)
    except Exception:
        pass

def braille(text):
    """Show text on the braille display the screen reader drives, if it has one."""
    try:
        output = _screen_reader()
        if output is not None:
            output.braille(text)
    except Exception:
        pass


# Whether a kind of remark (FEEDBACK_*) is to be said; set by the main window from the settings.
_allowed = lambda kind: True

def set_feedback_rule(allowed):
    global _allowed
    _allowed = allowed

def say(text, kind):
    """Speak a remark of the app's own, unless the user turned that kind of remark off."""
    if _allowed(kind):
        speak(text)

def kind_of(key):
    """The kind of remark a message key makes, going by its name."""
    if key.startswith(UNAVAILABLE_KEY_STARTS):
        return FEEDBACK_UNAVAILABLE
    for kind, keys in ((FEEDBACK_WAITING, WAITING_KEYS), (FEEDBACK_RESULT, RESULT_KEYS), (FEEDBACK_NAVIGATION, NAVIGATION_KEYS)):
        if key in keys:
            return kind
    return FEEDBACK_CONFIRM
