import asyncio
import datetime
import os
import threading
from telethon import TelegramClient, events
from telethon.errors import (
    PhoneCodeInvalidError, PhoneCodeExpiredError, PhoneNumberInvalidError,
    SessionPasswordNeededError, PasswordHashInvalidError, FloodWaitError,
    MessageNotModifiedError, ChatAdminRequiredError, ChatWriteForbiddenError,
    ChatNotModifiedError, ChatAboutNotModifiedError, UserAdminInvalidError,
    RightForbiddenError, UserCreatorError, MessageDeleteForbiddenError, RPCError
)
from telethon.tl import functions, types
from telethon.utils import get_display_name, get_input_peer, get_peer_id
from core.constants import (
    API_ID, API_HASH, SESSION_NAME, EMPTY_STRING, DIALOGS_LIMIT, MESSAGES_LIMIT,
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
    EVENT_NEW_MESSAGE, EVENT_MESSAGE_EDITED, EVENT_MESSAGES_DELETED
)

STOP_TIMEOUT_SECONDS = 5

class ChatNotFoundError(Exception):
    """No user or chat matches what was typed."""

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
        self.loop = asyncio.new_event_loop()
        self.client = None
        self.phone = None
        self.phone_hash = None
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
        self.client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
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

    def set_muted(self, dialog_id, muted, on_result):
        self._request(on_result, self._set_muted_async, dialog_id, muted)

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

    def forward_message(self, from_dialog_id, message_id, to_dialog_id, on_result):
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

    def load_invite_link(self, dialog_id, on_result):
        self._request(on_result, self._load_invite_link_async, dialog_id)

    def set_pinned(self, dialog_id, message_id, pinned, on_result):
        self._request(on_result, self._set_pinned_async, dialog_id, message_id, pinned)

    def download_media(self, dialog_id, message_id, on_result):
        """Saves the message's media to the downloads folder; the result is the file path."""
        self._request(on_result, self._download_media_async, dialog_id, message_id)

    def send_message(self, dialog_id, text, on_result, reply_to=None, schedule=None):
        """`schedule` is a datetime to deliver the message at, instead of now."""
        self._request(on_result, self._send_message_async, dialog_id, text, reply_to, schedule)

    def log_out(self):
        """Ends the session on Telegram, then reports the next login step through ui_callback."""
        asyncio.run_coroutine_threadsafe(self._log_out_async(), self.loop)

    def edit_message(self, dialog_id, message_id, text, on_result):
        self._request(on_result, self._edit_message_async, dialog_id, message_id, text)

    def delete_message(self, dialog_id, message_id, on_result):
        """Deletes the message for everyone in the chat."""
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
        except (
            ChatAdminRequiredError, ChatWriteForbiddenError, UserAdminInvalidError,
            RightForbiddenError, UserCreatorError, MessageDeleteForbiddenError
        ):
            on_result(None, ERR_NO_PERMISSION_KEY)
        except (ConnectionError, OSError):
            on_result(None, ERR_CONNECTION_KEY)
        except Exception:
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
                muted=self._is_muted(dialog), archived=bool(dialog.archived)
            )
            for dialog in dialogs
        ]

    def _describe_chat(self, entity, unread=0, pinned=False, muted=False, archived=False):
        is_user = isinstance(entity, types.User)
        return {
            "id": get_peer_id(entity), "title": get_display_name(entity),
            "unread": unread, "pinned": pinned, "muted": muted, "archived": archived,
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

    async def _load_invite_link_async(self, dialog_id):
        """The chat's main invite link, created first if it has none yet."""
        entity = self.entities[dialog_id]
        if isinstance(entity, types.InputPeerChannel):
            full = await self.client(functions.channels.GetFullChannelRequest(entity))
        else:
            full = await self.client(functions.messages.GetFullChatRequest(entity.chat_id))
        invite = full.full_chat.exported_invite
        if invite is None or not getattr(invite, "link", None):
            invite = await self.client(functions.messages.ExportChatInviteRequest(entity))
        return invite.link

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

    async def _set_muted_async(self, dialog_id, muted):
        await self.client(functions.account.UpdateNotifySettingsRequest(
            peer=types.InputNotifyPeer(self.entities[dialog_id]),
            settings=types.InputPeerNotifySettings(mute_until=MUTE_FOREVER if muted else 0)
        ))

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
        await self.client.delete_messages(self.entities[dialog_id], [message_id])

    async def _send_file_async(self, dialog_id, path, voice_note):
        await self.client.send_file(self.entities[dialog_id], path, voice_note=voice_note)

    async def _search_messages_async(self, dialog_id, query):
        messages = await self.client.get_messages(
            self.entities[dialog_id], limit=MESSAGES_LIMIT, search=query
        )
        return [self._describe_message(message, message.sender) for message in reversed(messages)]

    async def _download_media_async(self, dialog_id, message_id):
        message = await self.client.get_messages(self.entities[dialog_id], ids=message_id)
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        path = await self.client.download_media(message, file=DOWNLOADS_DIR + os.sep)
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
            return
        self.message_listener(EVENT_NEW_MESSAGE, chat, message)

    async def _on_message_edited(self, event):
        if self.message_listener is None:
            return
        try:
            message = self._describe_message(event.message, await event.get_sender())
        except Exception:
            return
        self.message_listener(EVENT_MESSAGE_EDITED, event.chat_id, message)

    async def _on_message_deleted(self, event):
        if self.message_listener is not None:
            self.message_listener(EVENT_MESSAGES_DELETED, event.chat_id, list(event.deleted_ids))

    async def _send_message_async(self, dialog_id, text, reply_to, schedule):
        await self.client.send_message(
            self.entities[dialog_id], text, reply_to=reply_to, schedule=schedule
        )

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
            self.ui_callback(STEP_PHONE, ERR_CONNECTION_KEY)

    async def _disconnect_async(self):
        if self.client is not None:
            await self.client.disconnect()

    async def _send_phone_async(self, phone):
        try:
            await self._ensure_connected()
            result = await self.client.send_code_request(phone)
            self.phone = phone
            self.phone_hash = result.phone_code_hash
            self.ui_callback(STEP_CODE)
        except PhoneNumberInvalidError:
            self.ui_callback(STEP_PHONE, ERR_PHONE_INVALID_KEY)
        except FloodWaitError:
            self.ui_callback(STEP_PHONE, ERR_FLOOD_KEY)
        except (ConnectionError, OSError):
            self.ui_callback(STEP_PHONE, ERR_CONNECTION_KEY)
        except Exception:
            self.ui_callback(STEP_PHONE, ERR_GENERAL_KEY)

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
            self.ui_callback(STEP_PASSWORD, ERR_GENERAL_KEY)
