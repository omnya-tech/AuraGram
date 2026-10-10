import asyncio
import datetime
import logging
import os
import threading
from telethon import TelegramClient, events
from telethon.errors import (
    PhoneCodeInvalidError, PhoneCodeExpiredError, PhoneNumberInvalidError,
    SessionPasswordNeededError, PasswordHashInvalidError, FloodWaitError,
    MessageNotModifiedError, ChatAdminRequiredError, ChatWriteForbiddenError,
    ChatNotModifiedError, ChatAboutNotModifiedError, UserAdminInvalidError,
    RightForbiddenError, UserCreatorError, MessageDeleteForbiddenError, RPCError,
    SendCodeUnavailableError, VoiceMessagesForbiddenError, ApiIdInvalidError,
    ApiIdPublishedFloodError
)
from telethon.tl import functions, types
from telethon.utils import get_display_name, get_input_peer, get_peer_id
from core.config import load_credentials
from core.constants import (
    SESSION_NAME, EMPTY_STRING, DIALOGS_LIMIT, MESSAGES_LIMIT,
    STEP_PHONE, STEP_CODE, STEP_PASSWORD, STEP_DONE,
    ERR_CODE_INVALID_KEY, ERR_CODE_EXPIRED_KEY, ERR_PHONE_INVALID_KEY,
    ERR_PASSWORD_INVALID_KEY, ERR_FLOOD_KEY, ERR_CONNECTION_KEY, ERR_GENERAL_KEY,
    ERR_LOGOUT_KEY, MEDIA_KINDS, DOWNLOADS_DIR, MUTE_FOREVER, ERR_NO_PERMISSION_KEY,
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
    EVENT_NEW_MESSAGE, EVENT_MESSAGE_EDITED, EVENT_MESSAGES_DELETED
)

STOP_TIMEOUT_SECONDS = 5
logger = logging.getLogger(__name__)

class ChatNotFoundError(Exception):
    """No user or chat matches what was typed."""

# Telegram's server-side filter for each message view that has one.
MESSAGE_VIEW_FILTERS = {
    MESSAGE_VIEW_PINNED: types.InputMessagesFilterPinned,
    MESSAGE_VIEW_PHOTOS: types.InputMessagesFilterPhotoVideo,
    MESSAGE_VIEW_FILES: types.InputMessagesFilterDocument,
    MESSAGE_VIEW_VOICE: types.InputMessagesFilterVoice,
    MESSAGE_VIEW_MUSIC: types.InputMessagesFilterMusic,
    MESSAGE_VIEW_LINKS: types.InputMessagesFilterUrl,
}
ADMIN_LOG_ACTION_PREFIX = "ChannelAdminLogEventAction"

# Every member permission Telethon's edit_permissions sets. The ones the app
# does not offer are still passed back unchanged when saving.
ALL_MEMBER_PERMISSIONS = MEMBER_PERMISSIONS + (
    "view_messages", "send_stickers", "send_gifs", "send_games", "send_inline", "embed_link_previews",
)
# Where Telegram's flag is named differently from Telethon's argument.
BANNED_RIGHT_NAMES = {"embed_link_previews": "embed_links"}

# Privacy settings offered in the app, by the name the UI uses for each.
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
        self.loop = asyncio.new_event_loop()
        self.client = None
        self.phone = None
        self.phone_hash = None
        # Locale keys describing the login code: how it was sent, and the next way on offer.
        self.code_delivery = CODE_DELIVERY_OTHER_KEY
        self.next_code_delivery = None
        self.entities = {}
        # Members of the chat whose member list was loaded last.
        self.member_entities = {}
        self.message_listener = None

    def run(self):
        asyncio.set_event_loop(self.loop)
        self._create_client()
        self.loop.create_task(self._connect_async())
        self.loop.run_forever()

    def _create_client(self):
        self.client = TelegramClient(SESSION_NAME, self.api_id, self.api_hash)
        self.client.add_event_handler(self._on_new_message, events.NewMessage())
        self.client.add_event_handler(self._on_message_edited, events.MessageEdited())
        self.client.add_event_handler(self._on_message_deleted, events.MessageDeleted())
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

    def send_phone(self, phone):
        asyncio.run_coroutine_threadsafe(self._send_phone_async(phone), self.loop)

    def send_code(self, code):
        asyncio.run_coroutine_threadsafe(self._send_code_async(code), self.loop)

    def resend_code(self):
        """Ask Telegram to deliver the login code another way, e.g. by voice call."""
        asyncio.run_coroutine_threadsafe(self._resend_code_async(), self.loop)

    def send_password(self, password):
        asyncio.run_coroutine_threadsafe(self._send_password_async(password), self.loop)

    def load_dialogs(self, on_result, limit=DIALOGS_LIMIT):
        self._request(on_result, self._load_dialogs_async, limit)

    def load_messages(self, dialog_id, on_result, before_id=None, mark_read=True):
        """Loads the latest page of a chat, or the page before message `before_id`."""
        self._request(on_result, self._load_messages_async, dialog_id, before_id, mark_read)

    def load_profile(self, on_result):
        """The result is the account's own first_name, last_name and about text."""
        self._request(on_result, self._load_profile_async)

    def save_profile(self, profile, on_result):
        self._request(on_result, self._save_profile_async, profile)

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

    def send_poll(self, dialog_id, question, options, on_result):
        self._request(on_result, self._send_poll_async, dialog_id, question, options)

    def load_admin_log(self, dialog_id, on_result):
        """The result is the recent admin actions in a channel or large group, newest first."""
        self._request(on_result, self._load_admin_log_async, dialog_id)

    def leave_chat(self, dialog_id, on_result):
        """Leaves a group or channel; for a private chat, deletes it from this account's list."""
        self._request(on_result, self._leave_chat_async, dialog_id)

    def react(self, dialog_id, message_id, emoji, on_result):
        """Sets this account's reaction (None removes it); the result is the refreshed message."""
        self._request(on_result, self._react_async, dialog_id, message_id, emoji)

    def manage_member(self, dialog_id, user_id, action, on_result, rights=None):
        """Applies one of the MEMBER_ACTION_* constants to a member loaded by load_members.

        `rights` is the set of admin right names to grant with MEMBER_ACTION_PROMOTE.
        """
        self._request(on_result, self._manage_member_async, dialog_id, user_id, action, rights)

    def load_folders(self, on_result):
        """The result is the account's chat folders with the rules for what belongs in each."""
        self._request(on_result, self._load_folders_async)

    def find_chat(self, query, on_result):
        """Looks up a username, phone number or link; the result is a chat like those of load_dialogs."""
        self._request(on_result, self._find_chat_async, query)

    def load_contacts(self, on_result):
        self._request(on_result, self._load_contacts_async)

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

    def create_invite_link(self, dialog_id, title, needs_approval, on_result):
        """`needs_approval` makes joiners wait in the join requests list."""
        self._request(on_result, self._create_invite_link_async, dialog_id, title, needs_approval)

    def revoke_invite_link(self, dialog_id, link, on_result):
        """Stops a link from working; people who already joined with it stay."""
        self._request(on_result, self._revoke_invite_link_async, dialog_id, link)

    def set_pinned(self, dialog_id, message_id, pinned, on_result):
        self._request(on_result, self._set_pinned_async, dialog_id, message_id, pinned)

    def download_media(self, dialog_id, message_id, on_result, folder=None):
        """Saves the message's media to `folder` (the downloads folder by default); the result is the file path."""
        self._request(on_result, self._download_media_async, dialog_id, message_id, folder or DOWNLOADS_DIR)

    def send_message(self, dialog_id, text, on_result, reply_to=None, schedule=None):
        """`schedule` is a datetime to deliver the message at, instead of now."""
        self._request(on_result, self._send_message_async, dialog_id, text, reply_to, schedule)

    def log_out(self):
        """Ends the session on Telegram, then reports the next login step through ui_callback."""
        asyncio.run_coroutine_threadsafe(self._log_out_async(), self.loop)

    def edit_message(self, dialog_id, message_id, text, on_result):
        self._request(on_result, self._edit_message_async, dialog_id, message_id, text)

    def delete_message(self, dialog_id, message_id, on_result):
        """Deletes a message, or a list of message ids, for everyone in the chat."""
        self._request(on_result, self._delete_message_async, dialog_id, message_id)

    def send_file(self, dialog_id, path, on_result, voice_note=False):
        self._request(on_result, self._send_file_async, dialog_id, path, voice_note)

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
        """
        self.message_listener = listener

    def _request(self, on_result, coroutine_function, *args):
        """Run a data request; on_result(result, error_key) is called from this thread."""
        asyncio.run_coroutine_threadsafe(
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

    async def _load_dialogs_async(self, limit):
        dialogs = await self.client.get_dialogs(limit=limit)
        # update(), not replace: chats learned from live messages may not be in this page.
        self.entities.update({dialog.id: dialog.input_entity for dialog in dialogs})
        return [
            self._describe_chat(
                dialog.entity, unread=dialog.unread_count, pinned=dialog.pinned,
                muted=self._is_muted(dialog), archived=bool(dialog.archived),
                marked_unread=bool(getattr(dialog.dialog, "unread_mark", False)),
                last_message=self._describe_last_message(getattr(dialog, "message", None))
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
                       marked_unread=False, last_message=None):
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
        }

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

    async def _load_contacts_async(self):
        result = await self.client(functions.contacts.GetContactsRequest(hash=0))
        chats = []
        for user in result.users:
            chat = self._describe_chat(user)
            self.entities[chat["id"]] = get_input_peer(user)
            chats.append(chat)
        return sorted(chats, key=lambda chat: chat["title"].casefold())

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
            }
            # Skip link kinds without an address of their own.
            for invite in result.invites if getattr(invite, "link", None)
        ]

    async def _create_invite_link_async(self, dialog_id, title, needs_approval):
        await self.client(functions.messages.ExportChatInviteRequest(
            peer=self.entities[dialog_id], title=title or None, request_needed=needs_approval
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
        if not mute_until:
            return False
        return mute_until > datetime.datetime.now(datetime.timezone.utc)

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
        }

    async def _save_profile_async(self, profile):
        await self.client(functions.account.UpdateProfileRequest(
            first_name=profile["first_name"], last_name=profile["last_name"], about=profile["about"]
        ))

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
        }
        if isinstance(entity, types.User):
            full = await self.client(functions.users.GetFullUserRequest(entity))
            info["kind"] = CHAT_KIND_USER
            info["about"] = full.full_user.about or EMPTY_STRING
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
        return [
            {
                "id": user.id,
                "name": get_display_name(user) or EMPTY_STRING,
                "role": fixed_role or self._member_role(getattr(user, "participant", None)),
                "rights": self._member_rights(getattr(user, "participant", None)),
                "is_self": bool(user.is_self),
            }
            for user in participants
        ]

    def _member_rights(self, participant):
        rights = getattr(participant, "admin_rights", None)
        return {name for name in ADMIN_RIGHTS if getattr(rights, name, False)}

    async def _manage_member_async(self, dialog_id, user_id, action, rights):
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
                await self.client.edit_admin(
                    entity, user, **{name: name in rights for name in ADMIN_RIGHTS}
                )
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
        if before_id is None and mark_read:
            await self._mark_read_async(dialog_id)
        # Telegram returns newest first; the UI reads oldest first.
        return [self._describe_message(message, message.sender) for message in reversed(messages)]

    async def _edit_message_async(self, dialog_id, message_id, text):
        try:
            await self.client.edit_message(self.entities[dialog_id], message_id, text)
        except MessageNotModifiedError:
            # Saving the same text again is not a failure.
            pass

    async def _delete_message_async(self, dialog_id, message_id):
        message_ids = message_id if isinstance(message_id, list) else [message_id]
        await self.client.delete_messages(self.entities[dialog_id], message_ids)

    async def _send_file_async(self, dialog_id, path, voice_note):
        await self.client.send_file(self.entities[dialog_id], path, voice_note=voice_note)

    async def _search_messages_async(self, dialog_id, query):
        messages = await self.client.get_messages(
            self.entities[dialog_id], limit=MESSAGES_LIMIT, search=query
        )
        return [self._describe_message(message, message.sender) for message in reversed(messages)]

    async def _download_media_async(self, dialog_id, message_id, folder):
        message = await self.client.get_messages(self.entities[dialog_id], ids=message_id)
        os.makedirs(folder, exist_ok=True)
        path = await self.client.download_media(message, file=folder + os.sep)
        if not path:
            raise ValueError("message has no downloadable media")
        return path

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
            "text": message.message or EMPTY_STRING,
            "media": self._describe_media(message),
            "date": message.date,
            "outgoing": message.out,
            "pinned": bool(getattr(message, "pinned", False)),
            "reply_to": getattr(message, "reply_to_msg_id", None),
            "reactions": self._describe_reactions(message),
            "poll": self._describe_poll(message),
        }

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

    async def _on_message_deleted(self, event):
        if self.message_listener is not None:
            self.message_listener(EVENT_MESSAGES_DELETED, event.chat_id, list(event.deleted_ids))

    async def _send_message_async(self, dialog_id, text, reply_to, schedule):
        await self.client.send_message(
            self.entities[dialog_id], text, reply_to=reply_to, schedule=schedule
        )

    async def _load_message_view_async(self, dialog_id, view):
        entity = self.entities[dialog_id]
        if view == MESSAGE_VIEW_SCHEDULED:
            messages = await self.client.get_messages(entity, scheduled=True)
        else:
            messages = await self.client.get_messages(
                entity, limit=MESSAGES_LIMIT, filter=MESSAGE_VIEW_FILTERS[view]
            )
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

    async def _send_poll_async(self, dialog_id, question, options):
        def formatted(text):
            return types.TextWithEntities(text, [])
        poll = types.Poll(
            id=0, hash=0, question=formatted(question),
            answers=[types.PollAnswer(formatted(text), bytes([index])) for index, text in enumerate(options)]
        )
        await self.client.send_message(self.entities[dialog_id], file=types.InputMediaPoll(poll))

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
        await self.client.delete_dialog(self.entities[dialog_id])

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
        if not self.client.is_connected():
            await self.client.connect()

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

    async def _disconnect_async(self):
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
