"""Keeping a trace of what goes wrong, and putting it together for whoever is to fix it."""
import datetime
import logging
import os
import platform
import sys
import threading
import time

from core.constants import (
    APP_NAME, APP_VERSION, IS_FROZEN, LOG_FILE, REPORT_FILE_FORMAT, REPORT_LOG_BYTES, ERROR_NOTICE_SECONDS,
    LOG_STARTED_MARK, LOG_STOPPED, REPORT_INSTALLED_KEY, REPORT_FROM_SOURCE_KEY, REPORT_WINDOWS_FORMAT_KEY,
    REPORT_DESCRIPTION_KEY, REPORT_LOG_KEY, REPORT_PREVIOUS_LOG_KEY, REPORT_NONE_KEY
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


def read_log():
    """The whole log, the older file before the current one."""
    text = ""
    for path in (LOG_FILE + ".1", LOG_FILE):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as log_file:
                text += log_file.read()
        except OSError:
            pass
    return text


def latest_runs():
    """(this run's log, the run before's if it never closed normally, else ""), each at most REPORT_LOG_BYTES.
    Older runs are left out: what went wrong days ago has nothing to do with what the user reports now."""
    lines = read_log().splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if LOG_STARTED_MARK in line]
    if not starts:
        return "".join(lines)[-REPORT_LOG_BYTES:], ""
    this_run = "".join(lines[starts[-1]:])
    previous = "".join(lines[starts[-2]:starts[-1]]) if len(starts) > 1 else ""
    # A run that crashed, or that Windows ended, never wrote its closing line.
    if LOG_STOPPED in previous:
        previous = ""
    return this_run[-REPORT_LOG_BYTES:], previous[-REPORT_LOG_BYTES:]


def versions(text):
    lines = [
        "%s %s (%s)" % (APP_NAME, APP_VERSION, text(REPORT_INSTALLED_KEY if IS_FROZEN else REPORT_FROM_SOURCE_KEY)),
        text(REPORT_WINDOWS_FORMAT_KEY).format(version=platform.platform()),
        "Python: " + platform.python_version(),
    ]
    for name in ("wx", "telethon"):
        module = sys.modules.get(name)
        if module is not None:
            lines.append("%s: %s" % (name, getattr(module, "__version__", "?")))
    return lines


def write_report(folder, description, text, details=()):
    """Save what a developer needs to look into a problem as one text file; returns its path.

    `description` is the user's own account of it; `text` gives the report's own words in the
    user's language; `details` are further lines the caller knows (the interface language).
    """
    os.makedirs(folder, exist_ok=True)
    now = datetime.datetime.now()
    path = os.path.join(folder, REPORT_FILE_FORMAT.format(time=now.strftime("%Y%m%d-%H%M%S")))
    this_run, previous = latest_runs()
    parts = [
        now.strftime("%Y-%m-%d %H:%M:%S"), *versions(text), *details,
        "", text(REPORT_DESCRIPTION_KEY), description.strip() or text(REPORT_NONE_KEY),
    ]
    if previous:
        parts += ["", text(REPORT_PREVIOUS_LOG_KEY), previous.rstrip("\n")]
    parts += ["", text(REPORT_LOG_KEY), this_run.rstrip("\n") or text(REPORT_NONE_KEY)]
    with open(path, "w", encoding="utf-8") as report_file:
        report_file.write("\n".join(parts) + "\n")
    return path
