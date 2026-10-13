"""Who else on this computer already answers to a keyboard shortcut.

Two places are looked at. Windows is asked for the combination as a system-wide hot key:
it refuses when a running program holds it. And the shortcut files on the desktop and in
the Start menu are read, since each may carry a key combination that starts its program
from anywhere; those are known by name.
"""
import ctypes
import os
import struct
from core import shortcuts

ERROR_HOTKEY_ALREADY_REGISTERED = 1409
MOD_NOREPEAT = 0x4000
# Asked for and given back at once; the number only has to differ from the app's own.
PROBE_HOTKEY_ID = 0xB0A7
# The desktop and the Start menu, the user's own and the one shared by everybody.
LINK_FOLDER_IDS = (0x10, 0x19, 0x0B, 0x16)
LINK_EXTENSION = ".lnk"
LINK_HEADER_SIZE = 0x4C
LINK_HOTKEY_OFFSET = 0x40
# How a shortcut file names the modifiers of its key combination.
LINK_MODIFIERS = {shortcuts.SHIFT: 0x01, shortcuts.CTRL: 0x02, shortcuts.ALT: 0x04}
MAX_PATH = 260

# Shortcuts this program holds system-wide itself: Windows would refuse them as taken, by us.
own_hotkeys = set()


def taken_by_a_program(text):
    """Whether a running program other than this one holds the shortcut as a system-wide hot key."""
    if text in own_hotkeys:
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    modifiers, vk_code = shortcuts.windows_hotkey(text)
    if user32.RegisterHotKey(None, PROBE_HOTKEY_ID, modifiers | MOD_NOREPEAT, vk_code):
        user32.UnregisterHotKey(None, PROBE_HOTKEY_ID)
        return False
    return ctypes.get_last_error() == ERROR_HOTKEY_ALREADY_REGISTERED


def link_folders():
    folders = []
    for folder_id in LINK_FOLDER_IDS:
        path = ctypes.create_unicode_buffer(MAX_PATH)
        if ctypes.windll.shell32.SHGetFolderPathW(None, folder_id, None, 0, path) == 0 and path.value:
            folders.append(path.value)
    return folders


def link_hotkey(path):
    """The key combination a shortcut file starts its program with; "" if it has none."""
    try:
        with open(path, "rb") as link_file:
            header = link_file.read(LINK_HEADER_SIZE)
    except OSError:
        return ""
    if len(header) < LINK_HEADER_SIZE or struct.unpack_from("<I", header)[0] != LINK_HEADER_SIZE:
        return ""
    vk_code, flags = struct.unpack_from("<BB", header, LINK_HOTKEY_OFFSET)
    key = shortcuts.KEY_BY_VK_CODE.get(vk_code)
    if not key:
        return ""
    return shortcuts.SEPARATOR.join(
        [modifier for modifier in shortcuts.MODIFIERS if flags & LINK_MODIFIERS[modifier]] + [key]
    )


def link_hotkeys(folders=None):
    """{shortcut: name of the shortcut file that has it}, from the desktop and the Start menu."""
    found = {}
    for folder in link_folders() if folders is None else folders:
        for directory, _, names in os.walk(folder):
            for name in names:
                if name.lower().endswith(LINK_EXTENSION):
                    text = link_hotkey(os.path.join(directory, name))
                    if text:
                        found.setdefault(text, name[:-len(LINK_EXTENSION)])
    return found


def find(texts):
    """{shortcut: who holds it} for those of `texts` that something else on this computer answers to.

    The holder is the name of a shortcut file, or "" for a running program Windows does not name.
    """
    links = link_hotkeys()
    conflicts = {}
    for text in texts:
        if not text or text in own_hotkeys:
            continue
        if text in links:
            conflicts[text] = links[text]
        elif taken_by_a_program(text):
            conflicts[text] = ""
    return conflicts
