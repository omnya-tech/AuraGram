"""Finding out whether a newer AuraGram has been released.

The program reads one small JSON file from UPDATE_INFO_URL:

    {"version": "1.2.0", "url": "https://.../AuraGram-Setup-1.2.0.exe", "notes": {"ar": "...", "en": "..."}}

`notes` is optional, and may be one text for every language. Nothing is downloaded
or run by the program itself: the user is shown the address and opens it.
"""
import json
import urllib.request

from core.constants import APP_NAME, APP_VERSION, UPDATE_INFO_URL, UPDATE_TIMEOUT_SECONDS, EMPTY_STRING

SAFE_SCHEME = "https://"
MAX_INFO_BYTES = 64 * 1024


def version_numbers(version):
    """A version as numbers that compare the way versions do; () for text that is not one."""
    try:
        return tuple(int(part) for part in str(version).strip().lstrip("v").split("."))
    except ValueError:
        return ()


def is_newer(version, than=APP_VERSION):
    numbers = version_numbers(version)
    return bool(numbers) and numbers > version_numbers(than)


def read_release(data, language):
    """The release a downloaded file announces: {"version", "url", "notes"}; None if it is not usable."""
    try:
        info = json.loads(data)
    except ValueError:
        return None
    if not isinstance(info, dict) or not version_numbers(info.get("version")):
        return None
    url = info.get("url")
    # Only an address the browser opens over a checked connection is ever offered.
    if not isinstance(url, str) or not url.startswith(SAFE_SCHEME):
        return None
    notes = info.get("notes", EMPTY_STRING)
    if isinstance(notes, dict):
        notes = notes.get(language) or next(iter(notes.values()), EMPTY_STRING)
    return {"version": str(info["version"]).lstrip("v"), "url": url, "notes": notes if isinstance(notes, str) else EMPTY_STRING}


def is_configured():
    return UPDATE_INFO_URL.startswith(SAFE_SCHEME)


def fetch_release(language):
    """The newest release there is, as read_release gives it; None if it cannot be learned right now. Blocks."""
    if not is_configured():
        return None
    request = urllib.request.Request(UPDATE_INFO_URL, headers={"User-Agent": "%s/%s" % (APP_NAME, APP_VERSION)})
    try:
        with urllib.request.urlopen(request, timeout=UPDATE_TIMEOUT_SECONDS) as response:
            return read_release(response.read(MAX_INFO_BYTES), language)
    except (OSError, ValueError):
        return None
