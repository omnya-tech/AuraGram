"""The list of chats and what is done to a chat as a whole: folders, contacts, blocking, finding, joining, creating, muting, pinning, archiving, leaving.

Part of TelegramManager (core.telegram_client): its methods run as that thread's, on its event loop."""
import logging
import asyncio
import datetime
import urllib.parse
from telethon.errors import UserNotParticipantError, FloodWaitError, RPCError
from telethon.tl import functions, types
from telethon.utils import get_display_name, get_input_peer, get_peer_id, parse_username
from core.constants import (
    EMPTY_STRING, DIALOGS_LIMIT, MUTE_FOREVER, FOLDER_CATEGORIES, CATEGORY_CONTACTS, CATEGORY_NON_CONTACTS,
    CATEGORY_GROUPS, CATEGORY_BROADCASTS, CATEGORY_BOTS, USER_STATUS_KEYS, SAVED_MESSAGES_PEER, BLOCKED_LIMIT,
    GLOBAL_SEARCH_LIMIT, NOTIFY_USERS, NOTIFY_GROUPS, NOTIFY_CHANNELS, TYPING_SEND_SECONDS, FOLDER_EXCLUSIONS,
)
from core.tg_shared import ChatNotFoundError

logger = logging.getLogger(__name__)


class ChatsMixin:
    def load_dialogs(self, on_result, limit=DIALOGS_LIMIT, on_progress=None):
        """The first `limit` chats of the account. on_progress(percent) is called from this thread as they come."""
        self._request(on_result, self._load_dialogs_async, limit, self._percent_reporter(on_progress))

    def send_typing(self, dialog_id):
        """Let the other side see "typing"; asked often, sent at most once every few seconds."""
        asyncio.run_coroutine_threadsafe(self._send_typing_async(dialog_id), self.loop)

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

    def leave_chat(self, dialog_id, on_result):
        """Leaves a group or channel; for a private chat, deletes it from this account's list."""
        self._request(on_result, self._leave_chat_async, dialog_id)

    def open_saved_messages(self, on_result):
        """The account's chat with itself; the result is shaped like those of load_dialogs."""
        self._request(on_result, self._find_chat_async, SAVED_MESSAGES_PEER)

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

    def mark_read(self, dialog_id):
        asyncio.run_coroutine_threadsafe(self._mark_read_async(dialog_id), self.loop)

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
            # The owner or an admin of a group or channel, who gets its management.
            "is_admin": not is_user and bool(getattr(entity, "creator", False) or getattr(entity, "admin_rights", None)),
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
        # A link to a bot may carry what to start it with: t.me/name?start=..., tg://resolve?domain=name&start=...
        start_param = (urllib.parse.parse_qs(urllib.parse.urlsplit(text.strip()).query).get("start") or [None])[0]
        if start_param:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(text.strip()).query)
            text = (query.get("domain") or [text.split("?")[0]])[0]
        invite_hash, is_invite = parse_username(text)
        if not is_invite:
            chat = await self._find_chat_async(text)
            if start_param and chat["category"] == CATEGORY_BOTS:
                chat["start_param"] = start_param
            return {"chat": chat, "invite": None}
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
        # The answer may name other chats too: the new one is the channel of that name made last.
        made = [chat for chat in result.chats if isinstance(chat, types.Channel) and chat.title == title]
        entity = max(made, key=lambda chat: chat.id) if made else result.chats[0]
        try:
            # Asked for again, so whether it is a group or a channel is as Telegram now holds it.
            fresh = await self.client(functions.channels.GetChannelsRequest([get_input_peer(entity)]))
            entity = next((chat for chat in fresh.chats if chat.id == entity.id), entity)
        except (RPCError, TypeError, ValueError, AttributeError):
            logger.warning("Could not read the new chat back", exc_info=True)
        if isinstance(entity, types.Channel) and bool(entity.megagroup) == is_channel:
            logger.warning("Asked for a %s, Telegram made a %s", "channel" if is_channel else "group",
                           "group" if entity.megagroup else "channel")
        chat = self._describe_chat(entity)
        self.entities[chat["id"]] = get_input_peer(entity)
        return chat

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

    async def _save_draft_async(self, dialog_id, text):
        # Best effort: a draft that fails to sync is still kept in the app.
        try:
            await self.client(functions.messages.SaveDraftRequest(peer=self.entities[dialog_id], message=text))
        except Exception:
            pass

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

    async def _mark_read_async(self, dialog_id):
        # Best effort: failing to mark as read must not fail the request around it.
        try:
            await self.client.send_read_acknowledge(self.entities[dialog_id])
        except Exception:
            pass

    async def _leave_chat_async(self, dialog_id):
        try:
            await self.client.delete_dialog(self.entities[dialog_id])
        except UserNotParticipantError:
            # Never joined, or already gone: either way it is left.
            pass
