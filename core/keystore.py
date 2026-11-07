"""Keeping the user's secrets (the Gemini key, the proxy's password and secret) unreadable in the settings file.

Windows' own data protection (DPAPI) locks each one to the Windows account that saved it: the file
copied to another computer, or read by another user of this one, gives nothing away. No password is
asked for; Windows unlocks it for the same account without a word.

A locked value is stored as SEALED_PREFIX followed by base64. A value without the prefix is read as
it is: settings saved before this existed, which the next save locks.

Where DPAPI cannot be had (not on Windows) values are kept as they are, as before.
"""
import base64
import binascii
import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

SEALED_PREFIX = "dpapi:"
# Mixed into each lock, so another program of the same user cannot unlock the values by asking
# Windows alone: it must also know this.
ENTROPY = b"AuraGram settings secret"
# Never show a dialog: the program may be running out of sight, started with Windows.
CRYPTPROTECT_UI_FORBIDDEN = 0x01
AVAILABLE = sys.platform == "win32"

if AVAILABLE:
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _BLOB_ARGUMENTS = [
        ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(_Blob),
    ]
    _crypt32.CryptProtectData.argtypes = _BLOB_ARGUMENTS
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = _BLOB_ARGUMENTS
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def _blob(data):
    """A DATA_BLOB over `data`, and the buffer behind it, which must be kept alive while it is used."""
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _run(function, data):
    """CryptProtectData or CryptUnprotectData over `data`; raises OSError if Windows refuses."""
    source, source_buffer = _blob(data)
    entropy, entropy_buffer = _blob(ENTROPY)
    result = _Blob()
    if not function(
        ctypes.byref(source), None, ctypes.byref(entropy), None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(result)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        _kernel32.LocalFree(result.pbData)


def seal(text):
    """`text` locked to this Windows account, as it is stored; "" stays "". Left as it is if it cannot be
    locked: keeping the user's key readable is better than losing it."""
    if not text or not AVAILABLE:
        return text
    try:
        sealed = _run(_crypt32.CryptProtectData, text.encode("utf-8"))
    except OSError:
        logger.exception("A secret could not be locked; it is saved as it is")
        return text
    return SEALED_PREFIX + base64.b64encode(sealed).decode("ascii")


def is_sealed(stored):
    return isinstance(stored, str) and stored.startswith(SEALED_PREFIX)


def unseal(stored):
    """The text a stored value holds. A value saved unlocked comes back as it is; one that cannot be
    unlocked here (saved by another account or computer, or damaged) comes back as "", to be typed again."""
    if not is_sealed(stored):
        return stored
    if not AVAILABLE:
        logger.warning("A locked secret cannot be read on this system; it is left empty")
        return ""
    try:
        sealed = base64.b64decode(stored[len(SEALED_PREFIX):], validate=True)
        return _run(_crypt32.CryptUnprotectData, sealed).decode("utf-8")
    except (OSError, ValueError, binascii.Error):
        logger.warning("A locked secret could not be read here (another account or computer?); it is left empty")
        return ""
