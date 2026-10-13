"""Keeping a trace of what goes wrong, and putting it together for whoever is to fix it."""
import datetime
import logging
import os
import platform
import sys
import threading
import time

from core.constants import (
    APP_NAME, APP_VERSION, IS_FROZEN, LOG_FILE, REPORT_FILE_FORMAT, REPORT_LOG_BYTES, ERROR_NOTICE_SECONDS
)

logger = logging.getLogger(__name__)
# Called, from whichever thread failed, when an error nobody caught has been written down.
on_unexpected_error = None
_last_notice = 0.0


def _record(exception_type, exception, traceback):
    global _last_notice
    if issubclass(exception_type, KeyboardInterrupt):
        return
    logger.error("Unexpected error", exc_info=(exception_type, exception, traceback))
    # One failing timer or event can repeat many times a second: tell the user once in a while, not each time.
    if on_unexpected_error is not None and time.monotonic() - _last_notice > ERROR_NOTICE_SECONDS:
        _last_notice = time.monotonic()
        try:
            on_unexpected_error()
        except Exception:
            pass


def catch_unexpected_errors():
    """Write every error nothing else caught to the log. The built program has no console,
    so without this a failed command would do nothing and leave no trace."""
    sys.excepthook = _record
    threading.excepthook = lambda arguments: _record(
        arguments.exc_type, arguments.exc_value, arguments.exc_traceback
    )


def log_tail():
    """The latest part of the log, the older file before the current one."""
    text = ""
    for path in (LOG_FILE + ".1", LOG_FILE):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as log_file:
                text += log_file.read()
        except OSError:
            pass
    return text[-REPORT_LOG_BYTES:]


def versions():
    lines = [
        "%s %s (%s)" % (APP_NAME, APP_VERSION, "installed" if IS_FROZEN else "from source"),
        "Windows: " + platform.platform(),
        "Python: " + platform.python_version(),
    ]
    for name in ("wx", "telethon"):
        module = sys.modules.get(name)
        if module is not None:
            lines.append("%s: %s" % (name, getattr(module, "__version__", "?")))
    return lines


def write_report(folder, description, details=()):
    """Save what a developer needs to look into a problem as one text file; returns its path.

    `description` is the user's own account of it; `details` are further lines the
    caller knows (the interface language, the screen reader in use).
    """
    os.makedirs(folder, exist_ok=True)
    now = datetime.datetime.now()
    path = os.path.join(folder, REPORT_FILE_FORMAT.format(time=now.strftime("%Y%m%d-%H%M%S")))
    parts = [
        now.strftime("%Y-%m-%d %H:%M:%S"), *versions(), *details,
        "", "--- description ---", description.strip() or "(none)",
        "", "--- log ---", log_tail() or "(empty)",
    ]
    with open(path, "w", encoding="utf-8") as report_file:
        report_file.write("\n".join(parts) + "\n")
    return path
