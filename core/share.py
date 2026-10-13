"""Files handed to AuraGram from outside it: Windows' "Send to" menu starts the program
with their paths. A copy that finds another one already running leaves the paths where
that one will look, since only it holds the Telegram session.
"""
import json
import os
import uuid
from core.constants import SHARE_INBOX_DIR, JSON_EXT, ENCODING_UTF8

FLAG_PREFIX = "--"


def files_among(arguments):
    """The files named on the command line, as full paths; the program's own flags and anything that is no file are left out."""
    return [
        os.path.abspath(argument) for argument in arguments
        if not argument.startswith(FLAG_PREFIX) and os.path.isfile(argument)
    ]


def leave(paths):
    """Put paths where the running copy collects them."""
    os.makedirs(SHARE_INBOX_DIR, exist_ok=True)
    draft = os.path.join(SHARE_INBOX_DIR, uuid.uuid4().hex)
    with open(draft, "w", encoding=ENCODING_UTF8) as note:
        json.dump(paths, note)
    # Named as a note only once it is whole, so it is never read half written.
    os.replace(draft, draft + JSON_EXT)


def collect():
    """Every path left since the last time, oldest first; the notes are used up."""
    try:
        notes = [os.path.join(SHARE_INBOX_DIR, name) for name in os.listdir(SHARE_INBOX_DIR) if name.endswith(JSON_EXT)]
    except OSError:
        return []
    paths = []
    for note_path in sorted(notes, key=os.path.getmtime):
        try:
            with open(note_path, encoding=ENCODING_UTF8) as note:
                left = json.load(note)
            os.remove(note_path)
        except (OSError, ValueError):
            continue
        if isinstance(left, list):
            paths += [path for path in left if isinstance(path, str) and os.path.isfile(path)]
    return paths
