"""Reading and writing the Windows clipboard, patiently and quietly.

wx reaches the clipboard on Windows through OLE, which fails where Windows' own clipboard calls do
not: when the clipboard is shared with another computer (Remote Desktop, whose data is fetched from
the other side only when asked for), or held for a moment by another program (clipboard managers,
Office, password managers). wx then shows its own error box, in English and in Windows' terms:
"Failed to get data from the clipboard (error -2147221040: OpenClipboard Failed)".

So text, which is all the app copies, goes through Windows' own calls. Files and pictures pasted into
the message field still come through wx, which knows their many formats, with its box kept away. Either
way a clipboard held by another program is tried again a few times, a few hundredths of a second apart;
if it stays taken, the caller says so in the app's own words, or leaves the pasting to Windows.
"""
import ctypes
import sys
import time

import wx

# Half a second at most: long enough for what holds the clipboard to let go, short enough to go unnoticed.
TRIES = 20
WAIT_SECONDS = 0.025
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
NATIVE = sys.platform == "win32"

if NATIVE:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalFree.argtypes = [wintypes.HANDLE]
    kernel32.GlobalFree.restype = wintypes.HANDLE


def try_open():
    """One try at opening the clipboard; another program may have it open just now."""
    return bool(user32.OpenClipboard(None))


def opened():
    """Open the clipboard, trying again while another program holds it; False if it never let go."""
    for attempt in range(TRIES):
        if attempt:
            time.sleep(WAIT_SECONDS)
        if try_open():
            return True
    return False


def put_text(text):
    """Put text on the clipboard; False if another program kept it the whole time."""
    if not NATIVE:
        return use(lambda clipboard: True if clipboard.SetData(wx.TextDataObject(text)) else None) is True
    data = (text + "\0").encode("utf-16-le")
    if not opened():
        return False
    try:
        if not user32.EmptyClipboard():
            return False
        memory = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not memory:
            return False
        pointer = kernel32.GlobalLock(memory)
        if not pointer:
            kernel32.GlobalFree(memory)
            return False
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(memory)
        if not user32.SetClipboardData(CF_UNICODETEXT, memory):
            # Not taken by Windows: still this program's to free.
            kernel32.GlobalFree(memory)
            return False
        return True
    finally:
        user32.CloseClipboard()


def get_text():
    """The text on the clipboard ("" if it holds none); None if another program kept it the whole time."""
    if not NATIVE:
        def read(clipboard):
            if not clipboard.IsSupported(wx.DataFormat(wx.DF_UNICODETEXT)):
                return ""
            data = wx.TextDataObject()
            return data.GetText() if clipboard.GetData(data) else None
        return use(read)
    if not opened():
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def use(work):
    """Run work(clipboard) with wx's clipboard open, for what only wx reads (files, pictures), and give
    back its answer. A clipboard taken, or an answer of None (refused part way), is tried again, with
    wx's error box kept away; None if it never got through."""
    with wx.LogNull():
        for attempt in range(TRIES):
            if attempt:
                time.sleep(WAIT_SECONDS)
            # Looked up each time: the tests put a clipboard of their own in its place.
            clipboard = wx.TheClipboard
            if not clipboard.Open():
                continue
            try:
                answer = work(clipboard)
            finally:
                clipboard.Close()
            if answer is not None:
                return answer
    return None
