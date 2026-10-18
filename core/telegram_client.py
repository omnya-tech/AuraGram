import asyncio
import datetime
import logging
import os
import platform
import threading
from telethon import TelegramClient, events
from telethon.password import compute_check
from telethon.errors import (
    UserNotParticipantError,
    PhoneCodeInvalidError, PhoneCodeExpiredError, PhoneNumberInvalidError,
    SessionPasswordNeededError, PasswordHashInvalidError, FloodWaitError,
    MessageNotModifiedError, ChatAdminRequiredError, ChatWriteForbiddenError,
    ChatNotModifiedError, ChatAboutNotModifiedError, UserAdminInvalidError,
    RightForbiddenError, UserCreatorError, MessageDeleteForbiddenError, RPCError,
    SendCodeUnavailableError, VoiceMessagesForbiddenError, ApiIdInvalidError,
    ApiIdPublishedFloodError, BotResponseTimeoutError, UsernameOccupiedError, UsernameInvalidError,
    UsernameNotModifiedError, PhotoCropSizeSmallError, ImageProcessFailedError, PhotoExtInvalidError,
    PhoneNumberOccupiedError, CodeInvalidError, UserPrivacyRestrictedError, UserNotMutualContactError,
    UserChannelsTooMuchError, MegagroupPrehistoryHiddenError, LinkNotModifiedError, MegagroupRequiredError,
    BroadcastRequiredError
)
from telethon.tl import functions, types
from telethon.utils import get_display_name, get_input_peer, get_peer_id, parse_username
from core.config import load_credentials
from core.proxy import client_arguments
from core.constants import (
    APP_VERSION, CLIENT_DEVICE_MODEL, CLIENT_SYSTEM_FORMAT,
    SESSION_NAME, EMPTY_STRING, DIALOGS_LIMIT, MESSAGES_LIMIT,
    STEP_PHONE, STEP_CODE, STEP_PASSWORD, STEP_DONE,
    ERR_CODE_INVALID_KEY, ERR_CODE_EXPIRED_KEY, ERR_PHONE_INVALID_KEY,
    ERR_PASSWORD_INVALID_KEY, ERR_FLOOD_KEY, ERR_CONNECTION_KEY, ERR_GENERAL_KEY,
    ERR_LOGOUT_KEY, MEDIA_KINDS, DOWNLOADS_DIR, MUTE_FOREVER, ERR_NO_PERMISSION_KEY,
    CHAT_FILES_LIMIT, DOWNLOADABLE_MEDIA, CHAT_EXPORT_LIMIT, CHAT_EXPORT_PAGE,
    CHAT_KIND_USER, CHAT_KIND_GROUP, CHAT_KIND_SUPERGROUP, CHAT_KIND_CHANNEL,
    MEMBER_ROLE_OWNER, MEMBER_ROLE_ADMIN, MEMBERS_LIMIT,
    MEMBER_ACTION_KICK, MEMBER_ACTION_BAN, MEMBER_ACTION_PROMOTE, MEMBER_ACTION_DEMOTE,
    MEMBER_ACTION_UNBAN, MEMBER_ROLE_BANNED, ADMIN_RIGHTS, FOLDER_CATEGORIES,
    MEMBERS_CURRENT, MEMBERS_BANNED, MEMBERS_REQUESTS, MEMBER_ROLE_PENDING, MEMBER_ROLE_RESTRICTED,
    MEMBER_ACTION_MUTE, MEMBER_ACTION_UNMUTE, MEMBER_ACTION_APPROVE, MEMBER_ACTION_DECLINE,
    CATEGORY_CONTACTS, CATEGORY_NON_CONTACTS, CATEGORY_GROUPS, CATEGORY_BROADCASTS, CATEGORY_BOTS,
    PRIVACY_EVERYONE, PRIVACY_CONTACTS, PRIVACY_NOBODY, ERR_CHAT_NOT_FOUND_KEY,
    MESSAGE_VIEW_PINNED, MESSAGE_VIEW_SCHEDULED, MESSAGE_VIEW_PHOTOS, MESSAGE_VIEW_FILES,
    MESSAGE_VIEW_VOICE, MESSAGE_VIEW_MUSIC, MESSAGE_VIEW_LINKS, ADMIN_LOG_LIMIT, MEMBER_PERMISSIONS,
    INVITE_LINKS_LIMIT, CODE_DELIVERY_KEYS, NEXT_CODE_DELIVERY_KEYS, CODE_DELIVERY_OTHER_KEY,
    ERR_NO_OTHER_DELIVERY_KEY, ERR_VOICE_FORBIDDEN_KEY, ERR_API_INVALID_KEY,
    EVENT_NEW_MESSAGE, EVENT_MESSAGE_EDITED, EVENT_MESSAGES_DELETED,
    CONNECTION_ONLINE, CONNECTION_OFFLINE, CONNECTION_WATCH_SECONDS, CONNECTION_PING_TIMEOUT_SECONDS,
    EVENT_MESSAGES_READ, EVENT_USER_STATUS, EVENT_TYPING, USER_STATUS_KEYS, TYPING_ACTION_CANCEL,
    TYPING_ACTION_TYPING, TYPING_ACTION_VOICE, TYPING_ACTION_VIDEO, TYPING_ACTION_UPLOAD, SAVED_MESSAGES_PEER,
    BLOCKED_LIMIT, GLOBAL_SEARCH_LIMIT, ERR_NO_PHONE_KEY, MAP_LINK_FORMAT, TOPICS_LIMIT, AUDIENCE_LIMIT,
    ERR_USERNAME_TAKEN_KEY, ERR_USERNAME_INVALID_KEY, ERR_PHOTO_INVALID_KEY, NOTIFY_USERS, NOTIFY_GROUPS,
    NOTIFY_CHANNELS, ERR_PREHISTORY_HIDDEN_KEY, ERR_DISCUSSION_LINK_KEY, ERR_NO_INVITE_LINK_KEY, TYPING_SEND_SECONDS, ERR_EMAIL_UNCONFIRMED_KEY, ERR_PHONE_TAKEN_KEY, DELETE_ACCOUNT_REASON, EVENT_DRAFT,
    DEFAULT_LANG, MEMBER_ACTION_RESTRICT, MEMBER_ACTION_TITLE, MEMBER_ACTION_DELETE_MESSAGES,
    SETTING_USERNAME, SETTING_SIGNATURES, SETTING_HISTORY_HIDDEN, SETTING_PROTECTED, SETTING_JOIN_TO_SEND,
    SETTING_JOIN_REQUEST, SETTING_FORUM, SETTING_SLOW_MODE, SETTING_TTL, SETTING_REACTIONS, REACTIONS_ALL,
    REACTIONS_NONE, REACTIONS_SOME, ERR_CANNOT_ADD_KEY, ERR_STATS_UNAVAILABLE_KEY, MESSAGE_VIEW_COMMENTS,
    STORY_AUDIENCES, STORY_SECONDS, MESSAGE_VIEW_MENTIONS, COMMON_CHATS_LIMIT, FOLDER_EXCLUSIONS
)

STOP_TIMEOUT_SECONDS = 5
logger = logging.getLogger(__name__)

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

# Every member permission Telethon's edit_permissions sets. The ones the app
# does not offer are still passed back unchanged when saving.
ALL_MEMBER_PERMISSIONS = MEMBER_PERMISSIONS + ("view_messages", "send_games", "send_inline")
# Where Telegram's flag is named differently from Telethon's argument.
BANNED_RIGHT_NAMES = {"embed_link_previews": "embed_links"}

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

class TelegramManager(threading.Thread):
    """Runs Telethon on its own event loop.

    ui_callback(step, error_key=None) is called from this thread: `step` is the
    login step the UI should show next, `error_key` is set when the last
    request failed.
    """

    def __init__(self, ui_callback):
        super().__init__(daemon=True)
        self.ui_callback = ui_callback
        self.api_id, self.api_hash = load_credentials()
        # The language new messages are translated into; set by the app from the user's choice.
        self.translate_lang = DEFAULT_LANG
        # How Telegram is reached, as core.proxy describes it; None for a direct connection.
        self.proxy = None
        self.loop = asyncio.new_event_loop()
        self.client = None
        self.phone = None
        self.phone_hash = None
        # Locale keys describing the login code: how it was sent, and the next way on offer.
        self.code_delivery = CODE_DELIVERY_OTHER_KEY
        self.next_code_delivery = None
        # How many digits the login code has, when Telegram says; None otherwise.
        self.code_length = None
        self.entities = {}
        # Members of the chat whose member list was loaded last.
        self.member_entities = {}
        # user id -> (admin rights as Telegram holds them, custom title), for the same list.
        self.member_admins = {}
        # chat id -> id of the newest message of ours the other side has read, where Telegram told us.
        self.read_outbox = {}
        # The stickers listed last, in the order they were offered.
        self.stickers = []
        # Kinds of chat (NOTIFY_*) silenced by default on the account; a chat with no setting of its own follows it.
        self.default_muted = set()
        # A change of phone number waiting for its code: (number, hash).
        self.phone_change = None
        self.story_items = {}
        self.story_peers = {}
        self.last_typing = (None, 0.0)
        # Folder id -> the folder as Telegram sent it, for what an edit must leave untouched.
        self.folder_filters = {}
        self.sticker_sets = {}
        self.message_listener = None
        self.connection_listener = None
        # None until the first check has answered.
        self.connection_state = None
        self.watch_task = None
        # The watcher and a request may both find the connection down at the same moment.
        self.connect_lock = asyncio.Lock()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self._create_client()
        self.loop.create_task(self._connect_async())
        self.watch_task = self.loop.create_task(self._watch_connection_async())
        self.loop.run_forever()

    def _create_client(self):
        self.client = TelegramClient(
            SESSION_NAME, self.api_id, self.api_hash,
            # How the account's list of devices names this program; Telethon's own defaults say nothing of it.
            device_model=CLIENT_DEVICE_MODEL, app_version=APP_VERSION,
            system_version=CLIENT_SYSTEM_FORMAT.format(release=platform.release()),
            lang_code=self.translate_lang, system_lang_code=self.translate_lang,
            **client_arguments(self.proxy)
        )
        self.client.add_event_handler(self._on_new_message, events.NewMessage())
        self.client.add_event_handler(self._on_message_edited, events.MessageEdited())
        self.client.add_event_handler(self._on_message_deleted, events.MessageDeleted())
        self.client.add_event_handler(self._on_messages_read, events.MessageRead())
        self.client.add_event_handler(self._on_user_update, events.UserUpdate())
        self.client.add_event_handler(self._on_draft, events.Raw(types.UpdateDraftMessage))
        self.entities = {}

    def stop(self):
        if not self.is_alive():
            return
        future = asyncio.run_coroutine_threadsafe(self._disconnect_async(), self.loop)
        try:
            future.result(timeout=STOP_TIMEOUT_SECONDS)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.join(timeout=STOP_TIMEOUT_SECONDS)

    def set_proxy(self, proxy):
        """Reach Telegram another way from now on. Connects again at once; signing in starts over
        from the phone number, while an account already signed in simply carries on."""
        asyncio.run_coroutine_threadsafe(self._set_proxy_async(proxy), self.loop)

    def send_phone(self, phone):
        asyncio.run_coroutine_threadsafe(self._send_phone_async(phone), self.loop)

    def send_code(self, code):
        asyncio.run_coroutine_threadsafe(self._send_code_async(code), self.loop)

    def resend_code(self):
        """Ask Telegram to deliver the login code another way, e.g. by voice call."""
        asyncio.run_coroutine_threadsafe(self._resend_code_async(), self.loop)

    def send_password(self, password):
        asyncio.run_coroutine_threadsafe(self._send_password_async(password), self.loop)

    def load_dialogs(self, on_result, limit=DIALOGS_LIMIT, on_progress=None):
        """The first `limit` chats of the account. on_progress(percent) is called from this thread as they come."""
        self._request(on_result, self._load_dialogs_async, limit, self._percent_reporter(on_progress))

    def load_messages(self, dialog_id, on_result, before_id=None, mark_read=True):
        """Loads the latest page of a chat, or the page before message `before_id`."""
        self._request(on_result, self._load_messages_async, dialog_id, before_id, mark_read)

    def load_profile(self, on_result):
        """The result is the account's own first_name, last_name and about text."""
        self._request(on_result, self._load_profile_async)

    def save_profile(self, profile, on_result):
        self._request(on_result, self._save_profile_async, profile)

    def set_profile_photo(self, path, on_result):
        self._request(on_result, self._set_profile_photo_async, path)

    def delete_profile_photo(self, on_result):
        """The result is False if there was no photo to delete."""
        self._request(on_result, self._delete_profile_photo_async)

    def load_two_step_state(self, on_result):
        """The result is whether the account is protected by a two-step verification password."""
        self._request(on_result, self._load_two_step_state_async)

    def change_two_step(self, current_password, new_password, hint, on_result, email=None, ask_code=None):
        """Set, change or (with no new password) remove the two-step verification password.

        With a recovery `email`, Telegram mails it a code: ask_code(reply) is then called from
        this thread, and reply(code) continues; reply(None) leaves the email unconfirmed.
        """
        self._request(on_result, self._change_two_step_async, current_password, new_password, hint, email, ask_code)

    def request_phone_change(self, phone, on_result):
        """Have Telegram send a code to the number the account is to move to."""
        self._request(on_result, self._request_phone_change_async, phone)

    def confirm_phone_change(self, code, on_result):
        self._request(on_result, self._confirm_phone_change_async, code)

    def delete_account(self, password, on_result):
        """Delete the account for good; `password` is the two-step one, if the account has it."""
        self._request(on_result, self._delete_account_async, password)

    def translate(self, dialog_id, message_id, on_result):
        """The result is the message's text in the interface language."""
        self._request(on_result, self._translate_async, dialog_id, message_id)

    def load_stories(self, on_result):
        """The result is [{"peer_id", "name", "stories": [{"id", "caption", "media", "date"}]}]."""
        self._request(on_result, self._load_stories_async)

    def open_story(self, peer_id, story_id, on_result):
        """Download a story listed by load_stories and count it as seen; the result is the file's path."""
        self._request(on_result, self._open_story_async, peer_id, story_id)

    def send_typing(self, dialog_id):
        """Let the other side see "typing"; asked often, sent at most once every few seconds."""
        asyncio.run_coroutine_threadsafe(self._send_typing_async(dialog_id), self.loop)

    def load_notify(self, on_result):
        """The result is {NOTIFY_* kind: whether its notifications are on} for the whole account."""
        self._request(on_result, self._load_notify_async)

    def save_notify(self, changes, on_result):
        self._request(on_result, self._save_notify_async, changes)

    def save_draft(self, dialog_id, text):
        """Keep what is typed in a chat on the account, so every device shows it; empty text clears it."""
        asyncio.run_coroutine_threadsafe(self._save_draft_async(dialog_id, text), self.loop)

    def set_muted(self, dialog_id, seconds, on_result):
        """Mutes a chat for `seconds`, forever with MUTE_FOREVER, or unmutes it with 0."""
        self._request(on_result, self._set_muted_async, dialog_id, seconds)

    def set_marked_unread(self, dialog_id, unread, on_result):
        """Flags a chat as unread, or removes the flag, without touching its messages."""
        self._request(on_result, self._set_marked_unread_async, dialog_id, unread)

    def set_chat_pinned(self, dialog_id, pinned, on_result):
        self._request(on_result, self._set_chat_pinned_async, dialog_id, pinned)

    def set_archived(self, dialog_id, archived, on_result):
        self._request(on_result, self._set_archived_async, dialog_id, archived)

    def clear_history(self, dialog_id, on_result):
        """Removes every message of the chat for this account only; the chat itself stays."""
        self._request(on_result, self._clear_history_async, dialog_id)

    def load_message_link(self, dialog_id, message_id, on_result):
        """The web address of a message in a channel or large group."""
        self._request(on_result, self._load_message_link_async, dialog_id, message_id)

    def load_chat_info(self, dialog_id, on_result):
        """The result describes the chat: kind, title, about, username, members_count, can_edit."""
        self._request(on_result, self._load_chat_info_async, dialog_id)

    def save_chat_info(self, dialog_id, title, about, on_result):
        """Pass None for a field that should stay as it is."""
        self._request(on_result, self._save_chat_info_async, dialog_id, title, about)

    def load_members(self, dialog_id, search, on_result, which=MEMBERS_CURRENT):
        """The result is a list of people, each with id, name, role, rights and is_self.

        `which` is one of the MEMBERS_* constants: current members, banned users, or join requests.
        """
        self._request(on_result, self._load_members_async, dialog_id, search, which)

    def load_message_view(self, dialog_id, view, on_result):
        """Loads one of the MESSAGE_VIEW_* lists of a chat: pinned, scheduled, or one kind of shared media."""
        self._request(on_result, self._load_message_view_async, dialog_id, view)

    def delete_scheduled(self, dialog_id, message_id, on_result):
        """Cancels a scheduled message before it is sent."""
        self._request(on_result, self._delete_scheduled_async, dialog_id, message_id)

    def vote(self, dialog_id, message_id, option_indexes, on_result):
        """Votes in a poll (an empty list retracts the vote); the result is the refreshed message."""
        self._request(on_result, self._vote_async, dialog_id, message_id, option_indexes)

    def send_poll(self, dialog_id, question, options, on_result, reply_to=None):
        self._request(on_result, self._send_poll_async, dialog_id, question, options, reply_to)

    def load_admin_log(self, dialog_id, on_result):
        """The result is the recent admin actions in a channel or large group, newest first."""
        self._request(on_result, self._load_admin_log_async, dialog_id)

    def leave_chat(self, dialog_id, on_result):
        """Leaves a group or channel; for a private chat, deletes it from this account's list."""
        self._request(on_result, self._leave_chat_async, dialog_id)

    def press_button(self, dialog_id, message_id, index, on_result):
        """Press the index-th button under a bot's message. The result is {"url", "answer"}:
        a link the button wants opened (nothing was pressed yet), or what the bot answered, if anything."""
        self._request(on_result, self._press_button_async, dialog_id, message_id, index)

    def open_saved_messages(self, on_result):
        """The account's chat with itself; the result is shaped like those of load_dialogs."""
        self._request(on_result, self._find_chat_async, SAVED_MESSAGES_PEER)

    def react(self, dialog_id, message_id, emoji, on_result):
        """Sets this account's reaction (None removes it); the result is the refreshed message."""
        self._request(on_result, self._react_async, dialog_id, message_id, emoji)

    def load_admin_settings(self, dialog_id, on_result):
        """What an admin can set for a group or channel. The result is {"kind", "is_owner", "can_edit",
        "can_invite", "can_view_stats", "values": {SETTING_*: its value now}}, with only the
        settings that exist for this kind of chat."""
        self._request(on_result, self._load_admin_settings_async, dialog_id)

    def save_admin_settings(self, dialog_id, changes, on_result):
        self._request(on_result, self._save_admin_settings_async, dialog_id, changes)

    def set_chat_photo(self, dialog_id, path, on_result):
        self._request(on_result, self._set_chat_photo_async, dialog_id, path)

    def add_members(self, dialog_id, user_ids, on_result):
        """Add contacts (loaded with load_contacts) to a group or channel."""
        self._request(on_result, self._add_members_async, dialog_id, user_ids)

    def load_stats(self, dialog_id, on_result):
        """The result is [(name, current, previous or None), ...]; previous None marks a percentage."""
        self._request(on_result, self._load_stats_async, dialog_id)

    def transfer_ownership(self, dialog_id, user_id, password, on_result):
        """Hand the chat to one of its admins (from the member list loaded last); needs the two-step password."""
        self._request(on_result, self._transfer_ownership_async, dialog_id, user_id, password)

    def delete_chat(self, dialog_id, on_result):
        """Delete a group or channel for everyone in it."""
        self._request(on_result, self._delete_chat_async, dialog_id)

    def manage_member(self, dialog_id, user_id, action, on_result, rights=None, title=None, seconds=None):
        """Applies one of the MEMBER_ACTION_* constants to a member loaded by load_members.

        `rights` is the set of admin right names to grant with MEMBER_ACTION_PROMOTE.
        """
        self._request(on_result, self._manage_member_async, dialog_id, user_id, action, rights, title, seconds)

    def load_folders(self, on_result):
        """The result is the account's chat folders with the rules for what belongs in each."""
        self._request(on_result, self._load_folders_async)

    def find_chat(self, query, on_result):
        """Looks up a username, phone number or link; the result is a chat like those of load_dialogs."""
        self._request(on_result, self._find_chat_async, query)

    def open_sender(self, dialog_id, message_id, on_result):
        """The private chat with whoever wrote a message, shaped like the chats of load_dialogs."""
        self._request(on_result, self._open_sender_async, dialog_id, message_id)

    def load_contacts(self, on_result):
        self._request(on_result, self._load_contacts_async)

    def add_contact(self, dialog_id, name, on_result):
        """Save the person of a private chat as a contact under `name`."""
        self._request(on_result, self._add_contact_async, dialog_id, name)

    def add_contact_by_phone(self, phone, name, on_result):
        """The result is the new contact's chat; fails as "not found" if the number is not on Telegram."""
        self._request(on_result, self._add_contact_by_phone_async, phone, name)

    def delete_contact(self, dialog_id, on_result):
        self._request(on_result, self._delete_contact_async, dialog_id)

    def load_blocked_state(self, dialog_id, on_result):
        """The result is whether this account has blocked the person of a private chat."""
        self._request(on_result, self._load_blocked_state_async, dialog_id)

    def set_blocked(self, dialog_id, blocked, on_result):
        self._request(on_result, self._set_blocked_async, dialog_id, blocked)

    def load_blocked(self, on_result):
        """The result is the blocked people, shaped like chats."""
        self._request(on_result, self._load_blocked_async)

    def search_public(self, queries, on_result):
        """Look through all of Telegram for people, groups and channels, once for each of `queries`.
        The result is every chat found, once each, with its "username" and its number of "members" when known."""
        self._request(on_result, self._search_public_async, queries)

    def resolve_link(self, text, on_result):
        """Find what a username, phone number or t.me link points to. The result is
        {"chat": the chat, or None, "invite": (hash, title) of an invitation not accepted yet, or None}."""
        self._request(on_result, self._resolve_link_async, text)

    def join_invite(self, invite_hash, on_result):
        """Accept an invitation link; the result is the chat joined."""
        self._request(on_result, self._join_invite_async, invite_hash)

    def join_chat(self, dialog_id, on_result):
        """Join a public group or channel that is open but not joined; the result is the chat, refreshed."""
        self._request(on_result, self._join_chat_async, dialog_id)

    def create_chat(self, title, about, is_channel, on_result):
        """Creates a channel or a group owned by this account; the result is the new chat."""
        self._request(on_result, self._create_chat_async, title, about, is_channel)

    def load_member_permissions(self, dialog_id, on_result):
        """The result is the set of MEMBER_PERMISSIONS names ordinary members currently have."""
        self._request(on_result, self._load_member_permissions_async, dialog_id)

    def save_member_permissions(self, dialog_id, allowed, on_result):
        self._request(on_result, self._save_member_permissions_async, dialog_id, allowed)

    def forward_message(self, from_dialog_id, message_id, to_dialog_id, on_result):
        """Forwards a message, or a list of message ids, to another chat."""
        self._request(on_result, self._forward_message_async, from_dialog_id, message_id, to_dialog_id)

    def load_sessions(self, on_result):
        """The result lists every device signed in to the account."""
        self._request(on_result, self._load_sessions_async)

    def end_session(self, session_hash, on_result):
        self._request(on_result, self._end_session_async, session_hash)

    def load_privacy(self, on_result):
        """The result maps each PRIVACY_KEYS name to a PRIVACY_* level, or None if it has exceptions."""
        self._request(on_result, self._load_privacy_async)

    def save_privacy(self, changes, on_result):
        self._request(on_result, self._save_privacy_async, changes)

    def load_invite_links(self, dialog_id, on_result):
        """The result lists the working invite links this account made for the chat."""
        self._request(on_result, self._load_invite_links_async, dialog_id)

    def create_invite_link(self, dialog_id, title, needs_approval, on_result, expire_seconds=None, usage_limit=None):
        """`needs_approval` makes joiners wait in the join requests list; the link stops working
        after `expire_seconds` or once `usage_limit` people have joined with it."""
        self._request(
            on_result, self._create_invite_link_async, dialog_id, title, needs_approval, expire_seconds, usage_limit
        )

    def create_topic(self, dialog_id, title, on_result):
        self._request(on_result, self._create_topic_async, dialog_id, title)

    def edit_topic(self, dialog_id, topic_id, on_result, title=None, closed=None):
        """Rename a forum topic, or close or reopen it; None leaves that part as it is."""
        self._request(on_result, self._edit_topic_async, dialog_id, topic_id, title, closed)

    def delete_topic(self, dialog_id, topic_id, on_result):
        """Delete a topic together with every message in it."""
        self._request(on_result, self._delete_topic_async, dialog_id, topic_id)

    def load_discussion_groups(self, on_result):
        """The groups this account could attach to a channel for its comments, shaped like chats."""
        self._request(on_result, self._load_discussion_groups_async)

    def set_discussion_group(self, dialog_id, group_id, on_result):
        """Attach a group (from load_discussion_groups) to a channel; None detaches the one it has."""
        self._request(on_result, self._set_discussion_group_async, dialog_id, group_id)

    def load_invite_link(self, dialog_id, on_result):
        """The chat's own public or main invite link, for copying or sharing. The result is the link."""
        self._request(on_result, self._load_invite_link_async, dialog_id)

    def set_reactions(self, dialog_id, emojis, on_result):
        """Allow exactly these emoji as reactions in the chat."""
        self._request(on_result, self._set_reactions_async, dialog_id, emojis)

    def load_send_as(self, dialog_id, on_result):
        """Who this account may write as in a group, shaped like chats; empty where only itself."""
        self._request(on_result, self._load_send_as_async, dialog_id)

    def set_send_as(self, dialog_id, sender_id, on_result):
        self._request(on_result, self._set_send_as_async, dialog_id, sender_id)

    def revoke_invite_link(self, dialog_id, link, on_result):
        """Stops a link from working; people who already joined with it stay."""
        self._request(on_result, self._revoke_invite_link_async, dialog_id, link)

    def set_pinned(self, dialog_id, message_id, pinned, on_result):
        self._request(on_result, self._set_pinned_async, dialog_id, message_id, pinned)

    def fetch_media(self, dialog_id, message_id, on_result, on_progress=None):
        """The message's media as bytes, held in memory only: nothing is written to the disk."""
        self._request(on_result, self._fetch_media_async, dialog_id, message_id, self._percent_reporter(on_progress))

    def download_media(self, dialog_id, message_id, on_result, folder=None, on_progress=None):
        """Saves the message's media to `folder` (the downloads folder by default); the result is the file path.
        on_progress(percent) is called from this thread as the file comes in."""
        self._request(
            on_result, self._download_media_async, dialog_id, message_id, folder or DOWNLOADS_DIR,
            self._percent_reporter(on_progress)
        )

    def _percent_reporter(self, on_progress):
        """Turn Telethon's "bytes so far, bytes in all" into whole percents, each reported once."""
        if on_progress is None:
            return None
        last = [None]

        def report(done, total):
            percent = int(done * 100 / total) if total else 0
            if percent != last[0]:
                last[0] = percent
                on_progress(percent)
        return report

    def send_message(self, dialog_id, text, on_result, reply_to=None, schedule=None, silent=False):
        """`schedule` is a datetime to deliver the message at, instead of now;
        `silent` delivers it without the sound of a notification on the other side."""
        self._request(on_result, self._send_message_async, dialog_id, text, reply_to, schedule, silent)

    def load_thread(self, dialog_id, thread_id, view, on_result):
        """The comments under a channel post (view MESSAGE_VIEW_COMMENTS) or the messages of a forum topic.

        The result is {"peer", "root", "messages"}: the chat those messages live in and the message
        they all answer, which is where anything written into the thread has to go. For a topic that
        is the group and the topic itself; comments live in the channel's discussion group.
        """
        self._request(on_result, self._load_thread_async, dialog_id, thread_id, view)

    def pin_topic(self, dialog_id, topic_id, pinned, on_result):
        self._request(on_result, self._pin_topic_async, dialog_id, topic_id, pinned)

    def post_story(self, path, caption, audience, on_result, on_progress=None):
        """Post a picture as this account's story; `audience` is one of STORY_AUDIENCES."""
        self._request(on_result, self._post_story_async, path, caption, audience, self._percent_reporter(on_progress))

    def load_topics(self, dialog_id, on_result):
        """The result is a forum group's topics as [{"id", "title", "unread"}]."""
        self._request(on_result, self._load_topics_async, dialog_id)

    def load_audience(self, dialog_id, message_id, on_result):
        """Who read a message and who reacted to it. The result is {"readers": names, or None where
        Telegram does not tell, "reactions": [(name, emoji), ...]}."""
        self._request(on_result, self._load_audience_async, dialog_id, message_id)

    def log_out(self):
        """Ends the session on Telegram, then reports the next login step through ui_callback."""
        asyncio.run_coroutine_threadsafe(self._log_out_async(), self.loop)

    def edit_message(self, dialog_id, message_id, text, on_result):
        self._request(on_result, self._edit_message_async, dialog_id, message_id, text)

    def delete_message(self, dialog_id, message_id, on_result, for_everyone=True):
        """Deletes a message, or a list of message ids: for everyone in the chat, or from this account's side only."""
        self._request(on_result, self._delete_message_async, dialog_id, message_id, for_everyone)

    def save_folder(self, folder, offered_ids, on_result):
        """Create or change a folder. `folder` is shaped like those of load_folders, with id None for a new
        one given its number here; `offered_ids` are the chats the user could tick or untick: what the
        folder holds beyond those is kept as it is."""
        self._request(on_result, self._save_folder_async, folder, offered_ids)

    def delete_folder(self, folder_id, on_result):
        self._request(on_result, self._delete_folder_async, folder_id)

    def mark_all_read(self, dialog_ids):
        for dialog_id in dialog_ids:
            self.mark_read(dialog_id)

    def report(self, dialog_id, message_ids, option, comment, on_result):
        """One step of reporting messages to Telegram, which asks its questions one at a time.

        Start with option b"". The result is {"done": True}, or {"title", "options": [(text, option), ...]}
        to choose from and call again with, or {"comment": option} to call again with a comment added.
        """
        self._request(on_result, self._report_async, dialog_id, message_ids, option, comment)

    def load_messages_around(self, dialog_id, message_id, on_result):
        """A page of the conversation with that message in the middle of it, oldest first."""
        self._request(on_result, self._load_messages_around_async, dialog_id, message_id)

    def load_messages_from(self, dialog_id, date, on_result):
        """The first page of the conversation from a day onwards, oldest first."""
        self._request(on_result, self._load_messages_from_async, dialog_id, date)

    def search_all(self, query, on_result):
        """Look through the messages of every chat. The result is [{"chat", "message"}], newest first."""
        self._request(on_result, self._search_all_async, query)

    def send_file(self, dialog_id, path, on_result, voice_note=False, on_progress=None, reply_to=None):
        self._request(
            on_result, self._send_file_async, dialog_id, path, voice_note, self._percent_reporter(on_progress), reply_to
        )

    def send_files(self, dialog_id, paths, caption, as_documents, on_result, reply_to=None, on_progress=None):
        """Send one or more files as one message; several pictures or videos become an album.
        on_progress(progress) is called from this thread as the files go up, with progress
        {"percent", "done", "total", "file", "files"}: bytes up and in all over every file,
        and which file of how many is on its way (counted from 1). Returns what cancels the sending."""
        return self._request(
            on_result, self._send_files_async, dialog_id, paths, caption, as_documents, reply_to,
            self._upload_reporter(on_progress, paths)
        )

    def _upload_reporter(self, on_progress, paths):
        """Turn Telethon's "bytes so far of this file" into the progress of all the files together,
        each whole percent reported once. Telethon sends the files of an album one after another,
        in the order given: a report after one file is whole, or a count that drops, is the next file's."""
        if on_progress is None:
            return None
        sizes = [os.path.getsize(path) if os.path.isfile(path) else 0 for path in paths]
        state = {"file": 0, "last": (0, 0), "percent": None}

        def report(done, total):
            last_done, last_total = state["last"]
            finished = last_total and last_done >= last_total and (done, total) != state["last"]
            if (finished or done < last_done) and state["file"] + 1 < len(sizes):
                state["file"] += 1
            state["last"] = (done, total)
            index = state["file"]
            # Telethon knows the size of the file it is sending better than the disk did a moment ago.
            sizes[index] = total or sizes[index]
            everything = sum(sizes)
            sent = sum(sizes[:index]) + min(done, sizes[index])
            percent = int(sent * 100 / everything) if everything else 0
            if percent != state["percent"]:
                state["percent"] = percent
                on_progress({"percent": percent, "done": sent, "total": everything, "file": index + 1, "files": len(sizes)})
        return report

    def load_sticker_sets(self, on_result):
        """The result is the installed sticker sets as [{"id", "title"}]."""
        self._request(on_result, self._load_sticker_sets_async)

    def load_stickers(self, set_id, on_result):
        """The result is the emoji each sticker of a set stands for; set_id None means the recently used."""
        self._request(on_result, self._load_stickers_async, set_id)

    def send_sticker(self, dialog_id, index, on_result, reply_to=None):
        """Send the index-th sticker of the list load_stickers gave last."""
        self._request(on_result, self._send_media_async, dialog_id, lambda: self.stickers[index], reply_to)

    def send_contact(self, dialog_id, contact_id, on_result, reply_to=None):
        """Share one of this account's contacts (loaded with load_contacts) as a contact card."""
        self._request(on_result, self._send_contact_async, dialog_id, contact_id, reply_to)

    def send_location(self, dialog_id, latitude, longitude, on_result, reply_to=None):
        point = types.InputMediaGeoPoint(types.InputGeoPoint(lat=latitude, long=longitude))
        self._request(on_result, self._send_media_async, dialog_id, lambda: point, reply_to)

    def export_messages(self, dialog_id, on_result, on_progress=None):
        """Every message of a chat, as far back as CHAT_EXPORT_LIMIT, oldest first.
        on_progress(count) is called from this thread as each batch of them comes in."""
        self._request(on_result, self._export_messages_async, dialog_id, on_progress)

    def load_chat_files(self, dialog_id, on_result):
        """Every message of a chat with a file that can be downloaded, as far back as
        CHAT_FILES_LIMIT of each kind, oldest first."""
        self._request(on_result, self._load_chat_files_async, dialog_id)

    def search_messages(self, dialog_id, query, on_result):
        """Finds the latest messages of a chat that contain `query`."""
        self._request(on_result, self._search_messages_async, dialog_id, query)

    def mark_read(self, dialog_id):
        asyncio.run_coroutine_threadsafe(self._mark_read_async(dialog_id), self.loop)

    def set_message_listener(self, listener):
        """listener(event, *details) is called from this thread when a chat changes:

        EVENT_NEW_MESSAGE, chat, message  (chat is shaped like those of load_dialogs)
        EVENT_MESSAGE_EDITED, dialog_id, message
        EVENT_MESSAGES_DELETED, dialog_id, message_ids  (dialog_id is None outside channels)
        EVENT_MESSAGES_READ, dialog_id, max_id  (the other side read our messages up to that one)
        EVENT_USER_STATUS, user_id, status  (status as in a chat's "status")
        EVENT_TYPING, dialog_id, action, name  (someone in that chat is typing, recording or sending a file:
            one of the TYPING_ACTION_* names; `name` is who, in a group, and None in a private chat)
        EVENT_DRAFT, dialog_id, text  (what is left unsent in a chat changed on another device)
        """
        self.message_listener = listener

    def set_connection_listener(self, listener):
        """listener(state) is called from this thread whenever reaching Telegram starts or stops
        working: CONNECTION_ONLINE or CONNECTION_OFFLINE."""
        self.connection_listener = listener

    def _request(self, on_result, coroutine_function, *args):
        """Run a data request; on_result(result, error_key) is called from this thread.

        Returns the request as a future: cancelling it stops the request where it is, and then
        on_result is never called."""
        return asyncio.run_coroutine_threadsafe(
            self._run_request(on_result, coroutine_function, *args), self.loop
        )

    async def _run_request(self, on_result, coroutine_function, *args):
        try:
            await self._ensure_connected()
            result = await coroutine_function(*args)
        except FloodWaitError:
            on_result(None, ERR_FLOOD_KEY)
        except ChatNotFoundError:
            on_result(None, ERR_CHAT_NOT_FOUND_KEY)
        except PhoneHiddenError:
            on_result(None, ERR_NO_PHONE_KEY)
        except UsernameOccupiedError:
            on_result(None, ERR_USERNAME_TAKEN_KEY)
        except UsernameInvalidError:
            on_result(None, ERR_USERNAME_INVALID_KEY)
        except (PhotoCropSizeSmallError, ImageProcessFailedError, PhotoExtInvalidError):
            on_result(None, ERR_PHOTO_INVALID_KEY)
        except PasswordHashInvalidError:
            on_result(None, ERR_PASSWORD_INVALID_KEY)
        except (EmailNotConfirmedError, CodeInvalidError):
            on_result(None, ERR_EMAIL_UNCONFIRMED_KEY)
        except PhoneNumberOccupiedError:
            on_result(None, ERR_PHONE_TAKEN_KEY)
        except (UserPrivacyRestrictedError, UserNotMutualContactError, UserChannelsTooMuchError):
            on_result(None, ERR_CANNOT_ADD_KEY)
        except StatsUnavailableError:
            on_result(None, ERR_STATS_UNAVAILABLE_KEY)
        except NoInviteLinkError:
            on_result(None, ERR_NO_INVITE_LINK_KEY)
        except MegagroupPrehistoryHiddenError:
            on_result(None, ERR_PREHISTORY_HIDDEN_KEY)
        except LinkNotModifiedError:
            # Already linked to that group (or already unlinked): nothing to do, not a failure.
            on_result(None, None)
        except (MegagroupRequiredError, BroadcastRequiredError):
            on_result(None, ERR_DISCUSSION_LINK_KEY)
        except PhoneNumberInvalidError:
            on_result(None, ERR_PHONE_INVALID_KEY)
        except (PhoneCodeInvalidError, PhoneCodeExpiredError):
            on_result(None, ERR_CODE_INVALID_KEY)
        except VoiceMessagesForbiddenError:
            on_result(None, ERR_VOICE_FORBIDDEN_KEY)
        except (
            ChatAdminRequiredError, ChatWriteForbiddenError, UserAdminInvalidError,
            RightForbiddenError, UserCreatorError, MessageDeleteForbiddenError
        ):
            on_result(None, ERR_NO_PERMISSION_KEY)
        except (ConnectionError, OSError):
            on_result(None, ERR_CONNECTION_KEY)
        except Exception:
            logger.exception("Telegram request failed")
            on_result(None, ERR_GENERAL_KEY)
        else:
            on_result(result, None)

    async def _load_dialogs_async(self, limit, report=None):
        try:
            self.default_muted = {kind for kind, enabled in (await self._load_notify_async()).items() if not enabled}
        except RPCError:
            # The chat list matters more than knowing which kinds of chat are silent by default.
            pass
        dialogs = []
        async for dialog in self.client.iter_dialogs(limit=limit):
            dialogs.append(dialog)
            # Telegram hands them over a page at a time: only then is there something new to tell.
            if report is not None and len(dialogs) % DIALOGS_LIMIT == 0:
                report(len(dialogs), limit)
        # update(), not replace: chats learned from live messages may not be in this page.
        self.entities.update({dialog.id: dialog.input_entity for dialog in dialogs})
        return [
            self._describe_chat(
                dialog.entity, unread=dialog.unread_count, pinned=dialog.pinned,
                muted=self._is_muted(dialog), archived=bool(dialog.archived),
                marked_unread=bool(getattr(dialog.dialog, "unread_mark", False)),
                last_message=self._describe_last_message(getattr(dialog, "message", None)),
                draft=getattr(getattr(dialog, "draft", None), "text", None) or EMPTY_STRING
            )
            for dialog in dialogs
        ]

    def _describe_last_message(self, message):
        if message is None:
            return None
        return self._describe_message(message, getattr(message, "sender", None))

    def _can_send(self, entity):
        """Whether this account may write in the chat."""
        if isinstance(entity, types.User):
            return True
        if getattr(entity, "left", False) or getattr(entity, "deactivated", False):
            return False
        if isinstance(entity, types.Channel) and not entity.megagroup:
            # A broadcast channel takes posts only from its owner and posting admins.
            return self._has_right(entity, "post_messages")
        if getattr(entity, "creator", False) or getattr(entity, "admin_rights", None):
            return True
        # Restrictions on this member in particular, then the group's rules for everyone.
        for rights in (getattr(entity, "banned_rights", None), getattr(entity, "default_banned_rights", None)):
            if rights is not None and rights.send_messages:
                return False
        return True

    def _describe_chat(self, entity, unread=0, pinned=False, muted=False, archived=False,
                       marked_unread=False, last_message=None, draft=EMPTY_STRING):
        is_user = isinstance(entity, types.User)
        return {
            "id": get_peer_id(entity), "title": get_display_name(entity),
            "unread": unread, "pinned": pinned, "muted": muted, "archived": archived,
            # Flagged unread by hand, with no unread messages behind it.
            "marked_unread": marked_unread,
            # The newest message, read or not, for the preview in the chat list.
            "last_message": last_message,
            "can_send": self._can_send(entity),
            # Only messages of channels and large groups have a web address.
            "has_links": isinstance(entity, types.Channel),
            "category": self._chat_category(entity),
            "can_delete_others": self._has_right(entity, "delete_messages"),
            # Anyone may pin in a private chat; elsewhere it takes the right.
            "can_pin": is_user or self._has_right(entity, "pin_messages"),
            # Channels and supergroups number their messages separately from everything else.
            "is_channel": isinstance(entity, types.Channel),
            # False for a public group or channel that was only opened to look at.
            "joined": not getattr(entity, "left", False),
            # A group split into topics.
            "is_forum": bool(getattr(entity, "forum", False)),
            # Text left unsent in this chat, as saved on the account by any device.
            "draft": draft,
            # For a person: when they were last around. Bots and this account itself have none.
            "status": self._describe_status(getattr(entity, "status", None))
            if is_user and not entity.bot and not entity.is_self else None,
        }

    def _describe_status(self, status):
        """(locale key, time or None) for a person's online status, or None if Telegram gives none."""
        key = USER_STATUS_KEYS.get(type(status).__name__)
        return (key, getattr(status, "was_online", None)) if key else None

    def _chat_category(self, entity):
        """Which of Telegram's folder categories a chat falls under."""
        if isinstance(entity, types.User):
            if entity.bot:
                return CATEGORY_BOTS
            return CATEGORY_CONTACTS if entity.contact else CATEGORY_NON_CONTACTS
        if isinstance(entity, types.Channel) and not entity.megagroup:
            return CATEGORY_BROADCASTS
        return CATEGORY_GROUPS

    async def _load_folders_async(self):
        result = await self.client(functions.messages.GetDialogFiltersRequest())
        folders = []
        for chat_filter in getattr(result, "filters", result):
            # The built-in "All chats" entry has no id or rules of its own.
            if not hasattr(chat_filter, "include_peers"):
                continue
            title = chat_filter.title
            self.folder_filters[chat_filter.id] = chat_filter
            included = list(chat_filter.include_peers) + list(chat_filter.pinned_peers)
            folders.append({
                "id": chat_filter.id,
                # Newer Telegram layers wrap the title in a formatted-text object.
                "title": getattr(title, "text", title),
                "include_ids": {get_peer_id(peer) for peer in included},
                "exclude_ids": {get_peer_id(peer) for peer in getattr(chat_filter, "exclude_peers", [])},
                "categories": {
                    category for category in FOLDER_CATEGORIES if getattr(chat_filter, category, False)
                },
                "exclude_muted": bool(getattr(chat_filter, "exclude_muted", False)),
                "exclude_read": bool(getattr(chat_filter, "exclude_read", False)),
                "exclude_archived": bool(getattr(chat_filter, "exclude_archived", False)),
            })
        return folders

    async def _find_chat_async(self, query):
        try:
            entity = await self.client.get_entity(query)
        except FloodWaitError:
            raise
        except (ValueError, TypeError, RPCError) as error:
            # Telethon reports an unknown username or number in several different ways.
            raise ChatNotFoundError() from error
        chat = self._describe_chat(entity)
        self.entities[chat["id"]] = get_input_peer(entity)
        return chat

    async def _open_sender_async(self, dialog_id, message_id):
        message = await self.client.get_messages(self.entities[dialog_id], ids=message_id)
        sender = getattr(message, "sender", None)
        if sender is None and hasattr(message, "get_sender"):
            sender = await message.get_sender()
        if not isinstance(sender, types.User):
            raise ChatNotFoundError()
        return self._remember_chat(sender)

    async def _load_contacts_async(self):
        result = await self.client(functions.contacts.GetContactsRequest(hash=0))
        chats = []
        for user in result.users:
            chat = self._describe_chat(user)
            self.entities[chat["id"]] = get_input_peer(user)
            chats.append(chat)
        return sorted(chats, key=lambda chat: chat["title"].casefold())

    def _remember_chat(self, entity):
        """Describe a chat that did not come from the chat list, keeping what is needed to talk to it."""
        chat = self._describe_chat(entity)
        self.entities[chat["id"]] = get_input_peer(entity)
        return chat

    async def _add_contact_async(self, dialog_id, name):
        await self.client(functions.contacts.AddContactRequest(
            id=self.entities[dialog_id], first_name=name, last_name=EMPTY_STRING, phone=EMPTY_STRING
        ))

    async def _add_contact_by_phone_async(self, phone, name):
        result = await self.client(functions.contacts.ImportContactsRequest([
            types.InputPhoneContact(client_id=0, phone=phone, first_name=name, last_name=EMPTY_STRING)
        ]))
        if not result.users:
            # Telegram answers with nobody when the number has no account.
            raise ChatNotFoundError()
        return self._remember_chat(result.users[0])

    async def _delete_contact_async(self, dialog_id):
        await self.client(functions.contacts.DeleteContactsRequest(id=[self.entities[dialog_id]]))

    async def _load_blocked_state_async(self, dialog_id):
        full = await self.client(functions.users.GetFullUserRequest(self.entities[dialog_id]))
        return bool(getattr(full.full_user, "blocked", False))

    async def _set_blocked_async(self, dialog_id, blocked):
        request = functions.contacts.BlockRequest if blocked else functions.contacts.UnblockRequest
        await self.client(request(id=self.entities[dialog_id]))

    async def _load_blocked_async(self):
        result = await self.client(functions.contacts.GetBlockedRequest(offset=0, limit=BLOCKED_LIMIT))
        return [self._remember_chat(user) for user in result.users]

    async def _search_public_async(self, queries):
        found = {}
        for query in queries:
            try:
                result = await self.client(functions.contacts.SearchRequest(q=query, limit=GLOBAL_SEARCH_LIMIT))
            except FloodWaitError:
                # Asked too often: what was found so far is still worth showing.
                if found:
                    break
                raise
            for entity in list(result.users) + list(result.chats):
                chat = self._remember_chat(entity)
                if chat["id"] not in found:
                    chat["username"] = getattr(entity, "username", None)
                    chat["members"] = getattr(entity, "participants_count", None)
                    found[chat["id"]] = chat
        return list(found.values())

    async def _resolve_link_async(self, text):
        invite_hash, is_invite = parse_username(text)
        if not is_invite:
            return {"chat": await self._find_chat_async(text), "invite": None}
        try:
            invite = await self.client(functions.messages.CheckChatInviteRequest(invite_hash))
        except FloodWaitError:
            raise
        except RPCError as error:
            # Expired, revoked or mistyped.
            raise ChatNotFoundError() from error
        if isinstance(invite, (types.ChatInviteAlready, types.ChatInvitePeek)):
            return {"chat": self._remember_chat(invite.chat), "invite": None}
        return {"chat": None, "invite": (invite_hash, invite.title)}

    async def _join_invite_async(self, invite_hash):
        result = await self.client(functions.messages.ImportChatInviteRequest(invite_hash))
        return self._remember_chat(result.chats[0])

    async def _join_chat_async(self, dialog_id):
        await self.client(functions.channels.JoinChannelRequest(self.entities[dialog_id]))
        # Asked again: joining changes what this account may do there.
        return self._remember_chat(await self.client.get_entity(self.entities[dialog_id]))

    async def _create_chat_async(self, title, about, is_channel):
        result = await self.client(functions.channels.CreateChannelRequest(
            title=title, about=about, broadcast=is_channel, megagroup=not is_channel
        ))
        entity = result.chats[0]
        chat = self._describe_chat(entity)
        self.entities[chat["id"]] = get_input_peer(entity)
        return chat

    async def _default_rights(self, dialog_id):
        entity = await self.client.get_entity(self.entities[dialog_id])
        return getattr(entity, "default_banned_rights", None)

    def _allowed_by(self, banned_rights):
        """Every permission Telethon can set -> whether members have it, read from Telegram's "banned" flags."""
        return {
            name: not getattr(banned_rights, BANNED_RIGHT_NAMES.get(name, name), False)
            for name in ALL_MEMBER_PERMISSIONS
        }

    async def _load_member_permissions_async(self, dialog_id):
        allowed = self._allowed_by(await self._default_rights(dialog_id))
        return {name for name in MEMBER_PERMISSIONS if allowed[name]}

    async def _save_member_permissions_async(self, dialog_id, allowed):
        # Start from what is set now, so permissions this app does not show stay as they are.
        permissions = self._allowed_by(await self._default_rights(dialog_id))
        permissions.update({name: name in allowed for name in MEMBER_PERMISSIONS})
        await self.client.edit_permissions(self.entities[dialog_id], **permissions)

    async def _forward_message_async(self, from_dialog_id, message_id, to_dialog_id):
        await self.client.forward_messages(
            self.entities[to_dialog_id], message_id, self.entities[from_dialog_id]
        )

    async def _load_sessions_async(self):
        result = await self.client(functions.account.GetAuthorizationsRequest())
        return [
            {
                "hash": session.hash, "current": bool(session.current),
                "device": session.device_model, "app": session.app_name,
                "platform": session.platform, "country": session.country,
                "last_active": session.date_active,
            }
            for session in result.authorizations
        ]

    async def _end_session_async(self, session_hash):
        await self.client(functions.account.ResetAuthorizationRequest(hash=session_hash))

    async def _load_privacy_async(self):
        privacy = {}
        for name, key_type in PRIVACY_KEYS.items():
            result = await self.client(functions.account.GetPrivacyRequest(key_type()))
            privacy[name] = self._privacy_level(result.rules)
        return privacy

    def _privacy_level(self, rules):
        """Everyone, contacts or nobody; None when the setting also has per-person
        exceptions, which this simple three-way choice cannot represent."""
        kinds = {type(rule) for rule in rules}
        if kinds == {types.PrivacyValueAllowAll}:
            return PRIVACY_EVERYONE
        if kinds and kinds <= {types.PrivacyValueAllowContacts, types.PrivacyValueDisallowAll}:
            if types.PrivacyValueAllowContacts in kinds:
                return PRIVACY_CONTACTS
            return PRIVACY_NOBODY
        return None

    async def _save_privacy_async(self, changes):
        rules = {
            PRIVACY_EVERYONE: [types.InputPrivacyValueAllowAll()],
            PRIVACY_CONTACTS: [types.InputPrivacyValueAllowContacts()],
            PRIVACY_NOBODY: [types.InputPrivacyValueDisallowAll()],
        }
        for name, level in changes.items():
            await self.client(functions.account.SetPrivacyRequest(PRIVACY_KEYS[name](), rules[level]))

    async def _load_invite_links_async(self, dialog_id):
        result = await self.client(functions.messages.GetExportedChatInvitesRequest(
            peer=self.entities[dialog_id], admin_id=types.InputUserSelf(), limit=INVITE_LINKS_LIMIT
        ))
        return [
            {
                "link": invite.link,
                "title": getattr(invite, "title", None) or EMPTY_STRING,
                "uses": getattr(invite, "usage", None) or 0,
                # The chat's main link; Telegram replaces it when revoked instead of removing it.
                "permanent": bool(getattr(invite, "permanent", False)),
                "needs_approval": bool(getattr(invite, "request_needed", False)),
                "expires": getattr(invite, "expire_date", None),
                "limit": getattr(invite, "usage_limit", None),
            }
            # Skip link kinds without an address of their own.
            for invite in result.invites if getattr(invite, "link", None)
        ]

    async def _create_invite_link_async(self, dialog_id, title, needs_approval, expire_seconds, usage_limit):
        expires = None
        if expire_seconds:
            expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=expire_seconds)
        await self.client(functions.messages.ExportChatInviteRequest(
            peer=self.entities[dialog_id], title=title or None, request_needed=needs_approval,
            expire_date=expires, usage_limit=usage_limit
        ))

    async def _create_topic_async(self, dialog_id, title):
        await self.client(functions.messages.CreateForumTopicRequest(peer=self.entities[dialog_id], title=title))

    async def _edit_topic_async(self, dialog_id, topic_id, title, closed):
        await self.client(functions.messages.EditForumTopicRequest(
            peer=self.entities[dialog_id], topic_id=topic_id, title=title, closed=closed
        ))

    async def _delete_topic_async(self, dialog_id, topic_id):
        await self.client(functions.messages.DeleteTopicHistoryRequest(
            peer=self.entities[dialog_id], top_msg_id=topic_id
        ))

    async def _load_discussion_groups_async(self):
        result = await self.client(functions.channels.GetGroupsForDiscussionRequest())
        # Small basic groups are listed too, but have to be upgraded before they can be attached.
        return [self._remember_chat(chat) for chat in result.chats if isinstance(chat, types.Channel)]

    async def _load_invite_link_async(self, dialog_id):
        entity = await self.client.get_entity(self.entities[dialog_id])
        username = getattr(entity, "username", None)
        if username:
            # A public chat's address is its link, the one anyone can share.
            return "https://t.me/" + username
        if isinstance(entity, types.User):
            # A person with no username has no link to share; a private chat is not invited into.
            raise NoInviteLinkError()
        try:
            if isinstance(entity, types.Channel):
                full = (await self.client(functions.channels.GetFullChannelRequest(entity))).full_chat
            else:
                full = (await self.client(functions.messages.GetFullChatRequest(entity.id))).full_chat
            invite = getattr(full, "exported_invite", None)
            if invite is not None and getattr(invite, "link", None):
                return invite.link
            # None yet: make the main one. legacy_revoke_permanent keeps it the chat's primary link.
            result = await self.client(functions.messages.ExportChatInviteRequest(
                peer=self.entities[dialog_id], legacy_revoke_permanent=True
            ))
            return result.link
        except (ChatAdminRequiredError, ValueError) as error:
            raise NoInviteLinkError() from error

    async def _set_discussion_group_async(self, dialog_id, group_id):
        group = self.entities[group_id] if group_id is not None else types.InputChannelEmpty()
        await self.client(functions.channels.SetDiscussionGroupRequest(broadcast=self.entities[dialog_id], group=group))

    async def _set_reactions_async(self, dialog_id, emojis):
        await self.client(functions.messages.SetChatAvailableReactionsRequest(
            peer=self.entities[dialog_id],
            available_reactions=types.ChatReactionsSome([types.ReactionEmoji(emoticon=emoji) for emoji in emojis])
        ))

    async def _load_send_as_async(self, dialog_id):
        result = await self.client(functions.channels.GetSendAsRequest(peer=self.entities[dialog_id]))
        return [self._remember_chat(sender) for sender in list(result.chats) + list(result.users)]

    async def _set_send_as_async(self, dialog_id, sender_id):
        await self.client(functions.messages.SaveDefaultSendAsRequest(
            peer=self.entities[dialog_id], send_as=self.entities[sender_id]
        ))

    async def _revoke_invite_link_async(self, dialog_id, link):
        await self.client(functions.messages.EditExportedChatInviteRequest(
            peer=self.entities[dialog_id], link=link, revoked=True
        ))

    def _has_right(self, entity, right):
        """Whether this account holds an admin right in a group or channel."""
        if getattr(entity, "creator", False):
            return True
        rights = getattr(entity, "admin_rights", None)
        return bool(rights and getattr(rights, right, False))

    def _is_muted(self, dialog):
        mute_until = getattr(dialog.dialog.notify_settings, "mute_until", None)
        if mute_until is None:
            # No setting of its own: the chat follows the account's default for its kind.
            return self._notify_kind(dialog.entity) in self.default_muted
        return self._is_in_future(mute_until)

    def _is_in_future(self, mute_until):
        return bool(mute_until) and mute_until > datetime.datetime.now(datetime.timezone.utc)

    def _notify_kind(self, entity):
        if isinstance(entity, types.User):
            return NOTIFY_USERS
        if isinstance(entity, types.Channel) and not entity.megagroup:
            return NOTIFY_CHANNELS
        return NOTIFY_GROUPS

    async def _load_notify_async(self):
        enabled = {}
        for kind, peer in NOTIFY_PEERS.items():
            settings = await self.client(functions.account.GetNotifySettingsRequest(peer=peer()))
            enabled[kind] = not self._is_in_future(getattr(settings, "mute_until", None))
        return enabled

    async def _save_notify_async(self, changes):
        for kind, enabled in changes.items():
            await self.client(functions.account.UpdateNotifySettingsRequest(
                peer=NOTIFY_PEERS[kind](),
                settings=types.InputPeerNotifySettings(mute_until=0 if enabled else MUTE_FOREVER)
            ))

    async def _save_draft_async(self, dialog_id, text):
        # Best effort: a draft that fails to sync is still kept in the app.
        try:
            await self.client(functions.messages.SaveDraftRequest(peer=self.entities[dialog_id], message=text))
        except Exception:
            pass

    async def _log_out_async(self):
        try:
            await self._ensure_connected()
            logged_out = await self.client.log_out()
        except Exception:
            logger.exception("Telegram request failed")
            logged_out = False
        if not logged_out:
            # Still signed in: send the UI back to the main window with the reason.
            self.ui_callback(STEP_DONE, ERR_LOGOUT_KEY)
            return
        # log_out() deletes the session, so the old client cannot be reused.
        self._create_client()
        await self._connect_async()

    async def _load_profile_async(self):
        full = await self.client(functions.users.GetFullUserRequest("me"))
        me = full.users[0]
        return {
            "first_name": me.first_name or EMPTY_STRING,
            "last_name": me.last_name or EMPTY_STRING,
            "about": full.full_user.about or EMPTY_STRING,
            "username": me.username or EMPTY_STRING,
        }

    async def _save_profile_async(self, profile):
        await self.client(functions.account.UpdateProfileRequest(
            first_name=profile["first_name"], last_name=profile["last_name"], about=profile["about"]
        ))
        try:
            await self.client(functions.account.UpdateUsernameRequest(profile["username"].lstrip("@")))
        except UsernameNotModifiedError:
            # The usual case: the name was not what the user changed.
            pass

    async def _set_profile_photo_async(self, path):
        await self.client(functions.photos.UploadProfilePhotoRequest(file=await self.client.upload_file(path)))

    async def _delete_profile_photo_async(self):
        photos = await self.client.get_profile_photos("me", limit=1)
        if not photos:
            return False
        photo = photos[0]
        await self.client(functions.photos.DeletePhotosRequest(id=[
            types.InputPhoto(id=photo.id, access_hash=photo.access_hash, file_reference=photo.file_reference)
        ]))
        return True

    async def _load_two_step_state_async(self):
        return bool((await self.client(functions.account.GetPasswordRequest())).has_password)

    async def _change_two_step_async(self, current_password, new_password, hint, email, ask_code):
        async def code_from_user(length):
            # The loop must stay free while the user goes to read their mail.
            answer = self.loop.create_future()
            ask_code(lambda code: self.loop.call_soon_threadsafe(answer.set_result, code))
            code = await answer
            if not code:
                raise EmailNotConfirmedError()
            return code

        await self.client.edit_2fa(
            current_password=current_password or None, new_password=new_password or None,
            hint=hint or EMPTY_STRING, email=email or None, email_code_callback=code_from_user if email else None
        )

    async def _request_phone_change_async(self, phone):
        sent = await self.client(functions.account.SendChangePhoneCodeRequest(
            phone_number=phone, settings=types.CodeSettings()
        ))
        self.phone_change = (phone, sent.phone_code_hash)

    async def _confirm_phone_change_async(self, code):
        phone, phone_hash = self.phone_change
        await self.client(functions.account.ChangePhoneRequest(
            phone_number=phone, phone_code_hash=phone_hash, phone_code=code
        ))
        self.phone_change = None

    async def _delete_account_async(self, password):
        proof = None
        if password:
            proof = compute_check(await self.client(functions.account.GetPasswordRequest()), password)
        await self.client(functions.account.DeleteAccountRequest(reason=DELETE_ACCOUNT_REASON, password=proof))

    async def _translate_async(self, dialog_id, message_id):
        result = await self.client(functions.messages.TranslateTextRequest(
            to_lang=self.translate_lang, peer=self.entities[dialog_id], id=[message_id]
        ))
        return result.result[0].text

    async def _load_stories_async(self):
        result = await self.client(functions.stories.GetAllStoriesRequest())
        owners = list(getattr(result, "users", [])) + list(getattr(result, "chats", []))
        names = {get_peer_id(owner): get_display_name(owner) for owner in owners}
        self.story_peers = {get_peer_id(owner): get_input_peer(owner) for owner in owners}
        self.story_items = {}
        groups = []
        for peer_stories in getattr(result, "peer_stories", []):
            peer_id = get_peer_id(peer_stories.peer)
            stories = []
            for story in peer_stories.stories:
                # Stories Telegram only names by id (expired, or not loaded) have nothing to open.
                if getattr(story, "media", None) is None:
                    continue
                self.story_items[(peer_id, story.id)] = story
                is_photo = isinstance(story.media, types.MessageMediaPhoto)
                stories.append({
                    "id": story.id, "caption": getattr(story, "caption", None) or EMPTY_STRING,
                    "media": "MEDIA_PHOTO" if is_photo else "MEDIA_VIDEO", "date": story.date,
                })
            if stories:
                groups.append({"peer_id": peer_id, "name": names.get(peer_id, EMPTY_STRING), "stories": stories})
        return groups

    async def _open_story_async(self, peer_id, story_id):
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        path = await self.client.download_media(self.story_items[(peer_id, story_id)].media, file=DOWNLOADS_DIR + os.sep)
        if not path:
            raise ValueError("story has no downloadable media")
        try:
            await self.client(functions.stories.ReadStoriesRequest(peer=self.story_peers[peer_id], max_id=story_id))
        except Exception:
            # Best effort: the story was opened whether or not Telegram hears of it.
            pass
        return path

    async def _send_typing_async(self, dialog_id):
        now = self.loop.time()
        if self.last_typing[0] == dialog_id and now - self.last_typing[1] < TYPING_SEND_SECONDS:
            return
        self.last_typing = (dialog_id, now)
        try:
            await self.client(functions.messages.SetTypingRequest(
                peer=self.entities[dialog_id], action=types.SendMessageTypingAction()
            ))
        except Exception:
            pass

    async def _set_muted_async(self, dialog_id, seconds):
        if seconds in (0, MUTE_FOREVER):
            mute_until = seconds
        else:
            mute_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
        await self.client(functions.account.UpdateNotifySettingsRequest(
            peer=types.InputNotifyPeer(self.entities[dialog_id]),
            settings=types.InputPeerNotifySettings(mute_until=mute_until)
        ))

    async def _set_marked_unread_async(self, dialog_id, unread):
        await self.client(functions.messages.MarkDialogUnreadRequest(
            peer=types.InputDialogPeer(self.entities[dialog_id]), unread=unread
        ))

    async def _set_chat_pinned_async(self, dialog_id, pinned):
        await self.client(functions.messages.ToggleDialogPinRequest(
            peer=types.InputDialogPeer(self.entities[dialog_id]), pinned=pinned
        ))

    async def _set_archived_async(self, dialog_id, archived):
        # Telegram's folder 1 is the archive, folder 0 the main list.
        await self.client.edit_folder(self.entities[dialog_id], 1 if archived else 0)

    async def _clear_history_async(self, dialog_id):
        entity = self.entities[dialog_id]
        if isinstance(entity, types.InputPeerChannel):
            await self.client(functions.channels.DeleteHistoryRequest(channel=entity, max_id=0))
            return
        # Telegram clears a long history in several rounds and says when none are left.
        while True:
            result = await self.client(functions.messages.DeleteHistoryRequest(
                peer=entity, max_id=0, just_clear=True, revoke=False
            ))
            if not getattr(result, "offset", 0):
                return

    async def _load_message_link_async(self, dialog_id, message_id):
        result = await self.client(functions.channels.ExportMessageLinkRequest(
            channel=self.entities[dialog_id], id=message_id
        ))
        return result.link

    async def _load_chat_info_async(self, dialog_id):
        entity = await self.client.get_entity(self.entities[dialog_id])
        info = {
            "title": get_display_name(entity),
            "username": getattr(entity, "username", None) or EMPTY_STRING,
            "about": EMPTY_STRING, "members_count": None,
            "can_edit": False, "can_ban": False, "can_promote": False, "can_invite": False,
            "phone": EMPTY_STRING, "common_chats": [],
        }
        if isinstance(entity, types.User):
            full = await self.client(functions.users.GetFullUserRequest(entity))
            info["kind"] = CHAT_KIND_USER
            info["about"] = full.full_user.about or EMPTY_STRING
            # Shown only where the person lets this account see it.
            info["phone"] = getattr(entity, "phone", None) or EMPTY_STRING
            common = await self.client(functions.messages.GetCommonChatsRequest(
                user_id=entity, max_id=0, limit=COMMON_CHATS_LIMIT
            ))
            info["common_chats"] = [get_display_name(chat) for chat in getattr(common, "chats", [])]
            return info

        if isinstance(entity, types.Channel):
            full = await self.client(functions.channels.GetFullChannelRequest(entity))
            info["kind"] = CHAT_KIND_SUPERGROUP if entity.megagroup else CHAT_KIND_CHANNEL
            info["members_count"] = full.full_chat.participants_count
        else:
            full = await self.client(functions.messages.GetFullChatRequest(entity.id))
            info["kind"] = CHAT_KIND_GROUP
            info["members_count"] = getattr(entity, "participants_count", None)
        info["about"] = full.full_chat.about or EMPTY_STRING
        rights = getattr(entity, "admin_rights", None)
        is_owner = bool(getattr(entity, "creator", False))
        info["can_edit"] = is_owner or bool(rights and rights.change_info)
        info["can_ban"] = is_owner or bool(rights and rights.ban_users)
        info["can_promote"] = is_owner or bool(rights and rights.add_admins)
        info["can_invite"] = is_owner or bool(rights and rights.invite_users)
        return info

    async def _save_chat_info_async(self, dialog_id, title, about):
        entity = self.entities[dialog_id]
        try:
            if title is not None:
                if isinstance(entity, types.InputPeerChannel):
                    await self.client(functions.channels.EditTitleRequest(entity, title))
                else:
                    await self.client(functions.messages.EditChatTitleRequest(entity.chat_id, title))
            if about is not None:
                await self.client(functions.messages.EditChatAboutRequest(entity, about))
        except (ChatNotModifiedError, ChatAboutNotModifiedError):
            # Saving the same value again is not a failure.
            pass

    async def _load_members_async(self, dialog_id, search, which):
        entity = self.entities[dialog_id]
        if which == MEMBERS_REQUESTS:
            result = await self.client(functions.messages.GetChatInviteImportersRequest(
                peer=entity, requested=True, q=search or None,
                offset_date=None, offset_user=types.InputUserEmpty(), limit=MEMBERS_LIMIT
            ))
            waiting = {importer.user_id for importer in result.importers}
            participants = [user for user in result.users if user.id in waiting]
        else:
            participants = await self.client.get_participants(
                entity, limit=MEMBERS_LIMIT, search=search,
                filter=types.ChannelParticipantsKicked if which == MEMBERS_BANNED else None
            )
        fixed_role = {MEMBERS_BANNED: MEMBER_ROLE_BANNED, MEMBERS_REQUESTS: MEMBER_ROLE_PENDING}.get(which)
        self.member_entities = {user.id: get_input_peer(user) for user in participants}
        self.member_admins = {
            user.id: (
                getattr(getattr(user, "participant", None), "admin_rights", None),
                getattr(getattr(user, "participant", None), "rank", None) or EMPTY_STRING
            )
            for user in participants
        }
        return [
            {
                "id": user.id,
                "name": get_display_name(user) or EMPTY_STRING,
                "username": getattr(user, "username", None),
                "role": fixed_role or self._member_role(getattr(user, "participant", None)),
                "rights": self._member_rights(getattr(user, "participant", None)),
                # The custom title shown beside an admin's name.
                "title": self.member_admins[user.id][1],
                "is_self": bool(user.is_self),
            }
            for user in participants
        ]

    def _member_rights(self, participant):
        rights = getattr(participant, "admin_rights", None)
        return {name for name in ADMIN_RIGHTS if getattr(rights, name, False)}

    async def _set_admin_async(self, entity, user, user_id, rights=None, title=None):
        """Give a channel or large group admin exactly `rights` and `title`; None keeps what they have."""
        current, rank = self.member_admins.get(user_id, (None, EMPTY_STRING))
        # Start from what Telegram holds, so rights this app does not show stay as they are.
        flags = {name: value for name, value in (current.to_dict() if current else {}).items() if name != "_"}
        if rights is not None:
            flags.update({name: name in rights for name in ADMIN_RIGHTS})
        await self.client(functions.channels.EditAdminRequest(
            channel=entity, user_id=user, admin_rights=types.ChatAdminRights(**flags),
            rank=rank if title is None else title
        ))

    async def _load_admin_settings_async(self, dialog_id):
        entity = await self.client.get_entity(self.entities[dialog_id])
        is_channel = isinstance(entity, types.Channel)
        if is_channel:
            full = (await self.client(functions.channels.GetFullChannelRequest(entity))).full_chat
        else:
            full = (await self.client(functions.messages.GetFullChatRequest(entity.id))).full_chat
        values = {
            SETTING_PROTECTED: bool(getattr(entity, "noforwards", False)),
            SETTING_TTL: getattr(full, "ttl_period", None) or 0,
            SETTING_REACTIONS: self._reactions_kind(getattr(full, "available_reactions", None)),
        }
        if is_channel:
            values[SETTING_USERNAME] = getattr(entity, "username", None) or EMPTY_STRING
            if entity.megagroup:
                values[SETTING_SLOW_MODE] = getattr(full, "slowmode_seconds", None) or 0
                values[SETTING_HISTORY_HIDDEN] = bool(getattr(full, "hidden_prehistory", False))
                values[SETTING_JOIN_TO_SEND] = bool(getattr(entity, "join_to_send", False))
                values[SETTING_JOIN_REQUEST] = bool(getattr(entity, "join_request", False))
                values[SETTING_FORUM] = bool(getattr(entity, "forum", False))
            else:
                values[SETTING_SIGNATURES] = bool(getattr(entity, "signatures", False))
        rights = getattr(entity, "admin_rights", None)
        is_owner = bool(getattr(entity, "creator", False))
        if is_channel:
            kind = CHAT_KIND_SUPERGROUP if entity.megagroup else CHAT_KIND_CHANNEL
        else:
            kind = CHAT_KIND_GROUP
        return {
            "kind": kind, "is_owner": is_owner,
            "can_edit": is_owner or bool(rights and rights.change_info),
            "can_invite": is_owner or bool(rights and rights.invite_users),
            "can_view_stats": bool(getattr(full, "can_view_stats", False)),
            "can_manage_topics": is_owner or bool(rights and getattr(rights, "manage_topics", False)),
            # The emoji allowed as reactions, where the chat allows only some.
            "reactions": [
                reaction.emoticon
                for reaction in getattr(getattr(full, "available_reactions", None), "reactions", None) or []
                if isinstance(reaction, types.ReactionEmoji)
            ],
            "values": values,
        }

    def _reactions_kind(self, reactions):
        if isinstance(reactions, types.ChatReactionsAll):
            return REACTIONS_ALL
        return REACTIONS_SOME if isinstance(reactions, types.ChatReactionsSome) else REACTIONS_NONE

    async def _save_admin_settings_async(self, dialog_id, changes):
        entity = self.entities[dialog_id]
        channel_requests = {
            SETTING_USERNAME: lambda value: functions.channels.UpdateUsernameRequest(entity, value.lstrip("@")),
            SETTING_SIGNATURES: lambda value: functions.channels.ToggleSignaturesRequest(entity, signatures_enabled=value),
            SETTING_HISTORY_HIDDEN: lambda value: functions.channels.TogglePreHistoryHiddenRequest(entity, value),
            SETTING_JOIN_TO_SEND: lambda value: functions.channels.ToggleJoinToSendRequest(entity, value),
            SETTING_JOIN_REQUEST: lambda value: functions.channels.ToggleJoinRequestRequest(entity, value),
            SETTING_FORUM: lambda value: functions.channels.ToggleForumRequest(entity, enabled=value, tabs=False),
            SETTING_SLOW_MODE: lambda value: functions.channels.ToggleSlowModeRequest(entity, value),
            SETTING_PROTECTED: lambda value: functions.messages.ToggleNoForwardsRequest(entity, value),
            SETTING_TTL: lambda value: functions.messages.SetHistoryTTLRequest(entity, value),
            SETTING_REACTIONS: lambda value: functions.messages.SetChatAvailableReactionsRequest(
                entity, types.ChatReactionsAll() if value == REACTIONS_ALL else types.ChatReactionsNone()
            ),
        }
        for name, value in changes.items():
            await self.client(channel_requests[name](value))

    async def _set_chat_photo_async(self, dialog_id, path):
        entity = self.entities[dialog_id]
        photo = types.InputChatUploadedPhoto(file=await self.client.upload_file(path))
        if isinstance(entity, types.InputPeerChannel):
            await self.client(functions.channels.EditPhotoRequest(entity, photo))
        else:
            await self.client(functions.messages.EditChatPhotoRequest(entity.chat_id, photo))

    async def _add_members_async(self, dialog_id, user_ids):
        entity = self.entities[dialog_id]
        users = [self.entities[user_id] for user_id in user_ids]
        if isinstance(entity, types.InputPeerChannel):
            await self.client(functions.channels.InviteToChannelRequest(entity, users))
        else:
            for user in users:
                await self.client(functions.messages.AddChatUserRequest(entity.chat_id, user, fwd_limit=50))

    async def _load_stats_async(self, dialog_id):
        entity = await self.client.get_entity(self.entities[dialog_id])
        is_group = bool(getattr(entity, "megagroup", False))
        request = functions.stats.GetMegagroupStatsRequest if is_group else functions.stats.GetBroadcastStatsRequest
        try:
            stats = await self.client(request(self.entities[dialog_id]))
        except FloodWaitError:
            raise
        except (RPCError, TypeError) as error:
            # Too small a chat, no right to see them, or not a channel at all.
            raise StatsUnavailableError() from error
        names = ("members", "messages", "viewers", "posters") if is_group else (
            "followers", "views_per_post", "shares_per_post", "reactions_per_post"
        )
        rows = [(name, getattr(stats, name).current, getattr(stats, name).previous) for name in names]
        notifications = getattr(stats, "enabled_notifications", None)
        if notifications is not None and notifications.total:
            rows.append(("enabled_notifications", round(notifications.part * 100 / notifications.total, 1), None))
        return rows

    async def _transfer_ownership_async(self, dialog_id, user_id, password):
        proof = compute_check(await self.client(functions.account.GetPasswordRequest()), password)
        await self.client(functions.messages.EditChatCreatorRequest(
            peer=self.entities[dialog_id], user_id=self.member_entities[user_id], password=proof
        ))

    async def _delete_chat_async(self, dialog_id):
        entity = self.entities[dialog_id]
        if isinstance(entity, types.InputPeerChannel):
            await self.client(functions.channels.DeleteChannelRequest(entity))
        else:
            await self.client(functions.messages.DeleteChatRequest(entity.chat_id))

    async def _manage_member_async(self, dialog_id, user_id, action, rights, title, seconds):
        entity = self.entities[dialog_id]
        user = self.member_entities[user_id]
        if action == MEMBER_ACTION_KICK:
            await self.client.kick_participant(entity, user)
        elif action == MEMBER_ACTION_BAN:
            await self.client.edit_permissions(entity, user, view_messages=False)
        elif action in (MEMBER_ACTION_UNBAN, MEMBER_ACTION_UNMUTE):
            # Default permissions: lifts a ban or restriction without re-adding the user.
            await self.client.edit_permissions(entity, user)
        elif action == MEMBER_ACTION_MUTE:
            await self.client.edit_permissions(entity, user, send_messages=False)
        elif action in (MEMBER_ACTION_APPROVE, MEMBER_ACTION_DECLINE):
            await self.client(functions.messages.HideChatJoinRequestRequest(
                peer=entity, user_id=user, approved=action == MEMBER_ACTION_APPROVE
            ))
        elif action == MEMBER_ACTION_PROMOTE:
            if isinstance(entity, types.InputPeerChat):
                # Small basic groups have a single admin level, no separate rights.
                await self.client.edit_admin(entity, user, is_admin=True)
            else:
                # Each right is set explicitly, so nothing is granted that was not chosen.
                await self._set_admin_async(entity, user, user_id, rights=rights)
        elif action == MEMBER_ACTION_TITLE:
            await self._set_admin_async(entity, user, user_id, title=title)
        elif action == MEMBER_ACTION_RESTRICT:
            until = datetime.timedelta(seconds=seconds) if seconds else None
            await self.client.edit_permissions(
                entity, user, until, **{name: name in rights for name in MEMBER_PERMISSIONS}
            )
        elif action == MEMBER_ACTION_DELETE_MESSAGES:
            await self.client(functions.channels.DeleteParticipantHistoryRequest(channel=entity, participant=user))
        elif action == MEMBER_ACTION_DEMOTE:
            await self.client.edit_admin(entity, user, is_admin=False)

    async def _set_pinned_async(self, dialog_id, message_id, pinned):
        entity = self.entities[dialog_id]
        if pinned:
            await self.client.pin_message(entity, message_id, notify=False)
        else:
            await self.client.unpin_message(entity, message_id)

    def _member_role(self, participant):
        if isinstance(participant, (types.ChannelParticipantCreator, types.ChatParticipantCreator)):
            return MEMBER_ROLE_OWNER
        if isinstance(participant, (types.ChannelParticipantAdmin, types.ChatParticipantAdmin)):
            return MEMBER_ROLE_ADMIN
        # Still a member, but with some permission taken away.
        if isinstance(participant, types.ChannelParticipantBanned) and not participant.left:
            return MEMBER_ROLE_RESTRICTED
        return None

    async def _load_messages_async(self, dialog_id, before_id, mark_read):
        entity = self.entities[dialog_id]
        messages = await self.client.get_messages(entity, limit=MESSAGES_LIMIT, max_id=before_id or 0)
        if before_id is None:
            self.read_outbox[dialog_id] = await self._load_read_outbox_async(entity)
        if before_id is None and mark_read:
            await self._mark_read_async(dialog_id)
        # Telegram returns newest first; the UI reads oldest first.
        return [self._describe_message(message, message.sender) for message in reversed(messages)]

    async def _load_read_outbox_async(self, entity):
        """Id of the newest message of ours that was read in this chat; None if Telegram does not say."""
        result = await self.client(functions.messages.GetPeerDialogsRequest(peers=[types.InputDialogPeer(entity)]))
        try:
            return result.dialogs[0].read_outbox_max_id
        except (AttributeError, IndexError):
            return None

    async def _press_button_async(self, dialog_id, message_id, index):
        message = await self.client.get_messages(self.entities[dialog_id], ids=message_id)
        button = [button for row in message.buttons or [] for button in row][index]
        url = getattr(button, "url", None)
        if url:
            # Left to the UI: a link from a bot is opened only once the user has seen where it goes.
            return {"url": url, "answer": None}
        try:
            result = await button.click()
        except BotResponseTimeoutError:
            # The press went through; the bot just never answered it.
            result = None
        is_answer = isinstance(result, types.messages.BotCallbackAnswer)
        return {"url": None, "answer": result.message if is_answer else None}

    async def _edit_message_async(self, dialog_id, message_id, text):
        try:
            await self.client.edit_message(self.entities[dialog_id], message_id, text)
        except MessageNotModifiedError:
            # Saving the same text again is not a failure.
            pass

    async def _delete_message_async(self, dialog_id, message_id, for_everyone):
        message_ids = message_id if isinstance(message_id, list) else [message_id]
        await self.client.delete_messages(self.entities[dialog_id], message_ids, revoke=for_everyone)

    async def _save_folder_async(self, folder, offered_ids):
        original = self.folder_filters.get(folder["id"])
        # Chats the user was not shown stay in or out as they were.
        kept = [
            peer for peer in getattr(original, "include_peers", [])
            if get_peer_id(peer) not in offered_ids
        ]
        chosen = [self.entities[dialog_id] for dialog_id in folder["include_ids"] if dialog_id in self.entities]
        pinned = list(getattr(original, "pinned_peers", []))
        pinned_ids = {get_peer_id(peer) for peer in pinned}
        await self.client(functions.messages.UpdateDialogFilterRequest(id=folder["id"], filter=types.DialogFilter(
            id=folder["id"], title=types.TextWithEntities(folder["title"], []),
            pinned_peers=pinned,
            # A pinned chat is in the folder already; Telegram refuses it listed twice.
            include_peers=[peer for peer in chosen + kept if get_peer_id(peer) not in pinned_ids],
            exclude_peers=list(getattr(original, "exclude_peers", [])),
            **{category: category in folder["categories"] for category in FOLDER_CATEGORIES},
            **{flag: bool(folder[flag]) for flag in FOLDER_EXCLUSIONS},
            emoticon=getattr(original, "emoticon", None), color=getattr(original, "color", None)
        )))

    async def _delete_folder_async(self, folder_id):
        await self.client(functions.messages.UpdateDialogFilterRequest(id=folder_id))
        self.folder_filters.pop(folder_id, None)

    async def _report_async(self, dialog_id, message_ids, option, comment):
        result = await self.client(functions.messages.ReportRequest(
            peer=self.entities[dialog_id], id=message_ids, option=option, message=comment
        ))
        if isinstance(result, types.ReportResultChooseOption):
            return {"title": result.title, "options": [(choice.text, choice.option) for choice in result.options]}
        if isinstance(result, types.ReportResultAddComment):
            return {"comment": result.option}
        return {"done": True}

    async def _load_messages_around_async(self, dialog_id, message_id):
        messages = await self.client.get_messages(
            self.entities[dialog_id], limit=MESSAGES_LIMIT, offset_id=message_id, add_offset=-(MESSAGES_LIMIT // 2)
        )
        return [
            self._describe_message(message, message.sender)
            for message in sorted(messages, key=lambda message: message.id)
        ]

    async def _load_messages_from_async(self, dialog_id, date):
        messages = await self.client.get_messages(
            self.entities[dialog_id], limit=MESSAGES_LIMIT, offset_date=date, reverse=True
        )
        return [self._describe_message(message, message.sender) for message in messages]

    async def _search_all_async(self, query):
        messages = await self.client.get_messages(None, limit=GLOBAL_SEARCH_LIMIT, search=query)
        return [
            {"chat": self._remember_chat(message.chat), "message": self._describe_message(message, message.sender)}
            # A hit in a chat Telegram sent no details of cannot be opened from here.
            for message in messages if getattr(message, "chat", None) is not None
        ]

    async def _send_file_async(self, dialog_id, path, voice_note, report, reply_to):
        await self.client.send_file(
            self.entities[dialog_id], path, voice_note=voice_note, progress_callback=report, reply_to=reply_to
        )

    async def _send_files_async(self, dialog_id, paths, caption, as_documents, reply_to, report):
        await self.client.send_file(
            # A list, even of one, would be sent as an album.
            self.entities[dialog_id], paths if len(paths) > 1 else paths[0],
            caption=caption or None, force_document=as_documents, reply_to=reply_to, progress_callback=report
        )

    async def _send_media_async(self, dialog_id, get_media, reply_to):
        await self.client.send_file(self.entities[dialog_id], get_media(), reply_to=reply_to)

    async def _load_sticker_sets_async(self):
        result = await self.client(functions.messages.GetAllStickersRequest(hash=0))
        self.sticker_sets = {
            sticker_set.id: types.InputStickerSetID(id=sticker_set.id, access_hash=sticker_set.access_hash)
            for sticker_set in result.sets
        }
        return [{"id": sticker_set.id, "title": sticker_set.title} for sticker_set in result.sets]

    async def _load_stickers_async(self, set_id):
        if set_id is None:
            result = await self.client(functions.messages.GetRecentStickersRequest(hash=0))
            self.stickers = list(result.stickers)
        else:
            result = await self.client(functions.messages.GetStickerSetRequest(
                stickerset=self.sticker_sets[set_id], hash=0
            ))
            self.stickers = list(result.documents)
        return [self._sticker_emoji(document) for document in self.stickers]

    def _sticker_emoji(self, document):
        """The emoji a sticker stands for: the only words Telegram has for the picture."""
        for attribute in getattr(document, "attributes", None) or []:
            if isinstance(attribute, types.DocumentAttributeSticker):
                return attribute.alt or EMPTY_STRING
        return EMPTY_STRING

    async def _send_contact_async(self, dialog_id, contact_id, reply_to):
        user = await self.client.get_entity(self.entities[contact_id])
        if not getattr(user, "phone", None):
            raise PhoneHiddenError()
        await self.client.send_file(self.entities[dialog_id], types.InputMediaContact(
            phone_number=user.phone, first_name=user.first_name or EMPTY_STRING,
            last_name=user.last_name or EMPTY_STRING, vcard=EMPTY_STRING
        ), reply_to=reply_to)

    async def _search_messages_async(self, dialog_id, query):
        messages = await self.client.get_messages(
            self.entities[dialog_id], limit=MESSAGES_LIMIT, search=query
        )
        return [self._describe_message(message, message.sender) for message in reversed(messages)]

    async def _export_messages_async(self, dialog_id, on_progress):
        entity = self.entities[dialog_id]
        found = []
        oldest = 0
        while len(found) < CHAT_EXPORT_LIMIT:
            page = await self.client.get_messages(entity, limit=CHAT_EXPORT_PAGE, max_id=oldest)
            if not page:
                break
            found.extend(self._describe_message(message, message.sender) for message in page)
            oldest = page[-1].id
            if on_progress is not None:
                on_progress(len(found))
            if len(page) < CHAT_EXPORT_PAGE:
                break
        # Telegram gives the newest first; a file is read from the start.
        return list(reversed(found))

    async def _load_chat_files_async(self, dialog_id):
        entity = self.entities[dialog_id]
        found = {}
        # Telegram finds each kind of file on its own; one message can turn up under two of them.
        for kind in CHAT_FILE_FILTERS:
            for message in await self.client.get_messages(entity, limit=CHAT_FILES_LIMIT, filter=kind):
                found.setdefault(message.id, message)
        described = [self._describe_message(found[message_id], found[message_id].sender) for message_id in sorted(found)]
        return [message for message in described if message["media"] in DOWNLOADABLE_MEDIA and message["file"]]

    async def _download_media_async(self, dialog_id, message_id, folder, report):
        message = await self.client.get_messages(self.entities[dialog_id], ids=message_id)
        os.makedirs(folder, exist_ok=True)
        path = await self.client.download_media(message, file=folder + os.sep, progress_callback=report)
        if not path:
            raise ValueError("message has no downloadable media")
        return path

    async def _fetch_media_async(self, dialog_id, message_id, report):
        message = await self.client.get_messages(self.entities[dialog_id], ids=message_id)
        data = await self.client.download_media(message, file=bytes, progress_callback=report)
        if not data:
            raise ValueError("message has no downloadable media")
        return data

    async def _mark_read_async(self, dialog_id):
        # Best effort: failing to mark as read must not fail the request around it.
        try:
            await self.client.send_read_acknowledge(self.entities[dialog_id])
        except Exception:
            pass

    def _describe_message(self, message, sender):
        return {
            "id": message.id,
            "sender": get_display_name(sender) if sender else EMPTY_STRING,
            # Set when a person wrote it, and so can be written to; None for a channel or a group writing as itself.
            "sender_id": sender.id if isinstance(sender, types.User) else None,
            "text": message.message or EMPTY_STRING,
            # Words for an attachment that has no text of its own: a sticker's emoji, a contact's name and number.
            "detail": self._describe_detail(message),
            # What an attached file is: {"name", "size", "duration"}; None for a message without one.
            "file": self._describe_file(message),
            "media": self._describe_media(message),
            "date": message.date,
            "outgoing": message.out,
            "pinned": bool(getattr(message, "pinned", False)),
            "reply_to": getattr(message, "reply_to_msg_id", None),
            # The topic or post this message sits under: the top of its chain of replies.
            "thread_id": getattr(getattr(message, "reply_to", None), "reply_to_top_id", None)
            or getattr(message, "reply_to_msg_id", None),
            "reactions": self._describe_reactions(message),
            "poll": self._describe_poll(message),
            "buttons": [button.text for row in getattr(message, "buttons", None) or [] for button in row],
            "links": self._describe_links(message),
            # How many comments a channel post has; None for anything that takes no comments.
            "comments": self._count_comments(message),
            # Changed by its author after sending. Telegram also stamps a post when its reactions change; that is not an edit.
            "edited": bool(getattr(message, "edit_date", None)) and not getattr(message, "edit_hide", False),
            # Whose message this was before it was passed on: a name, "" if hidden, None if not forwarded.
            "forwarded_from": self._describe_forward(message),
            "views": getattr(message, "views", None) if getattr(message, "post", False) else None,
            "forwards": getattr(message, "forwards", None) if getattr(message, "post", False) else None,
            "read": self._is_read(message),
        }

    def _describe_forward(self, message):
        forward = getattr(message, "forward", None)
        if forward is None:
            return None
        origin = getattr(forward, "sender", None) or getattr(forward, "chat", None)
        return getattr(forward, "from_name", None) or (get_display_name(origin) if origin else EMPTY_STRING)

    def _count_comments(self, message):
        replies = getattr(message, "replies", None)
        return replies.replies if replies is not None and getattr(replies, "comments", False) else None

    def _describe_file(self, message):
        attached = getattr(message, "file", None)
        if attached is None or getattr(message, "sticker", None):
            return None
        return {
            "name": getattr(attached, "name", None) or EMPTY_STRING,
            "size": getattr(attached, "size", None) or 0,
            # Seconds, for sound and video.
            "duration": getattr(attached, "duration", None) or 0,
        }

    def _describe_detail(self, message):
        contact = getattr(message, "contact", None)
        if contact:
            return " ".join(filter(None, [contact.first_name, contact.last_name, contact.phone_number]))
        geo = getattr(message, "geo", None)
        if geo:
            return "%s, %s" % (geo.lat, geo.long)
        if getattr(message, "sticker", None):
            return self._sticker_emoji(message.sticker)
        return EMPTY_STRING

    def _describe_links(self, message):
        """Every address a message points to: written out, hidden behind words, or an @mention."""
        get_entities_text = getattr(message, "get_entities_text", None)
        links = []
        for entity, text in get_entities_text() if get_entities_text else []:
            if isinstance(entity, types.MessageEntityTextUrl):
                links.append(entity.url)
            elif isinstance(entity, types.MessageEntityUrl):
                links.append(text)
            elif isinstance(entity, types.MessageEntityMention):
                links.append("https://t.me/" + text.lstrip("@"))
        geo = getattr(message, "geo", None)
        if geo:
            # A place has no address of its own; a map of it is the nearest thing to open.
            links.append(MAP_LINK_FORMAT.format(latitude=geo.lat, longitude=geo.long))
        return links

    def _is_read(self, message):
        """Whether a message of ours was read by the other side; None where that is not known
        or means nothing (someone else's message, a channel post)."""
        read_up_to = self.read_outbox.get(getattr(message, "chat_id", None))
        if read_up_to is None or not message.out or getattr(message, "post", False):
            return None
        return message.id <= read_up_to

    def _describe_media(self, message):
        """Locale key naming the non-text content of a message, or None for plain text."""
        # A link preview is media to Telegram, but the message is still just text.
        if getattr(message, "web_preview", None):
            return None
        # Specific kinds first: a sticker, voice note or video is also a document.
        for attribute, key in MEDIA_KINDS:
            if getattr(message, attribute, None):
                return key
        return None

    async def _on_new_message(self, event):
        if self.message_listener is None:
            return
        try:
            dialog_id = event.chat_id
            if dialog_id not in self.entities:
                self.entities[dialog_id] = await event.get_input_chat()
            chat = self._describe_chat(await event.get_chat())
            message = self._describe_message(event.message, await event.get_sender())
        except Exception:
            logger.exception("Telegram request failed")
            return
        self.message_listener(EVENT_NEW_MESSAGE, chat, message)

    async def _on_message_edited(self, event):
        if self.message_listener is None:
            return
        try:
            message = self._describe_message(event.message, await event.get_sender())
        except Exception:
            logger.exception("Telegram request failed")
            return
        self.message_listener(EVENT_MESSAGE_EDITED, event.chat_id, message)

    async def _on_messages_read(self, event):
        self.read_outbox[event.chat_id] = event.max_id
        if self.message_listener is not None:
            self.message_listener(EVENT_MESSAGES_READ, event.chat_id, event.max_id)

    async def _on_user_update(self, event):
        if self.message_listener is None:
            return
        if event.status is not None:
            self.message_listener(EVENT_USER_STATUS, event.user_id, self._describe_status(event.status))
        else:
            action = self._typing_action(event)
            if action is None:
                return
            name = None
            if not event.is_private:
                # In a group, which of its members it is; Telethon usually has them already.
                try:
                    name = get_display_name(await event.get_user())
                except Exception:
                    logger.info("Could not tell who is typing", exc_info=True)
            self.message_listener(EVENT_TYPING, event.chat_id, action, name)

    @staticmethod
    def _typing_action(event):
        """Which TYPING_ACTION_* a user update is; None for anything else (playing a game, choosing a sticker)."""
        if getattr(event, "cancel", False):
            return TYPING_ACTION_CANCEL
        if getattr(event, "typing", False):
            return TYPING_ACTION_TYPING
        if getattr(event, "recording", False):
            return TYPING_ACTION_VOICE if getattr(event, "audio", False) else TYPING_ACTION_VIDEO
        if getattr(event, "uploading", False):
            return TYPING_ACTION_UPLOAD
        return None

    async def _on_draft(self, update):
        if self.message_listener is not None:
            # An emptied draft arrives as a draft object with no text at all.
            text = getattr(update.draft, "message", None) or EMPTY_STRING
            self.message_listener(EVENT_DRAFT, get_peer_id(update.peer), text)

    async def _on_message_deleted(self, event):
        if self.message_listener is not None:
            self.message_listener(EVENT_MESSAGES_DELETED, event.chat_id, list(event.deleted_ids))

    async def _send_message_async(self, dialog_id, text, reply_to, schedule, silent):
        await self.client.send_message(
            # None, not False: unasked, the chat's own setting for this decides.
            self.entities[dialog_id], text, reply_to=reply_to, schedule=schedule, silent=silent or None
        )

    async def _load_thread_async(self, dialog_id, thread_id, view):
        peer, root = dialog_id, thread_id
        if view == MESSAGE_VIEW_COMMENTS:
            # The post has a twin in the discussion group, and the comments are the answers to that twin.
            discussion = await self.client(functions.messages.GetDiscussionMessageRequest(
                peer=self.entities[dialog_id], msg_id=thread_id
            ))
            twin = discussion.messages[0]
            peer, root = get_peer_id(twin.peer_id), twin.id
            for chat in discussion.chats:
                self.entities.setdefault(get_peer_id(chat), get_input_peer(chat))
        messages = await self.client.get_messages(self.entities[peer], limit=MESSAGES_LIMIT, reply_to=root)
        return {
            "peer": peer, "root": root,
            "messages": [self._describe_message(message, message.sender) for message in reversed(messages)],
        }

    async def _pin_topic_async(self, dialog_id, topic_id, pinned):
        await self.client(functions.messages.UpdatePinnedForumTopicRequest(
            peer=self.entities[dialog_id], topic_id=topic_id, pinned=pinned
        ))

    async def _post_story_async(self, path, caption, audience, report):
        rules = dict(zip(STORY_AUDIENCES, (
            types.InputPrivacyValueAllowAll, types.InputPrivacyValueAllowContacts,
            types.InputPrivacyValueAllowCloseFriends,
        )))
        photo = types.InputMediaUploadedPhoto(file=await self.client.upload_file(path, progress_callback=report))
        await self.client(functions.stories.SendStoryRequest(
            peer=types.InputPeerSelf(), media=photo, privacy_rules=[rules[audience]()],
            caption=caption or None, period=STORY_SECONDS
        ))

    async def _load_topics_async(self, dialog_id):
        result = await self.client(functions.messages.GetForumTopicsRequest(
            peer=self.entities[dialog_id], offset_date=None, offset_id=0, offset_topic=0, limit=TOPICS_LIMIT
        ))
        return [
            {
                "id": topic.id, "title": topic.title, "unread": getattr(topic, "unread_count", 0),
                "closed": bool(getattr(topic, "closed", False)),
                "pinned": bool(getattr(topic, "pinned", False)),
            }
            # A deleted topic is still listed, as a bare id with no title.
            for topic in result.topics if getattr(topic, "title", None)
        ]

    async def _load_audience_async(self, dialog_id, message_id):
        entity = self.entities[dialog_id]
        try:
            result = await self.client(functions.messages.GetMessageReactionsListRequest(
                peer=entity, id=message_id, limit=AUDIENCE_LIMIT
            ))
        except FloodWaitError:
            raise
        except RPCError:
            # Channels do not tell who reacted, only how many.
            result = None
        names = {
            get_peer_id(reactor): get_display_name(reactor)
            for reactor in list(getattr(result, "users", [])) + list(getattr(result, "chats", []))
        }
        reactions = [
            (names.get(get_peer_id(reaction.peer_id), EMPTY_STRING), reaction.reaction.emoticon)
            for reaction in getattr(result, "reactions", [])
            if isinstance(reaction.reaction, types.ReactionEmoji)
        ]
        try:
            read = await self.client(functions.messages.GetMessageReadParticipantsRequest(peer=entity, msg_id=message_id))
            readers = []
            for reader in read or []:
                try:
                    readers.append(get_display_name(await self.client.get_entity(reader.user_id)))
                except ValueError:
                    # Someone this session has never seen: counted by Telegram, but nameless here.
                    pass
        except FloodWaitError:
            raise
        except RPCError:
            # Only for this account's own recent messages in small groups.
            readers = None
        return {"readers": readers, "reactions": reactions}

    async def _load_message_view_async(self, dialog_id, view):
        entity = self.entities[dialog_id]
        if view == MESSAGE_VIEW_SCHEDULED:
            messages = await self.client.get_messages(entity, scheduled=True)
        else:
            messages = await self.client.get_messages(
                entity, limit=MESSAGES_LIMIT, filter=MESSAGE_VIEW_FILTERS[view]
            )
        if view == MESSAGE_VIEW_MENTIONS:
            # Seen now. Best effort: the list is what was asked for.
            try:
                await self.client(functions.messages.ReadMentionsRequest(peer=entity))
            except Exception:
                pass
        return [self._describe_message(message, message.sender) for message in reversed(messages)]

    async def _delete_scheduled_async(self, dialog_id, message_id):
        await self.client(functions.messages.DeleteScheduledMessagesRequest(
            peer=self.entities[dialog_id], id=[message_id]
        ))

    def _describe_poll(self, message):
        media = getattr(message, "poll", None)
        if not media:
            return None
        poll, results = media.poll, media.results
        votes = {result.option: result for result in getattr(results, "results", None) or []}
        return {
            # Newer Telegram layers wrap these texts in a formatted-text object.
            "question": getattr(poll.question, "text", poll.question),
            "options": [
                {
                    "text": getattr(answer.text, "text", answer.text),
                    # None while Telegram hides the results (before voting).
                    "voters": getattr(votes.get(answer.option), "voters", None),
                    "chosen": bool(getattr(votes.get(answer.option), "chosen", False)),
                }
                for answer in poll.answers
            ],
            "closed": bool(poll.closed),
            "multiple": bool(poll.multiple_choice),
        }

    async def _vote_async(self, dialog_id, message_id, option_indexes):
        entity = self.entities[dialog_id]
        message = await self.client.get_messages(entity, ids=message_id)
        answers = message.poll.poll.answers
        await self.client(functions.messages.SendVoteRequest(
            peer=entity, msg_id=message_id, options=[answers[index].option for index in option_indexes]
        ))
        message = await self.client.get_messages(entity, ids=message_id)
        return self._describe_message(message, message.sender)

    async def _send_poll_async(self, dialog_id, question, options, reply_to):
        def formatted(text):
            return types.TextWithEntities(text, [])
        poll = types.Poll(
            id=0, hash=0, question=formatted(question),
            answers=[types.PollAnswer(formatted(text), bytes([index])) for index, text in enumerate(options)]
        )
        await self.client.send_message(self.entities[dialog_id], file=types.InputMediaPoll(poll), reply_to=reply_to)

    async def _load_admin_log_async(self, dialog_id):
        events = []
        async for event in self.client.iter_admin_log(self.entities[dialog_id], limit=ADMIN_LOG_LIMIT):
            events.append({
                "user": get_display_name(event.user) if event.user else EMPTY_STRING,
                "date": event.date,
                # E.g. "ChannelAdminLogEventActionParticipantInvite" -> "ParticipantInvite".
                "action": type(event.action).__name__.replace(ADMIN_LOG_ACTION_PREFIX, EMPTY_STRING),
            })
        return events

    async def _leave_chat_async(self, dialog_id):
        try:
            await self.client.delete_dialog(self.entities[dialog_id])
        except UserNotParticipantError:
            # Never joined, or already gone: either way it is left.
            pass

    async def _react_async(self, dialog_id, message_id, emoji):
        entity = self.entities[dialog_id]
        await self.client(functions.messages.SendReactionRequest(
            peer=entity, msg_id=message_id,
            reaction=[types.ReactionEmoji(emoticon=emoji)] if emoji else []
        ))
        # Read it back so the list shows the totals Telegram now has.
        message = await self.client.get_messages(entity, ids=message_id)
        return self._describe_message(message, message.sender)

    def _describe_reactions(self, message):
        """[(emoji, count), ...] for the standard emoji reactions on a message."""
        reactions = getattr(message, "reactions", None)
        return [
            (result.reaction.emoticon, result.count)
            for result in getattr(reactions, "results", None) or []
            if isinstance(result.reaction, types.ReactionEmoji)
        ]

    async def _ensure_connected(self):
        async with self.connect_lock:
            if not self.client.is_connected():
                await self.client.connect()

    async def _watch_connection_async(self):
        """Keep asking Telegram for a sign of life, and reconnect when the line has dropped."""
        while True:
            state = CONNECTION_ONLINE if await self._is_reachable_async() else CONNECTION_OFFLINE
            if state != self.connection_state:
                self.connection_state = state
                logger.info("Connection to Telegram: %s", state)
                if self.connection_listener is not None:
                    self.connection_listener(state)
            await asyncio.sleep(CONNECTION_WATCH_SECONDS)

    async def _is_reachable_async(self):
        try:
            # Telethon gives up reconnecting after a few tries; this picks it up again.
            await self._ensure_connected()
            # An open socket proves nothing when the network died silently; an answer does.
            await asyncio.wait_for(
                self.client(functions.PingRequest(ping_id=int.from_bytes(os.urandom(8), "big", signed=True))),
                CONNECTION_PING_TIMEOUT_SECONDS
            )
            return True
        except Exception:
            return False

    async def _connect_async(self):
        try:
            await self._ensure_connected()
            if await self.client.is_user_authorized():
                self.ui_callback(STEP_DONE)
            else:
                self.ui_callback(STEP_PHONE)
        except Exception:
            logger.exception("Telegram request failed")
            self.ui_callback(STEP_PHONE, ERR_CONNECTION_KEY)

    async def _set_proxy_async(self, proxy):
        async with self.connect_lock:
            self.proxy = proxy
            entities = self.entities
            try:
                await self.client.disconnect()
            except Exception:
                logger.exception("Telegram request failed")
            # The way in is fixed when a client is made, so this takes a new one on the same session.
            self._create_client()
            # The chats on screen are still the same ones.
            self.entities = entities
        await self._connect_async()

    async def _disconnect_async(self):
        # Otherwise the watcher would connect again right behind this.
        if self.watch_task is not None:
            self.watch_task.cancel()
        if self.client is not None:
            await self.client.disconnect()

    async def _send_phone_async(self, phone):
        try:
            await self._ensure_connected()
            result = await self.client.send_code_request(phone)
            self.phone = phone
            self._remember_code_delivery(result)
            self.ui_callback(STEP_CODE)
        except PhoneNumberInvalidError:
            self.ui_callback(STEP_PHONE, ERR_PHONE_INVALID_KEY)
        except (ApiIdInvalidError, ApiIdPublishedFloodError):
            # Not a network problem and not the user's number: the app's own key is wrong.
            logger.error("Telegram rejected the API id and hash")
            self.ui_callback(STEP_PHONE, ERR_API_INVALID_KEY)
        except FloodWaitError:
            self.ui_callback(STEP_PHONE, ERR_FLOOD_KEY)
        except (ConnectionError, OSError):
            self.ui_callback(STEP_PHONE, ERR_CONNECTION_KEY)
        except Exception:
            logger.exception("Telegram request failed")
            self.ui_callback(STEP_PHONE, ERR_GENERAL_KEY)

    def _remember_code_delivery(self, sent_code):
        """Keep what Telegram said about the login code: how it was sent, and what it would try next."""
        self.phone_hash = sent_code.phone_code_hash
        self.code_delivery = CODE_DELIVERY_KEYS.get(type(sent_code.type).__name__, CODE_DELIVERY_OTHER_KEY)
        # None when Telegram offers no further way for this number.
        self.next_code_delivery = NEXT_CODE_DELIVERY_KEYS.get(type(sent_code.next_type).__name__)
        self.code_length = getattr(sent_code.type, "length", None) or None

    async def _resend_code_async(self):
        try:
            await self._ensure_connected()
            # Telegram picks the method itself: each request moves on to the next one it
            # allows for this number (typically app, then SMS, then a voice call).
            result = await self.client(functions.auth.ResendCodeRequest(self.phone, self.phone_hash))
            self._remember_code_delivery(result)
            self.ui_callback(STEP_CODE)
        except SendCodeUnavailableError:
            self.ui_callback(STEP_CODE, ERR_NO_OTHER_DELIVERY_KEY)
        except PhoneCodeExpiredError:
            self.ui_callback(STEP_PHONE, ERR_CODE_EXPIRED_KEY)
        except FloodWaitError:
            self.ui_callback(STEP_CODE, ERR_FLOOD_KEY)
        except (ConnectionError, OSError):
            self.ui_callback(STEP_CODE, ERR_CONNECTION_KEY)
        except Exception:
            logger.exception("Telegram request failed")
            self.ui_callback(STEP_CODE, ERR_GENERAL_KEY)

    async def _send_code_async(self, code):
        try:
            await self._ensure_connected()
            await self.client.sign_in(self.phone, code, phone_code_hash=self.phone_hash)
            self.ui_callback(STEP_DONE)
        except SessionPasswordNeededError:
            self.ui_callback(STEP_PASSWORD)
        except PhoneCodeInvalidError:
            self.ui_callback(STEP_CODE, ERR_CODE_INVALID_KEY)
        except PhoneCodeExpiredError:
            # The hash is dead too, so a new code has to be requested.
            self.ui_callback(STEP_PHONE, ERR_CODE_EXPIRED_KEY)
        except FloodWaitError:
            self.ui_callback(STEP_CODE, ERR_FLOOD_KEY)
        except (ConnectionError, OSError):
            self.ui_callback(STEP_CODE, ERR_CONNECTION_KEY)
        except Exception:
            logger.exception("Telegram request failed")
            self.ui_callback(STEP_CODE, ERR_GENERAL_KEY)

    async def _send_password_async(self, password):
        try:
            await self._ensure_connected()
            await self.client.sign_in(password=password)
            self.ui_callback(STEP_DONE)
        except PasswordHashInvalidError:
            self.ui_callback(STEP_PASSWORD, ERR_PASSWORD_INVALID_KEY)
        except FloodWaitError:
            self.ui_callback(STEP_PASSWORD, ERR_FLOOD_KEY)
        except (ConnectionError, OSError):
            self.ui_callback(STEP_PASSWORD, ERR_CONNECTION_KEY)
        except Exception:
            logger.exception("Telegram request failed")
            self.ui_callback(STEP_PASSWORD, ERR_GENERAL_KEY)
