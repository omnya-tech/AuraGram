"""What TelegramManager and its mixins share: the errors they raise to tell the UI why, and Telegram's tables."""
from telethon.tl import types
from core.constants import (
    MESSAGE_VIEW_PINNED, MESSAGE_VIEW_PHOTOS, MESSAGE_VIEW_FILES, MESSAGE_VIEW_VOICE, MESSAGE_VIEW_MUSIC,
    MESSAGE_VIEW_LINKS, NOTIFY_USERS, NOTIFY_GROUPS, NOTIFY_CHANNELS, MESSAGE_VIEW_MENTIONS,
)

class ChatNotFoundError(Exception):
    """No user or chat matches what was typed."""

class PhoneHiddenError(Exception):
    """The person's phone number is not visible to this account."""

class EmailNotConfirmedError(Exception):
    """The user backed out of confirming the recovery email."""

class StatsUnavailableError(Exception):
    """Telegram keeps no statistics for this chat, or does not show them to this account."""

class NoInviteLinkError(Exception):
    """This chat has no invite link, or this account may not get one."""

# Telegram's server-side filter for each message view that has one.
MESSAGE_VIEW_FILTERS = {
    MESSAGE_VIEW_PINNED: types.InputMessagesFilterPinned,
    MESSAGE_VIEW_PHOTOS: types.InputMessagesFilterPhotoVideo,
    MESSAGE_VIEW_FILES: types.InputMessagesFilterDocument,
    MESSAGE_VIEW_VOICE: types.InputMessagesFilterVoice,
    MESSAGE_VIEW_MUSIC: types.InputMessagesFilterMusic,
    MESSAGE_VIEW_LINKS: types.InputMessagesFilterUrl,
    MESSAGE_VIEW_MENTIONS: types.InputMessagesFilterMyMentions,
}
# What the download manager looks through for a chat's files: every kind that can be saved.
CHAT_FILE_FILTERS = (
    types.InputMessagesFilterPhotoVideo, types.InputMessagesFilterDocument, types.InputMessagesFilterMusic,
    types.InputMessagesFilterVoice, types.InputMessagesFilterRoundVideo, types.InputMessagesFilterGif,
)
ADMIN_LOG_ACTION_PREFIX = "ChannelAdminLogEventAction"

# Where Telegram's flag is named differently from the permission's name in the app.
BANNED_RIGHT_NAMES = {"embed_link_previews": "embed_links"}
# Telegram's flags that are not shown as permissions but are kept as they are when saving.
KEPT_BANNED_RIGHTS = ("send_games", "send_inline", "send_reactions", "edit_rank", "manage_linked_peers")

# Privacy settings offered in the app, by the name the UI uses for each.
# Telegram's name for each kind of chat that has a default notification setting.
NOTIFY_PEERS = {
    NOTIFY_USERS: types.InputNotifyUsers,
    NOTIFY_GROUPS: types.InputNotifyChats,
    NOTIFY_CHANNELS: types.InputNotifyBroadcasts,
}

PRIVACY_KEYS = {
    "last_seen": types.InputPrivacyKeyStatusTimestamp,
    "phone": types.InputPrivacyKeyPhoneNumber,
    "photo": types.InputPrivacyKeyProfilePhoto,
    "invites": types.InputPrivacyKeyChatInvite,
    "calls": types.InputPrivacyKeyPhoneCall,
    "forwards": types.InputPrivacyKeyForwards,
}
