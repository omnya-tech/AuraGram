import asyncio
import threading
from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeInvalidError, PhoneCodeExpiredError, PhoneNumberInvalidError,
    SessionPasswordNeededError, PasswordHashInvalidError, FloodWaitError
)
from telethon.utils import get_display_name
from core.constants import (
    API_ID, API_HASH, SESSION_NAME, EMPTY_STRING, DIALOGS_LIMIT, MESSAGES_LIMIT,
    STEP_PHONE, STEP_CODE, STEP_PASSWORD, STEP_DONE,
    ERR_CODE_INVALID_KEY, ERR_CODE_EXPIRED_KEY, ERR_PHONE_INVALID_KEY,
    ERR_PASSWORD_INVALID_KEY, ERR_FLOOD_KEY, ERR_CONNECTION_KEY, ERR_GENERAL_KEY
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

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        self.loop.create_task(self._connect_async())
        self.loop.run_forever()

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

    def load_dialogs(self, on_result):
        self._request(on_result, self._load_dialogs_async)

    def load_messages(self, dialog_id, on_result):
        self._request(on_result, self._load_messages_async, dialog_id)

    def send_message(self, dialog_id, text, on_result):
        self._request(on_result, self._send_message_async, dialog_id, text)

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
        except (ConnectionError, OSError):
            on_result(None, ERR_CONNECTION_KEY)
        except Exception:
            on_result(None, ERR_GENERAL_KEY)
        else:
            on_result(result, None)

    async def _load_dialogs_async(self):
        dialogs = await self.client.get_dialogs(limit=DIALOGS_LIMIT)
        self.entities = {dialog.id: dialog.input_entity for dialog in dialogs}
        return [
            {"id": dialog.id, "title": dialog.name, "unread": dialog.unread_count}
            for dialog in dialogs
        ]

    async def _load_messages_async(self, dialog_id):
        messages = await self.client.get_messages(self.entities[dialog_id], limit=MESSAGES_LIMIT)
        # Telegram returns newest first; the UI reads oldest first.
        return [
            {
                "sender": get_display_name(message.sender) if message.sender else EMPTY_STRING,
                "text": message.message or EMPTY_STRING,
                "date": message.date,
                "outgoing": message.out,
            }
            for message in reversed(messages)
        ]

    async def _send_message_async(self, dialog_id, text):
        await self.client.send_message(self.entities[dialog_id], text)

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
