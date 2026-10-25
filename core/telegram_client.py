import asyncio
import logging
import os
import platform
import threading
from telethon import TelegramClient, events
from telethon.errors import (
    PhoneCodeInvalidError, PhoneCodeExpiredError, PhoneNumberInvalidError, SessionPasswordNeededError,
    PasswordHashInvalidError, FloodWaitError, ChatAdminRequiredError, ChatWriteForbiddenError,
    UserAdminInvalidError, RightForbiddenError, UserCreatorError, MessageDeleteForbiddenError,
    SendCodeUnavailableError, VoiceMessagesForbiddenError, ApiIdInvalidError, ApiIdPublishedFloodError,
    UsernameOccupiedError, UsernameInvalidError, PhotoCropSizeSmallError, ImageProcessFailedError,
    PhotoExtInvalidError, PhoneNumberOccupiedError, CodeInvalidError, UserPrivacyRestrictedError,
    UserNotMutualContactError, UserChannelsTooMuchError, MegagroupPrehistoryHiddenError, LinkNotModifiedError,
    MegagroupRequiredError, BroadcastRequiredError, PollQuestionInvalidError, PollOptionInvalidError,
    PollAnswersInvalidError, PollOptionDuplicateError, QuizCorrectAnswersEmptyError, QuizCorrectAnswersTooMuchError,
    QuizCorrectAnswerInvalidError, QuizMultipleInvalidError, BroadcastPublicVotersForbiddenError, PollVoteRequiredError,
    MessageAuthorRequiredError,
)
from telethon.tl import functions, types
from telethon.utils import get_display_name, get_peer_id
from core.config import load_credentials
from core.proxy import client_arguments
from core.constants import (
    APP_VERSION, CLIENT_DEVICE_MODEL, CLIENT_SYSTEM_FORMAT, SESSION_NAME, EMPTY_STRING, STEP_PHONE, STEP_CODE,
    STEP_PASSWORD, STEP_DONE, ERR_CODE_INVALID_KEY, ERR_CODE_EXPIRED_KEY, ERR_PHONE_INVALID_KEY,
    ERR_PASSWORD_INVALID_KEY, ERR_FLOOD_KEY, ERR_CONNECTION_KEY, ERR_GENERAL_KEY, ERR_NO_PERMISSION_KEY,
    ERR_CHAT_NOT_FOUND_KEY, CODE_DELIVERY_KEYS, NEXT_CODE_DELIVERY_KEYS, CODE_DELIVERY_OTHER_KEY,
    ERR_NO_OTHER_DELIVERY_KEY, ERR_VOICE_FORBIDDEN_KEY, ERR_API_INVALID_KEY, EVENT_NEW_MESSAGE,
    EVENT_MESSAGE_EDITED, EVENT_MESSAGES_DELETED, CONNECTION_ONLINE, CONNECTION_OFFLINE,
    CONNECTION_WATCH_SECONDS, CONNECTION_PING_TIMEOUT_SECONDS, EVENT_MESSAGES_READ, EVENT_USER_STATUS,
    EVENT_TYPING, TYPING_ACTION_CANCEL, TYPING_ACTION_TYPING, TYPING_ACTION_VOICE, TYPING_ACTION_VIDEO,
    TYPING_ACTION_UPLOAD, ERR_NO_PHONE_KEY, ERR_USERNAME_TAKEN_KEY, ERR_USERNAME_INVALID_KEY,
    ERR_PHOTO_INVALID_KEY, ERR_PREHISTORY_HIDDEN_KEY, ERR_DISCUSSION_LINK_KEY, ERR_NO_INVITE_LINK_KEY,
    ERR_EMAIL_UNCONFIRMED_KEY, ERR_PHONE_TAKEN_KEY, EVENT_DRAFT, DEFAULT_LANG, ERR_CANNOT_ADD_KEY,
    ERR_STATS_UNAVAILABLE_KEY, ERR_POLL_QUESTION_KEY, ERR_POLL_ANSWERS_KEY, ERR_POLL_SETTINGS_KEY, ERR_POLL_VOTE_REQUIRED_KEY,
)
from core.tg_chats import ChatsMixin
from core.tg_messages import MessagesMixin
from core.tg_media import MediaMixin
from core.tg_admin import AdminMixin
from core.tg_account import AccountMixin
from core.tg_bots import BotsMixin
from core.tg_shared import (
    ChatNotFoundError, PhoneHiddenError, EmailNotConfirmedError, StatsUnavailableError, NoInviteLinkError,
)

STOP_TIMEOUT_SECONDS = 5
logger = logging.getLogger(__name__)


class TelegramManager(ChatsMixin, MessagesMixin, MediaMixin, AdminMixin, AccountMixin, BotsMixin, threading.Thread):
    """Runs Telethon on its own event loop.

    ui_callback(step, error_key=None) is called from this thread: `step` is the
    login step the UI should show next, `error_key` is set when the last
    request failed.

    The connection, signing in and the updates Telegram pushes are here; the rest is in a mixin per
    topic (core/tg_*.py).
    """

    def __init__(self, ui_callback, session_name=SESSION_NAME):
        super().__init__(daemon=True)
        self.ui_callback = ui_callback
        # The account's own session file: several accounts each have one.
        self.session_name = session_name
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
        # The admins load_admins listed, apart from the members, whose list is loaded anew more often.
        self.admin_entities = {}
        self.emoji_sets = {}
        # What the last inline query found, to send one of them.
        self.inline_results = []
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
        # Whether this client has been connected before, and so may have left work running.
        self.client_was_connected = False
        self.client = TelegramClient(
            self.session_name, self.api_id, self.api_hash,
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
        # Done with for good once its thread has ended; still running, it is left for the thread to finish.
        if not self.is_alive() and not self.loop.is_running():
            self.loop.close()

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
        except PollVoteRequiredError:
            on_result(None, ERR_POLL_VOTE_REQUIRED_KEY)
        except PollQuestionInvalidError:
            on_result(None, ERR_POLL_QUESTION_KEY)
        except (PollOptionInvalidError, PollAnswersInvalidError, PollOptionDuplicateError):
            on_result(None, ERR_POLL_ANSWERS_KEY)
        except (QuizCorrectAnswersEmptyError, QuizCorrectAnswersTooMuchError, QuizCorrectAnswerInvalidError,
                QuizMultipleInvalidError, BroadcastPublicVotersForbiddenError):
            on_result(None, ERR_POLL_SETTINGS_KEY)
        except VoiceMessagesForbiddenError:
            on_result(None, ERR_VOICE_FORBIDDEN_KEY)
        except (
            ChatAdminRequiredError, ChatWriteForbiddenError, UserAdminInvalidError, MessageAuthorRequiredError,
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

    async def _ensure_connected(self):
        async with self.connect_lock:
            if not self.client.is_connected():
                if self.client_was_connected:
                    # When Telethon gives up reconnecting it leaves its loop of updates running; connecting
                    # over it starts a second loop on the same state, and the two break each other
                    # ("Should not be applying the difference..."). Disconnecting stops the old one first.
                    await self.client.disconnect()
                await self.client.connect()
                self.client_was_connected = True

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
