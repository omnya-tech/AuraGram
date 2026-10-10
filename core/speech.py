try:
    from accessible_output2.outputs.auto import Auto
    _auto = Auto()
except Exception:
    # The library is optional: without it the app simply stays silent.
    _auto = None

def is_available():
    """Whether the screen reader library loaded at all (not whether a screen reader is running)."""
    return _auto is not None

def speak(text):
    """Announce text through the running screen reader, if there is one."""
    if _auto is None:
        return
    try:
        output = _auto.get_first_available_output()
        # Skip the system voice fallback so users without a screen reader hear nothing.
        if output is not None and not output.is_system_output():
            output.speak(text, interrupt=False)
    except Exception:
        pass
