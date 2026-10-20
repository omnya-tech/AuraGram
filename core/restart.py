"""The program starting itself again, for what only a fresh start can take in, like a new language.

The new copy is started first, with RESTART_FLAG; it waits until the old copy has closed before
going on, so the two never run at once over the same session.
"""
import os
import subprocess
import sys

from core.constants import BASE_DIR, IS_FROZEN, RESTART_FLAG

MAIN_SCRIPT = "main.py"


def command():
    """How to start the program again: the built program itself, or Python with its main script."""
    if IS_FROZEN:
        return [sys.executable, RESTART_FLAG]
    return [sys.executable, os.path.join(BASE_DIR, MAIN_SCRIPT), RESTART_FLAG]


def start_new_copy():
    subprocess.Popen(command(), cwd=BASE_DIR, close_fds=True)
