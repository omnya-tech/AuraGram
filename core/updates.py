"""Finding out whether a newer AuraGram has been released, and fetching it.

The program reads one small JSON file from UPDATE_INFO_URL; build.py writes it:

    {
        "version": "1.2.0",
        "url": "https://github.com/owner/AuraGram/releases/tag/v1.2.0",
        "notes": {"ar": "...", "en": "..."},
        "full":   {"url": "https://.../AuraGram-Setup-1.2.0.exe",  "sha256": "...", "size": 49899400},
        "update": {"url": "https://.../AuraGram-Update-1.2.0.exe", "sha256": "...", "size": 8200000, "from": "1.0.0"}
    }

`url` is the release's page, for whoever would rather fetch it in a browser. `full` is
the whole installer. `update` is a small installer holding only what changes between
versions (the program itself, its texts and tones); it works over any installed version
from `from` upwards, the oldest one that has the same libraries. `notes`, `full` and
`update` are each optional, and `notes` may be one text for every language.

A package is fetched over https only, and is kept only if its size and SHA-256
are the ones the file announced. Nothing is run without the user saying so.
"""
import hashlib
import json
import os
import re
import urllib.request

from core.constants import (
    APP_NAME, APP_VERSION, UPDATE_INFO_URL, UPDATE_TIMEOUT_SECONDS, EMPTY_STRING, PACKAGE_FULL, PACKAGE_UPDATE,
    UPDATE_MAX_BYTES, UPDATE_CHUNK_BYTES, UPDATE_DOWNLOAD_TIMEOUT_SECONDS, ERR_UPDATE_DOWNLOAD_KEY,
    ERR_UPDATE_VERIFY_KEY
)

SAFE_SCHEME = "https://"
MAX_INFO_BYTES = 64 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PARTIAL_SUFFIX = ".part"


class DownloadError(Exception):
    """Fetching a package failed; `error_key` is the locale key of what to tell the user."""

    def __init__(self, error_key):
        super().__init__(error_key)
        self.error_key = error_key


def version_numbers(version):
    """A version as numbers that compare the way versions do; () for text that is not one."""
    try:
        return tuple(int(part) for part in str(version).strip().lstrip("v").split("."))
    except ValueError:
        return ()


def is_newer(version, than=APP_VERSION):
    numbers = version_numbers(version)
    return bool(numbers) and numbers > version_numbers(than)


def is_safe_url(url):
    # Only an address reached over a checked connection is ever opened or fetched.
    return isinstance(url, str) and url.startswith(SAFE_SCHEME)


def read_package(info):
    """One downloadable file as the release file describes it: {"url", "sha256", "size"}; None if it cannot be trusted."""
    if not isinstance(info, dict) or not is_safe_url(info.get("url")):
        return None
    checksum, size = info.get("sha256"), info.get("size")
    if not isinstance(checksum, str) or not SHA256_PATTERN.match(checksum.lower()):
        return None
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= UPDATE_MAX_BYTES:
        return None
    return {"url": info["url"], "sha256": checksum.lower(), "size": size}


def read_release(data, language, installed=APP_VERSION):
    """The release a downloaded file announces; None if it is not usable.

    {"version", "url", "notes", "packages"}: `packages` holds, under PACKAGE_FULL and
    PACKAGE_UPDATE, the files this copy of the program may fetch and install.
    """
    try:
        info = json.loads(data)
    except ValueError:
        return None
    if not isinstance(info, dict) or not version_numbers(info.get("version")):
        return None
    if not is_safe_url(info.get("url")):
        return None
    notes = info.get("notes", EMPTY_STRING)
    if isinstance(notes, dict):
        notes = notes.get(language) or next(iter(notes.values()), EMPTY_STRING)
    packages = {}
    full = read_package(info.get(PACKAGE_FULL))
    if full is not None:
        packages[PACKAGE_FULL] = full
    update = read_package(info.get(PACKAGE_UPDATE))
    # The small package only replaces the program's own files: it fits only over a
    # version whose libraries are the ones it was built with.
    oldest = version_numbers(info[PACKAGE_UPDATE].get("from")) if update is not None else ()
    if oldest and version_numbers(installed) >= oldest:
        packages[PACKAGE_UPDATE] = update
    return {
        "version": str(info["version"]).lstrip("v"), "url": info["url"],
        "notes": notes if isinstance(notes, str) else EMPTY_STRING, "packages": packages,
    }


def is_configured():
    return UPDATE_INFO_URL.startswith(SAFE_SCHEME)


def open_url(url, timeout):
    request = urllib.request.Request(url, headers={"User-Agent": "%s/%s" % (APP_NAME, APP_VERSION)})
    return urllib.request.urlopen(request, timeout=timeout)


def fetch_release(language):
    """The newest release there is, as read_release gives it; None if it cannot be learned right now. Blocks."""
    if not is_configured():
        return None
    try:
        with open_url(UPDATE_INFO_URL, UPDATE_TIMEOUT_SECONDS) as response:
            return read_release(response.read(MAX_INFO_BYTES), language)
    except (OSError, ValueError):
        return None


def download_package(package, target, on_progress=None):
    """Fetch a package (from read_release) to the file `target`. Blocks; raises DownloadError.

    on_progress(percent) is called as it comes in. The file appears under its own
    name only once it is whole and is what the release file said it would be.
    """
    partial = target + PARTIAL_SUFFIX
    digest, done, last_percent = hashlib.sha256(), 0, None
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open_url(package["url"], UPDATE_DOWNLOAD_TIMEOUT_SECONDS) as response, open(partial, "wb") as out:
            # The address may hand over to another one; that one must be as safe as the first.
            if not is_safe_url(response.geturl()):
                raise DownloadError(ERR_UPDATE_VERIFY_KEY)
            while True:
                chunk = response.read(UPDATE_CHUNK_BYTES)
                if not chunk:
                    break
                done += len(chunk)
                if done > package["size"]:
                    # More than was announced: not the file that was announced.
                    raise DownloadError(ERR_UPDATE_VERIFY_KEY)
                digest.update(chunk)
                out.write(chunk)
                percent = done * 100 // package["size"]
                if on_progress is not None and percent != last_percent:
                    last_percent = percent
                    on_progress(percent)
        if done != package["size"] or digest.hexdigest() != package["sha256"]:
            raise DownloadError(ERR_UPDATE_VERIFY_KEY)
        os.replace(partial, target)
    except DownloadError:
        discard(partial)
        raise
    except (OSError, ValueError) as error:
        discard(partial)
        raise DownloadError(ERR_UPDATE_DOWNLOAD_KEY) from error


def discard(path):
    try:
        os.remove(path)
    except OSError:
        pass


def describe_file(path, url):
    """What the release file says about one built installer: its address, checksum and size."""
    digest = hashlib.sha256()
    with open(path, "rb") as built:
        for chunk in iter(lambda: built.read(UPDATE_CHUNK_BYTES), b""):
            digest.update(chunk)
    return {"url": url, "sha256": digest.hexdigest(), "size": os.path.getsize(path)}
