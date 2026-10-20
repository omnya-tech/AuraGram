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

def is_available():
    """Whether the screen reader library loaded at all (not whether a screen reader is running)."""
    return _auto is not None

def _screen_reader():
    if _auto is None:
        return None
    output = _auto.get_first_available_output()
    # Skip the system voice fallback so users without a screen reader hear nothing.
    return output if output is not None and not output.is_system_output() else None

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
