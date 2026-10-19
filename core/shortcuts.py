"""The keyboard shortcuts of the menu commands: what each is until the user changes it,
how one is written and read back, and which combinations may not be taken at all.

A shortcut is text such as "Ctrl+Shift+S": the modifiers in that order, then one key.
It is the form the menus show, the form saved in the settings, and what wx reads
after the tab in a menu label.
"""
import wx
from core.constants import (
    MENU_CHAT_TONE_KEY, MENU_EXPORT_CHAT_KEY, MENU_CANCEL_UPLOAD_KEY, MENU_REMIND_KEY, MENU_REMINDERS_KEY,
    MENU_SETTINGS_KEY, MENU_OPEN_DOWNLOADS_KEY, MENU_DOWNLOAD_FILES_KEY, MENU_DOWNLOAD_STATUS_KEY,
    MENU_CANCEL_DOWNLOADS_KEY, MENU_LOGOUT_KEY, MENU_EXIT_KEY, MENU_NEW_CHAT_KEY,
    MENU_FIND_CHAT_KEY, MENU_SAVED_KEY, MENU_NEW_GROUP_KEY, MENU_NEW_CHANNEL_KEY, MENU_ADD_CONTACT_KEY,
    MENU_BLOCKED_KEY, MENU_FOLDERS_KEY, MENU_MARK_ALL_READ_KEY, MENU_CHAT_INFO_KEY, MENU_CHAT_MANAGE_KEY, MENU_COPY_INVITE_KEY,
    MENU_CHAT_READ_KEY, MENU_CHAT_PIN_KEY, MENU_CHAT_MUTE_KEY, MENU_CHAT_ARCHIVE_KEY, MENU_CHAT_JOIN_KEY,
    MENU_CHAT_CONTACT_KEY, MENU_CHAT_BLOCK_KEY, MENU_CHAT_CLEAR_KEY, MENU_CHAT_LEAVE_KEY, MENU_NEXT_VIEW_KEY,
    MENU_PREVIOUS_VIEW_KEY, MENU_TOPICS_KEY, MENU_STORIES_KEY, MENU_POST_STORY_KEY, MESSAGE_VIEW_PINNED,
    MESSAGE_VIEW_SCHEDULED, MESSAGE_VIEW_PHOTOS, MESSAGE_VIEW_FILES, MESSAGE_VIEW_VOICE, MESSAGE_VIEW_MUSIC,
    MESSAGE_VIEW_LINKS, MESSAGE_VIEW_MENTIONS, MENU_GO_CHATS_KEY, MENU_GO_MESSAGES_KEY, MENU_GO_INPUT_KEY,
    MENU_NEXT_UNREAD_KEY, MENU_GO_TO_DATE_KEY, MENU_GO_TO_REPLY_KEY, MENU_REPLY_KEY, MENU_EDIT_KEY,
    MENU_FORWARD_KEY, MENU_MESSAGE_SENDER_KEY, MENU_REACT_KEY, MENU_PIN_KEY, MENU_DELETE_KEY,
    MENU_READ_MESSAGE_KEY, MENU_TRANSLATE_KEY, MENU_DESCRIBE_IMAGE_KEY, MENU_COPY_KEY, MENU_COPY_LINK_KEY,
    MENU_OPEN_MEDIA_KEY, MENU_SAVE_AS_KEY, MENU_BUTTONS_KEY, MENU_OPEN_LINK_KEY, MENU_COMMENTS_KEY,
    MENU_AUDIENCE_KEY, MENU_MESSAGE_STATS_KEY, MENU_VOICE_SPEED_KEY, MENU_REPORT_KEY, MENU_MARK_KEY, MENU_UNMARK_ALL_KEY,
    MENU_SEND_FILE_KEY, MENU_RECORD_KEY, MENU_SEND_STICKER_KEY, MENU_SEND_CONTACT_KEY, MENU_SEND_LOCATION_KEY,
    MENU_NEW_POLL_KEY, MENU_SEND_SILENT_KEY, MENU_SCHEDULE_KEY, MENU_MENTION_KEY, MENU_SEND_AS_KEY,
    MENU_FIND_KEY, MENU_FIND_NEXT_KEY, MENU_SEARCH_MESSAGES_KEY, MENU_SEARCH_ALL_KEY, MENU_GLOBAL_SEARCH_KEY,
    MENU_SHORTCUTS_KEY, MENU_EXPORT_SHORTCUTS_KEY, MENU_CONNECTION_KEY, MENU_CHECK_UPDATES_KEY, MENU_PROBLEM_REPORT_KEY, MENU_ABOUT_KEY,
    MENU_LICENSE_KEY, SHORTCUT_SHOW_WINDOW, SHOW_HOTKEY_TEXT, ERR_SHORTCUT_MODIFIER_KEY,
    ERR_SHORTCUT_RESERVED_FORMAT_KEY, ERR_SHORTCUT_MENU_FORMAT_KEY, SHORTCUT_CONFLICT_LINK_FORMAT_KEY,
    SHORTCUT_CONFLICT_PROGRAM_KEY, SHORTCUT_CONFLICT_LINE_FORMAT_KEY
)
from core.settings import SETTING_SHORTCUTS

# Every command that can have a shortcut, in the order of the menus, with the one it starts
# with. Each name is the locale key of the command's menu entry, and of its row in the settings.
DEFAULTS = (
    (MENU_SETTINGS_KEY, "Ctrl+Shift+S"),
    (MENU_OPEN_DOWNLOADS_KEY, "Ctrl+Alt+O"),
    (MENU_DOWNLOAD_FILES_KEY, "Ctrl+Alt+E"),
    (MENU_DOWNLOAD_STATUS_KEY, "Ctrl+Alt+Z"),
    (MENU_CANCEL_DOWNLOADS_KEY, "Ctrl+Alt+Q"),
    (MENU_LOGOUT_KEY, "Ctrl+L"),
    (MENU_EXIT_KEY, "Ctrl+Q"),

    (MENU_NEW_CHAT_KEY, "Ctrl+N"),
    (MENU_FIND_CHAT_KEY, "Ctrl+Shift+N"),
    (MENU_SAVED_KEY, "Ctrl+Shift+M"),
    (MENU_NEW_GROUP_KEY, "Ctrl+Alt+G"),
    (MENU_NEW_CHANNEL_KEY, "Ctrl+Alt+H"),
    (MENU_ADD_CONTACT_KEY, "Ctrl+Alt+A"),
    (MENU_BLOCKED_KEY, "Ctrl+Alt+B"),
    (MENU_FOLDERS_KEY, "Ctrl+Alt+D"),
    (MENU_MARK_ALL_READ_KEY, "Ctrl+Alt+R"),
    (MENU_CHAT_INFO_KEY, "Ctrl+I"),
    (MENU_CHAT_MANAGE_KEY, "Ctrl+H"),
    (MENU_COPY_INVITE_KEY, "Ctrl+Alt+I"),
    (MENU_EXPORT_CHAT_KEY, "Ctrl+Alt+P"),
    (MENU_CHAT_READ_KEY, "Ctrl+Shift+R"),
    (MENU_CHAT_PIN_KEY, "Ctrl+P"),
    (MENU_CHAT_MUTE_KEY, "Ctrl+S"),
    (MENU_CHAT_TONE_KEY, "Ctrl+Alt+T"),
    (MENU_CHAT_ARCHIVE_KEY, "Ctrl+Shift+A"),
    (MENU_CHAT_JOIN_KEY, "Ctrl+Shift+J"),
    (MENU_CHAT_CONTACT_KEY, "Ctrl+Alt+K"),
    (MENU_CHAT_BLOCK_KEY, "Ctrl+Alt+X"),
    (MENU_CHAT_CLEAR_KEY, "Ctrl+Shift+Delete"),
    (MENU_CHAT_LEAVE_KEY, "Ctrl+Shift+X"),

    (MENU_NEXT_VIEW_KEY, "Ctrl+PgDn"),
    (MENU_PREVIOUS_VIEW_KEY, "Ctrl+PgUp"),
    (MENU_TOPICS_KEY, "Ctrl+Shift+O"),
    (MENU_STORIES_KEY, "Ctrl+Shift+Y"),
    (MENU_POST_STORY_KEY, "Ctrl+Alt+Y"),
    (MESSAGE_VIEW_PINNED, "Ctrl+1"),
    (MESSAGE_VIEW_SCHEDULED, "Ctrl+2"),
    (MESSAGE_VIEW_PHOTOS, "Ctrl+3"),
    (MESSAGE_VIEW_FILES, "Ctrl+4"),
    (MESSAGE_VIEW_VOICE, "Ctrl+5"),
    (MESSAGE_VIEW_MUSIC, "Ctrl+6"),
    (MESSAGE_VIEW_LINKS, "Ctrl+7"),
    (MESSAGE_VIEW_MENTIONS, "Ctrl+8"),

    (MENU_GO_CHATS_KEY, "Alt+1"),
    (MENU_GO_MESSAGES_KEY, "Alt+2"),
    (MENU_GO_INPUT_KEY, "Alt+3"),
    (MENU_NEXT_UNREAD_KEY, "Ctrl+U"),
    (MENU_GO_TO_DATE_KEY, "Ctrl+G"),
    (MENU_GO_TO_REPLY_KEY, "Ctrl+Shift+B"),

    (MENU_REPLY_KEY, "Ctrl+R"),
    (MENU_EDIT_KEY, "Ctrl+E"),
    (MENU_FORWARD_KEY, "Ctrl+W"),
    (MENU_MESSAGE_SENDER_KEY, "Ctrl+Shift+U"),
    (MENU_REACT_KEY, "Ctrl+J"),
    (MENU_PIN_KEY, "Ctrl+T"),
    (MENU_DELETE_KEY, "Ctrl+D"),
    (MENU_READ_MESSAGE_KEY, "F2"),
    (MENU_TRANSLATE_KEY, "Ctrl+Shift+E"),
    (MENU_DESCRIBE_IMAGE_KEY, "Ctrl+Shift+D"),
    (MENU_COPY_KEY, "Ctrl+Shift+C"),
    (MENU_COPY_LINK_KEY, "Ctrl+Alt+C"),
    (MENU_OPEN_MEDIA_KEY, "Ctrl+Alt+M"),
    (MENU_SAVE_AS_KEY, "Ctrl+Alt+S"),
    (MENU_BUTTONS_KEY, "Ctrl+B"),
    (MENU_OPEN_LINK_KEY, "Ctrl+K"),
    (MENU_COMMENTS_KEY, "Ctrl+Shift+L"),
    (MENU_AUDIENCE_KEY, "Ctrl+Shift+W"),
    (MENU_MESSAGE_STATS_KEY, "Ctrl+Alt+V"),
    (MENU_VOICE_SPEED_KEY, "Ctrl+Shift+V"),
    (MENU_REPORT_KEY, "Ctrl+Alt+W"),
    (MENU_MARK_KEY, "Ctrl+Space"),
    (MENU_UNMARK_ALL_KEY, "Ctrl+Shift+Space"),
    (MENU_REMIND_KEY, "Ctrl+Alt+N"),
    (MENU_REMINDERS_KEY, "Ctrl+Alt+J"),

    (MENU_SEND_FILE_KEY, "Ctrl+O"),
    (MENU_RECORD_KEY, "Ctrl+M"),
    (MENU_SEND_STICKER_KEY, "Ctrl+Shift+K"),
    (MENU_SEND_CONTACT_KEY, "Ctrl+Alt+U"),
    (MENU_SEND_LOCATION_KEY, "Ctrl+Alt+L"),
    (MENU_NEW_POLL_KEY, "Ctrl+Shift+P"),
    (MENU_SEND_SILENT_KEY, "Alt+Enter"),
    (MENU_SCHEDULE_KEY, "Ctrl+Shift+Enter"),
    (MENU_MENTION_KEY, "Ctrl+Shift+T"),
    (MENU_SEND_AS_KEY, "Ctrl+Shift+H"),
    (MENU_CANCEL_UPLOAD_KEY, "Ctrl+Shift+Q"),

    (MENU_FIND_KEY, "Ctrl+F"),
    (MENU_FIND_NEXT_KEY, "F3"),
    (MENU_SEARCH_MESSAGES_KEY, "Ctrl+Shift+F"),
    (MENU_SEARCH_ALL_KEY, "Ctrl+Alt+F"),
    (MENU_GLOBAL_SEARCH_KEY, "Ctrl+Shift+G"),

    (MENU_SHORTCUTS_KEY, "F1"),
    (MENU_EXPORT_SHORTCUTS_KEY, "Ctrl+Shift+F1"),
    (MENU_CONNECTION_KEY, "Ctrl+Shift+I"),
    (MENU_CHECK_UPDATES_KEY, "F5"),
    (MENU_PROBLEM_REPORT_KEY, "F8"),
    (MENU_ABOUT_KEY, "Shift+F1"),
    (MENU_LICENSE_KEY, "Ctrl+F1"),

    # Not a menu entry: it works from any program, to bring the hidden window back.
    (SHORTCUT_SHOW_WINDOW, SHOW_HOTKEY_TEXT),
)
COMMANDS = tuple(command for command, default in DEFAULTS)
# Commands whose shortcut Windows itself delivers, wherever the keyboard is.
GLOBAL_COMMANDS = (SHORTCUT_SHOW_WINDOW,)

SEPARATOR = "+"
CTRL, ALT, SHIFT = "Ctrl", "Alt", "Shift"
MODIFIERS = (CTRL, ALT, SHIFT)

# Key name -> (wx key code, Windows virtual-key code). Only keys that mean the same on every
# keyboard layout: a letter key reports its Latin letter even while it types Arabic, where the
# punctuation keys do not.
KEYS = {chr(code): (code, code) for code in list(range(ord("A"), ord("Z") + 1)) + list(range(ord("0"), ord("9") + 1))}
KEYS.update({"F%d" % number: (wx.WXK_F1 + number - 1, 0x70 + number - 1) for number in range(1, 13)})
KEYS.update({
    "Enter": (wx.WXK_RETURN, 0x0D), "Space": (wx.WXK_SPACE, 0x20),
    "PgUp": (wx.WXK_PAGEUP, 0x21), "PgDn": (wx.WXK_PAGEDOWN, 0x22),
    "End": (wx.WXK_END, 0x23), "Home": (wx.WXK_HOME, 0x24),
    "Left": (wx.WXK_LEFT, 0x25), "Up": (wx.WXK_UP, 0x26), "Right": (wx.WXK_RIGHT, 0x27), "Down": (wx.WXK_DOWN, 0x28),
    "Insert": (wx.WXK_INSERT, 0x2D), "Delete": (wx.WXK_DELETE, 0x2E),
})
FUNCTION_KEYS = tuple("F%d" % number for number in range(1, 13))
KEY_BY_WX_CODE = {wx_code: name for name, (wx_code, vk_code) in KEYS.items()}
KEY_BY_VK_CODE = {vk_code: name for name, (wx_code, vk_code) in KEYS.items()}
KEY_BY_WX_CODE[wx.WXK_NUMPAD_ENTER] = "Enter"

# What RegisterHotKey calls the modifiers.
WINDOWS_MODIFIERS = {ALT: 0x0001, CTRL: 0x0002, SHIFT: 0x0004}
WX_MODIFIERS = {ALT: wx.MOD_ALT, CTRL: wx.MOD_CONTROL, SHIFT: wx.MOD_SHIFT}

# Taken already, by Windows or by typing and moving inside the app itself. A menu shortcut
# is acted on before the key reaches a text field, so giving one of these away would break it.
RESERVED = frozenset((
    # Windows.
    "Alt+F4", "Alt+Space", "F10", "Shift+F10", "Ctrl+Alt+Delete",
    # Editing and moving in a text field.
    "Ctrl+A", "Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+Y", "Ctrl+Z", "Ctrl+Insert", "Shift+Insert", "Shift+Delete",
    "Ctrl+Delete", "Ctrl+Left", "Ctrl+Right", "Ctrl+Up", "Ctrl+Down", "Ctrl+Home", "Ctrl+End",
    "Ctrl+Shift+Left", "Ctrl+Shift+Right", "Ctrl+Shift+Up", "Ctrl+Shift+Down", "Ctrl+Shift+Home", "Ctrl+Shift+End",
    # Sending, or breaking the line, depending on the setting.
    "Ctrl+Enter",
))


def split(text):
    """(modifiers in their fixed order, key name) of a shortcut's text; None if it is not one."""
    parts = [part.strip() for part in text.split(SEPARATOR)]
    names = {name.lower(): name for name in list(KEYS) + list(MODIFIERS)}
    parts = [names.get(part.lower()) for part in parts]
    if not parts or None in parts or parts[-1] not in KEYS or len(set(parts)) != len(parts):
        return None
    if any(part not in MODIFIERS for part in parts[:-1]):
        return None
    return tuple(modifier for modifier in MODIFIERS if modifier in parts[:-1]), parts[-1]


def normalize(text):
    """The one way a shortcut is written, whatever case or order it came in; "" if it is not a shortcut."""
    parts = split(text)
    return SEPARATOR.join(parts[0] + (parts[1],)) if parts else ""


def from_key_event(event):
    """The shortcut a key press makes; "" for a modifier alone or a key no shortcut may hold."""
    key = KEY_BY_WX_CODE.get(event.GetKeyCode())
    if key is None:
        return ""
    held = {CTRL: event.ControlDown(), ALT: event.AltDown(), SHIFT: event.ShiftDown()}
    return SEPARATOR.join([modifier for modifier in MODIFIERS if held[modifier]] + [key])


def windows_hotkey(text):
    """(modifier flags, virtual-key code) as Windows' RegisterHotKey takes them."""
    modifiers, key = split(text)
    return sum(WINDOWS_MODIFIERS[modifier] for modifier in modifiers), KEYS[key][1]


def wx_hotkey(text):
    """(modifier flags, key code) as wx's RegisterHotKey takes them."""
    modifiers, key = split(text)
    return sum(WX_MODIFIERS[modifier] for modifier in modifiers), KEYS[key][0]


def from_windows_hotkey(modifiers, vk_code):
    """The shortcut Windows means by these flags and this key; "" if no shortcut here could be the same."""
    key = KEY_BY_VK_CODE.get(vk_code)
    if key is None:
        return ""
    return SEPARATOR.join([name for name in MODIFIERS if modifiers & WINDOWS_MODIFIERS[name]] + [key])


def refusal(text, command):
    """Why `text` may not be the shortcut of `command`, as the locale key of the reason; None if it may."""
    modifiers, key = split(text)
    if text in RESERVED:
        return ERR_SHORTCUT_RESERVED_FORMAT_KEY
    strong = CTRL in modifiers or ALT in modifiers
    if not strong and (key not in FUNCTION_KEYS or command in GLOBAL_COMMANDS):
        # A bare key, or one with Shift, is typing. A bare F key is fine inside the app,
        # but as a system-wide shortcut it would take that key from every other program.
        return ERR_SHORTCUT_MODIFIER_KEY
    if CTRL not in modifiers and len(key) == 1 and key.isalpha():
        # Alt with a letter opens one of the menus.
        return ERR_SHORTCUT_MENU_FORMAT_KEY
    return None


def defaults():
    return dict(DEFAULTS)


def current(settings):
    """{command: shortcut} as the user has them now; "" for a command left without one."""
    table = defaults()
    for command, text in settings.get(SETTING_SHORTCUTS).items():
        if command in table:
            table[command] = normalize(text)
    return table


def store(settings, table):
    """Keep only what differs from the defaults, so a later change of a default reaches whoever never touched it."""
    usual = defaults()
    settings.set(SETTING_SHORTCUTS, {
        command: text for command, text in table.items() if command in usual and text != usual[command]
    })


def owner(table, text, command):
    """The other command that already has this shortcut, or None."""
    for other, taken in table.items():
        if text and taken == text and other != command:
            return other
    return None


def label(i18n, command):
    """A command's name as its row in the settings and in the messages gives it: the menu entry's own words."""
    return wx.MenuItem.GetLabelText(i18n.get_string(command)).rstrip(".")


def holder_text(i18n, holder):
    """Who else answers to a shortcut, in words: `holder` is as core.key_conflicts.find gives it."""
    if holder:
        return i18n.get_string(SHORTCUT_CONFLICT_LINK_FORMAT_KEY).format(name=holder)
    return i18n.get_string(SHORTCUT_CONFLICT_PROGRAM_KEY)


def conflict_lines(i18n, table, conflicts):
    """One line for each command whose shortcut something else holds, in the order of the menus."""
    line = i18n.get_string(SHORTCUT_CONFLICT_LINE_FORMAT_KEY)
    return "\n".join(
        line.format(shortcut=table[command], command=label(i18n, command), holder=holder_text(i18n, conflicts[table[command]]))
        for command in COMMANDS if table[command] in conflicts
    )
