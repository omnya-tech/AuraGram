import asyncio
import datetime
import os
import threading
from telethon import TelegramClient, events
from telethon.errors import (
    PhoneCodeInvalidError, PhoneCodeExpiredError, PhoneNumberInvalidError,
    SessionPasswordNeededError, PasswordHashInvalidError, FloodWaitError,
    MessageNotModifiedError, ChatAdminRequiredError, ChatWriteForbiddenError,
    ChatNotModifiedError, ChatAboutNotModifiedError
)
from telethon.tl import functions, types
from telethon.utils import get_display_name
from core.constants import (
    API_ID, API_HASH, SESSION_NAME, EMPTY_STRING, DIALOGS_LIMIT, MESSAGES_LIMIT,
    STEP_PHONE, STEP_CODE, STEP_PASSWORD, STEP_DONE,
    ERR_CODE_INVALID_KEY, ERR_CODE_EXPIRED_KEY, ERR_PHONE_INVALID_KEY,
    ERR_PASSWORD_INVALID_KEY, ERR_FLOOD_KEY, ERR_CONNECTION_KEY, ERR_GENERAL_KEY,
    ERR_LOGOUT_KEY, MEDIA_KINDS, DOWNLOADS_DIR, MUTE_FOREVER, ERR_NO_PERMISSION_KEY,
    CHAT_KIND_USER, CHAT_KIND_GROUP, CHAT_KIND_SUPERGROUP, CHAT_KIND_CHANNEL,
    MEMBER_ROLE_OWNER, MEMBER_ROLE_ADMIN, MEMBERS_LIMIT,
    EVENT_NEW_MESSAGE, EVENT_MESSAGE_EDITED, EVENT_MESSAGES_DELETED
)

STOP_TIMEOUT_SECONDS = 5

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

    def load_members(self, dialog_id, search, on_result):
        """The result is a list of members, each with id, name and role."""
        self._request(on_result, self._load_members_async, dialog_id, search)

    def download_media(self, dialog_id, message_id, on_result):
        """Saves the message's media to the downloads folder; the result is the file path."""
        self._request(on_result, self._download_media_async, dialog_id, message_id)

    def send_message(self, dialog_id, text, on_result, reply_to=None):
        self._request(on_result, self._send_message_async, dialog_id, text, reply_to)

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

        EVENT_NEW_MESSAGE, dialog_id, dialog_title, message
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
        except (ChatAdminRequiredError, ChatWriteForbiddenError):
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
            {
                "id": dialog.id, "title": dialog.name,
                "unread": dialog.unread_count, "pinned": dialog.pinned,
                "muted": self._is_muted(dialog),
                # Channels and supergroups number their messages separately from everything else.
                "is_channel": dialog.is_channel,
            }
            for dialog in dialogs
        ]

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
            "about": EMPTY_STRING, "members_count": None, "can_edit": False,
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
        info["can_edit"] = bool(getattr(entity, "creator", False) or (rights and rights.change_info))
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

    async def _load_members_async(self, dialog_id, search):
        participants = await self.client.get_participants(
            self.entities[dialog_id], limit=MEMBERS_LIMIT, search=search
        )
        return [
            {
                "id": user.id,
                "name": get_display_name(user) or EMPTY_STRING,
                "role": self._member_role(getattr(user, "participant", None)),
            }
            for user in participants
        ]

    def _member_role(self, participant):
        if isinstance(participant, (types.ChannelParticipantCreator, types.ChatParticipantCreator)):
            return MEMBER_ROLE_OWNER
        if isinstance(participant, (types.ChannelParticipantAdmin, types.ChatParticipantAdmin)):
            return MEMBER_ROLE_ADMIN
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
            "reply_to": getattr(message, "reply_to_msg_id", None),
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
            title = get_display_name(await event.get_chat())
            message = self._describe_message(event.message, await event.get_sender())
        except Exception:
            return
        self.message_listener(EVENT_NEW_MESSAGE, dialog_id, title, message)

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

    async def _send_message_async(self, dialog_id, text, reply_to):
        await self.client.send_message(self.entities[dialog_id], text, reply_to=reply_to)

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
