"""Your own account: profile, two-step verification, phone number, privacy, devices, notifications, signing out.

Part of TelegramManager (core.telegram_client): its methods run as that thread's, on its event loop."""
import logging
import asyncio
from telethon.password import compute_check
from telethon.errors import UsernameNotModifiedError
from telethon.tl import functions, types
from telethon.utils import get_display_name
from core.constants import (
    EMPTY_STRING, STEP_DONE, ERR_LOGOUT_KEY, MUTE_FOREVER, PRIVACY_EVERYONE, PRIVACY_CONTACTS, PRIVACY_NOBODY,
    DELETE_ACCOUNT_REASON,
)
from core.tg_shared import EmailNotConfirmedError, NOTIFY_PEERS, PRIVACY_KEYS

logger = logging.getLogger(__name__)


class AccountMixin:
    def load_me(self, on_result):
        """The result is {"name", "phone"} of the account signed in."""
        self._request(on_result, self._load_me_async)

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

    def load_notify(self, on_result):
        """The result is {NOTIFY_* kind: whether its notifications are on} for the whole account."""
        self._request(on_result, self._load_notify_async)

    def save_notify(self, changes, on_result):
        self._request(on_result, self._save_notify_async, changes)

    def load_countries(self, language, on_result):
        """The result is Telegram's countries as [{"iso", "name", "code", "codes"}], named in `language`
        where Telegram has the names: "code" is the country's calling code, "codes" every start of a
        number that belongs to it (its code, or its code and a prefix where countries share a code)."""
        self._request(on_result, self._load_countries_async, language)

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

    def log_out(self):
        """Ends the session on Telegram, then reports the next login step through ui_callback."""
        asyncio.run_coroutine_threadsafe(self._log_out_async(), self.loop)

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

    async def _load_me_async(self):
        me = await self.client.get_me()
        return {"name": get_display_name(me), "phone": "+" + me.phone if getattr(me, "phone", None) else EMPTY_STRING}

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

    async def _load_countries_async(self, language):
        result = await self.client(functions.help.GetCountriesListRequest(lang_code=language, hash=0))
        countries = []
        for country in getattr(result, "countries", []):
            if getattr(country, "hidden", False) or not country.country_codes:
                continue
            codes = [
                code.country_code + prefix
                for code in country.country_codes for prefix in (code.prefixes or [EMPTY_STRING])
            ]
            countries.append({
                "iso": country.iso2, "name": getattr(country, "name", None) or country.default_name,
                "code": country.country_codes[0].country_code, "codes": codes,
            })
        return sorted(countries, key=lambda country: country["name"])
