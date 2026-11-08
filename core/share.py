"""Files handed to AuraGram from outside it: Windows' "Send to" menu starts the program
with their paths. A copy that finds another one already running leaves the paths where
that one will look, since only it holds the Telegram session.
"""
import json
import os
import uuid
from core.constants import SHARE_INBOX_DIR, JSON_EXT, ENCODING_UTF8, SEND_AS_FLAG, SEND_AS_CHOICES

FLAG_PREFIX = "--"
# What a note holds: the paths, and how they are to go.
NOTE_PATHS = "paths"
NOTE_SEND_AS = "as"


def files_among(arguments):
    """The files named on the command line, as full paths; the program's own flags and anything that is no file are left out."""
    return [
        os.path.abspath(argument) for argument in arguments
        if not argument.startswith(FLAG_PREFIX) and os.path.isfile(argument)
    ]


def send_as_among(arguments):
    """How the files are to go, as the entry of the "Send to" submenu says (SEND_AS_CHOICES); None when
    nothing says, as from the menu of an older install or files dropped on the program."""
    for argument in arguments:
        if argument.startswith(SEND_AS_FLAG) and argument[len(SEND_AS_FLAG):] in SEND_AS_CHOICES:
            return argument[len(SEND_AS_FLAG):]
    return None


def leave(paths, send_as=None):
    """Put paths where the running copy collects them, with how they are to go."""
    os.makedirs(SHARE_INBOX_DIR, exist_ok=True)
    draft = os.path.join(SHARE_INBOX_DIR, uuid.uuid4().hex)
    with open(draft, "w", encoding=ENCODING_UTF8) as note:
        json.dump({NOTE_PATHS: paths, NOTE_SEND_AS: send_as}, note)
    # Named as a note only once it is whole, so it is never read half written.
    os.replace(draft, draft + JSON_EXT)


def collect():
    """(every path left since the last time, oldest first; how the latest of them said they go, or None).
    The notes are used up."""
    try:
        notes = [os.path.join(SHARE_INBOX_DIR, name) for name in os.listdir(SHARE_INBOX_DIR) if name.endswith(JSON_EXT)]
    except OSError:
        return [], None
    paths = []
    send_as = None
    for note_path in sorted(notes, key=os.path.getmtime):
        try:
            with open(note_path, encoding=ENCODING_UTF8) as note:
                left = json.load(note)
            os.remove(note_path)
        except (OSError, ValueError):
            continue
        if isinstance(left, dict):
            # How they go is kept only where it is one of the ways there are.
            send_as = left.get(NOTE_SEND_AS) if left.get(NOTE_SEND_AS) in SEND_AS_CHOICES else send_as
            left = left.get(NOTE_PATHS)
        if isinstance(left, list):
            paths += [path for path in left if isinstance(path, str) and os.path.isfile(path)]
    return paths, send_as
