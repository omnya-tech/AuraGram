"""Writing the program's own small files so that a crash, a power cut or a full disk never leaves half of one."""
import json
import os

from core.constants import ENCODING_UTF8

PARTIAL_SUFFIX = ".partial"


def write_json(path, data, **dump_arguments):
    """Write `data` as JSON to `path`, all of it or none: it goes to a file beside it first, which then
    takes the old one's place in one step. A file read back half written would be thrown away whole."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    partial = path + PARTIAL_SUFFIX
    try:
        with open(partial, "w", encoding=ENCODING_UTF8) as file:
            json.dump(data, file, **dump_arguments)
            file.flush()
            os.fsync(file.fileno())
        os.replace(partial, path)
    except BaseException:
        # Out of room, say: what was there before is left as it was, and nothing half-written behind it.
        try:
            os.remove(partial)
        except OSError:
            pass
        raise
