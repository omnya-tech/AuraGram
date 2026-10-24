"""Shared test setup: one wx.App, a fake Telegram, and a main window that is never shown.

Nothing here touches the network or the real session: the Telethon client is
replaced by FakeTelegramClient before the app's manager creates it.
"""
import datetime
import os
import tempfile
import time
import unittest
from unittest import mock

import wx
from telethon.errors import RPCError
from telethon.tl import types
from telethon.utils import get_input_peer, parse_username

import core.key_conflicts
import core.settings
import core.sounds
import core.updates
import core.telegram_client as telegram_client
from core.i18n import I18NManager
from core.settings import Settings

NOW = datetime.datetime.now(datetime.timezone.utc)
_app = None


def get_app():
    """wx allows one App per process, so every test shares this one."""
    global _app
    if _app is None:
        _app = wx.App()
        # Without an active loop, timers and CallAfter would never fire in tests.
        _app.test_loop = wx.GUIEventLoop()
        wx.EventLoop.SetActive(_app.test_loop)
    return _app


def pump(condition=None, timeout=3.0):
    """Run pending UI events until `condition()` is true; returns whether it became true."""
    app = get_app()
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.Yield()
        app.ProcessPendingEvents()
        if condition is not None:
            try:
                if condition():
                    return True
            except Exception:
                pass
        time.sleep(0.005)
    return condition is None


class Record:
    """A plain object with whatever attributes it is given, standing in for Telethon results."""

    def __init__(self, **attributes):
        self.__dict__.update(attributes)


def make_user(user_id, name, contact=True, bot=False, is_self=False):
    return types.User(id=user_id, first_name=name, contact=contact, bot=bot, is_self=is_self, access_hash=1)


def make_channel(channel_id, title, group=False, creator=False, admin_rights=None):
    return types.Channel(
        id=channel_id, title=title, photo=None, date=NOW, megagroup=group, broadcast=not group,
        creator=creator, admin_rights=admin_rights, access_hash=1
    )


def make_member(user_id, name, participant=None, is_self=False):
    """A group member as Telethon returns it: a user carrying its membership record."""
    member = make_user(user_id, name, is_self=is_self)
    member.participant = participant
    return member


def make_message(message_id, text="", outgoing=False, sender=None, **extra):
    attributes = dict(
        id=message_id, message=text, out=outgoing, sender=sender, date=NOW,
        pinned=False, reply_to_msg_id=None, reactions=None
    )
    attributes.update(extra)
    return Record(**attributes)


class FakeTelegramClient:
    """In-memory Telegram. Tests set `chats`, `history` and `scheduled`, then read `calls`."""

    chats = []        # (entity, unread, archived)
    history = {}      # peer id -> messages, oldest first
    scheduled = {}    # peer id -> messages
    folders = []
    members = []      # users with a `participant` attribute, as get_participants returns them
    banned = []
    invites = []      # ChatInviteExported objects
    public = {}       # username -> entity, for what can be found without being in the chat list
    blocked_users = []
    contacts = None   # users GetContactsRequest returns, where a test sets them
    sticker_sets = []  # (title, [emoji, ...])
    threads = {}      # (peer id, post or topic id) -> messages, oldest first
    topics = []
    muted_kinds = set()  # names of the InputNotify* kinds silenced by default on the account
    drafts = {}       # peer id -> text left unsent from another device
    progress_steps = (100, 101, 200)  # bytes done, out of 200, that a transfer reports on its way
    transfer_gate = None  # an asyncio.Event a test sets to let a held upload finish
    history_gate = None
    discussion_groups = []
    common_chats = []  # chats GetCommonChatsRequest says are shared with a person
    discussions = {}  # (channel peer id, post id) -> (discussion group, id of the post's twin there)
    send_as = []      # who GetSendAsRequest says this account may write as
    full_chat = {}    # extra attributes of what GetFullChannelRequest answers
    join_requests = []  # users waiting to be let into a chat
    revoked_invites = 0  # how many revoked links GetExportedChatInvitesRequest counts
    admin_log = []    # events iter_admin_log yields
    inline_results = {}  # bot username -> what its inline query answers
    created = []      # channels and groups made by CreateChannelRequest
    link_joiners = {}  # (link, waiting for approval) -> users who came by it
    emoji_sets = []   # titles of the emoji packs added to the account
    stats = None      # what the statistics requests answer; None for a chat that has none
    stories = None    # what GetAllStoriesRequest answers, where a test sets it
    two_step_password = None  # the account's two-step verification password, if it has one
    profile_photos = []
    audience = None   # (reactions result, read participants), where a test sets it
    recent_stickers = []
    invitation = None  # (title, entity) behind any invitation link, where a test sets it
    read_outbox = None  # id of the newest sent message the other side has read, where a test sets it
    calls = []
    created_with = []  # the keyword arguments each client was made with, in order

    @classmethod
    def reset(cls, chats, history=None):
        cls.created_with = []
        cls.chats = chats
        cls.history = history or {}
        cls.scheduled = {}
        cls.folders = []
        cls.members = []
        cls.banned = []
        cls.invites = []
        cls.read_outbox = None
        cls.public = {}
        cls.blocked_users = []
        cls.contacts = None
        cls.sticker_sets = []
        cls.threads = {}
        cls.topics = []
        cls.audience = None
        cls.two_step_password = None
        cls.stories = None
        cls.full_chat = {}
        cls.join_requests = []
        cls.revoked_invites = 0
        cls.admin_log = []
        cls.inline_results = {}
        cls.created = []
        cls.link_joiners = {}
        cls.emoji_sets = []
        cls.discussion_groups = []
        cls.common_chats = []
        cls.discussions = {}
        cls.send_as = []
        cls.stats = None
        cls.transfer_gate = None
        # An asyncio.Event a test sets to let a chat's messages arrive; None for at once.
        cls.history_gate = None
        # Chats (by peer id) that refuse what is forwarded to them, as one this account may not write in does.
        cls.refused_forwards = set()
        cls.muted_kinds = set()
        cls.drafts = {}
        cls.profile_photos = []
        cls.recent_stickers = []
        cls.invitation = None
        cls.calls = []

    def __init__(self, *args, **kwargs):
        self.connected = False
        self.handlers = {}
        self.created_with.append(kwargs)

    def add_event_handler(self, handler, event):
        self.handlers[type(event).__name__] = handler

    def is_connected(self):
        return self.connected

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.connected = False

    async def is_user_authorized(self):
        return True

    async def iter_dialogs(self, limit):
        for dialog in await self.get_dialogs(limit):
            yield dialog

    async def get_dialogs(self, limit):
        return [
            Record(
                id=telegram_client.get_peer_id(entity), entity=entity, unread_count=unread,
                pinned=False, archived=archived, input_entity=get_input_peer(entity),
                dialog=Record(notify_settings=Record(mute_until=None), unread_mark=False),
                draft=Record(text=self.drafts.get(telegram_client.get_peer_id(entity))),
                # The chat list previews the newest message of each chat.
                message=(self.history.get(telegram_client.get_peer_id(entity)) or [None])[-1]
            )
            for entity, unread, archived in self.chats[:limit]
        ]

    async def edit_folder(self, entity, folder):
        self.calls.append(("folder", telegram_client.get_peer_id(entity), folder))

    async def iter_download(self, media, request_size=None):
        """The sound of a message piece by piece, as Telegram sends it to be played on arrival."""
        self.calls.append(("stream", request_size))
        yield b"sou"
        if self.transfer_gate is not None:
            await self.transfer_gate.wait()
        yield b"nd"

    async def download_media(self, message, file, progress_callback=None):
        self.calls.append(("download", getattr(message, "id", None), file))
        for done in self.progress_steps if progress_callback else ():
            progress_callback(done, 200)
        if self.transfer_gate is not None:
            await self.transfer_gate.wait()
        if file is bytes:
            # Asked for in memory: nothing is written anywhere.
            return b"sound"
        return file + "saved.bin"

    async def get_messages(self, entity, limit=None, max_id=0, ids=None, search=None, filter=None, scheduled=False,
                           reply_to=None, offset_id=0, add_offset=0, offset_date=None, reverse=False):
        if entity is None:
            # A search through every chat: each hit says which chat it is from.
            hits = []
            for chat, _, _ in self.chats:
                for message in self.history.get(telegram_client.get_peer_id(chat), []):
                    if search in message.message:
                        message.chat = chat
                        hits.append(message)
            return hits[:limit]
        peer_id = telegram_client.get_peer_id(entity)
        if self.history_gate is not None and not (scheduled or reply_to or ids or search or filter):
            # Held, as a slow connection would hold it, until the test lets it through.
            await self.history_gate.wait()
        messages = (self.scheduled if scheduled else self.history).get(peer_id, [])
        if reply_to is not None:
            messages = self.threads.get((peer_id, reply_to), [])
        if ids is not None:
            # A message may be known only as part of a topic or of a post's comments.
            in_threads = [m for (peer, _), thread in self.threads.items() if peer == peer_id for m in thread]
            return next(message for message in list(messages) + in_threads if message.id == ids)
        if search:
            messages = [message for message in messages if search in message.message]
        if filter is types.InputMessagesFilterPinned:
            messages = [message for message in messages if message.pinned]
        if max_id:
            messages = [message for message in messages if message.id < max_id]
        if reverse:
            # From a day onwards, oldest first.
            return [message for message in messages if message.date >= offset_date][:limit]
        if offset_id:
            # A page with that message in the middle, as far as there are messages on both sides.
            ids_in_order = [message.id for message in messages]
            if offset_id not in ids_in_order:
                return []
            start = max(ids_in_order.index(offset_id) + add_offset + 1, 0)
            return list(reversed(messages[start:start + limit]))
        newest_first = list(reversed(messages))
        return newest_first[:limit] if limit else newest_first

    async def send_read_acknowledge(self, entity):
        self.calls.append(("read", telegram_client.get_peer_id(entity)))

    async def send_message(self, entity, text=None, reply_to=None, schedule=None, file=None, silent=None):
        peer_id = telegram_client.get_peer_id(entity)
        if silent:
            self.calls.append(("silent", peer_id, text))
        thread = self.threads.get((peer_id, reply_to))
        if thread is not None and schedule is None:
            thread.append(make_message(1000 + len(thread), text, outgoing=True, reply_to_msg_id=reply_to))
        self.calls.append(("send", peer_id, text, reply_to, schedule))
        if isinstance(file, types.InputMediaPoll):
            # What was asked of the poll: its settings, and a quiz's right answer and explanation.
            self.calls.append(("poll", peer_id, file))
        if schedule is None and text is not None:
            messages = self.history.setdefault(peer_id, [])
            next_id = max((message.id for message in messages), default=0) + 1
            messages.append(make_message(next_id, text, outgoing=True, reply_to_msg_id=reply_to))
            return messages[-1]

    async def send_file(self, entity, file, caption=None, force_document=False, voice_note=False, reply_to=None,
                        progress_callback=None):
        for done in self.progress_steps if progress_callback else ():
            progress_callback(done, 200)
            if self.transfer_gate is not None:
                # Held here so a test can look at the window in the middle of the transfer.
                await self.transfer_gate.wait()
        self.calls.append(("send_file", telegram_client.get_peer_id(entity), file, caption, force_document, reply_to))

    async def upload_file(self, path, progress_callback=None):
        return "uploaded:" + path

    async def get_profile_photos(self, entity, limit=None):
        return list(self.profile_photos)

    async def edit_2fa(self, current_password=None, new_password=None, hint="", email=None, email_code_callback=None):
        if current_password != self.two_step_password:
            raise telegram_client.PasswordHashInvalidError(None)
        self.calls.append(("2fa", bool(new_password), hint))
        type(self).two_step_password = new_password
        if email:
            # As Telegram does: the password is in place before the email is confirmed.
            if await email_code_callback(6) != "123456":
                raise telegram_client.CodeInvalidError(None)
            self.calls.append(("2fa_email", email))

    async def edit_message(self, entity, message_id, text):
        self.calls.append(("edit", message_id, text))
        self._find(entity, message_id).message = text

    async def delete_messages(self, entity, message_ids, revoke=True):
        peer_id = telegram_client.get_peer_id(entity)
        self.calls.append(("delete", peer_id, list(message_ids)))
        if not revoke:
            self.calls.append(("delete_for_me", peer_id, list(message_ids)))
        self.history[peer_id] = [m for m in self.history.get(peer_id, []) if m.id not in message_ids]

    async def pin_message(self, entity, message_id, notify=False):
        self.calls.append(("pin", message_id))

    async def unpin_message(self, entity, message_id):
        self.calls.append(("unpin", message_id))

    async def forward_messages(self, to_entity, message_ids, from_entity):
        if telegram_client.get_peer_id(to_entity) in self.refused_forwards:
            from telethon.errors import ChatWriteForbiddenError
            raise ChatWriteForbiddenError(request=None)
        self.calls.append((
            "forward", telegram_client.get_peer_id(to_entity), message_ids,
            telegram_client.get_peer_id(from_entity)
        ))

    async def delete_dialog(self, entity):
        self.calls.append(("leave", telegram_client.get_peer_id(entity)))

    async def get_entity(self, peer):
        if isinstance(peer, str):
            username = parse_username(peer)[0]
            if username not in self.public:
                raise ValueError("nobody by that name")
            return self.public[username]
        peer_id = telegram_client.get_peer_id(peer)
        known = [entity for entity, _, _ in self.chats] + list(self.public.values())
        for entity in known:
            if telegram_client.get_peer_id(entity) == peer_id:
                return entity
        raise ValueError("never seen")

    async def get_participants(self, entity, limit=None, search="", filter=None):
        if filter is types.ChannelParticipantsKicked:
            return list(self.banned)
        if filter is types.ChannelParticipantsAdmins:
            return [member for member in self.members if isinstance(
                getattr(member, "participant", None), (types.ChannelParticipantAdmin, types.ChannelParticipantCreator)
            )]
        return [member for member in self.members if search.lower() in member.first_name.lower()]

    async def inline_query(self, bot, query, entity=None):
        self.calls.append(("inline_query", bot.username, query))
        return list(self.inline_results.get(bot.username, []))

    async def iter_admin_log(self, entity, limit=None, **narrowed):
        self.calls.append(("admin_log", narrowed))
        for event in self.admin_log:
            yield event

    async def kick_participant(self, entity, user):
        self.calls.append(("kick", user.user_id))

    async def edit_permissions(self, entity, user=None, until_date=None, **permissions):
        self.calls.append(("permissions", getattr(user, "user_id", None), permissions))
        if until_date is not None:
            self.calls.append(("until", getattr(user, "user_id", None), until_date))

    async def edit_admin(self, entity, user, **rights):
        self.calls.append(("admin", user.user_id, rights))

    async def __call__(self, request):
        name = type(request).__name__
        self.calls.append((name, request))
        if name == "GetPeerDialogsRequest" and self.read_outbox is not None:
            return Record(dialogs=[Record(read_outbox_max_id=self.read_outbox)])
        if name == "GetContactsRequest":
            return Record(users=list(self.contacts or []))
        if name == "GetAllStickersRequest":
            return Record(sets=[
                Record(id=index, access_hash=1, title=title) for index, (title, emojis) in enumerate(self.sticker_sets)
            ])
        if name in ("GetStickerSetRequest", "GetRecentStickersRequest"):
            emojis = self.recent_stickers if name == "GetRecentStickersRequest" else self.sticker_sets[request.stickerset.id][1]
            stickers = [
                Record(attributes=[types.DocumentAttributeSticker(alt=emoji, stickerset=types.InputStickerSetEmpty())])
                for emoji in emojis
            ]
            return Record(stickers=stickers, documents=stickers)
        if name == "GetNotifySettingsRequest":
            muted = type(request.peer).__name__ in self.muted_kinds
            return Record(mute_until=NOW + datetime.timedelta(days=3650) if muted else None)
        if name == "SendChangePhoneCodeRequest":
            if request.phone_number == "+taken":
                raise telegram_client.PhoneNumberOccupiedError(None)
            return Record(phone_code_hash="change-hash")
        if name == "TranslateTextRequest":
            return Record(result=[Record(text="translated #%d" % request.id[0])])
        if name == "GetAllStoriesRequest" and self.stories is not None:
            return self.stories
        if name == "GetPasswordRequest":
            return Record(has_password=self.two_step_password is not None)
        if name == "GetDiscussionMessageRequest":
            group, twin_id = self.discussions[(telegram_client.get_peer_id(request.peer), request.msg_id)]
            return Record(
                messages=[Record(id=twin_id, peer_id=types.PeerChannel(group.id))], chats=[group]
            )
        if name == "GetGroupsForDiscussionRequest":
            return Record(chats=list(self.discussion_groups))
        if name == "ExportChatInviteRequest" and getattr(request, "legacy_revoke_permanent", False):
            return Record(link="https://t.me/+primary%d" % telegram_client.get_peer_id(request.peer))
        if name == "GetSendAsRequest":
            return Record(
                chats=[sender for sender in self.send_as if not isinstance(sender, types.User)],
                users=[sender for sender in self.send_as if isinstance(sender, types.User)]
            )
        if name == "GetForumTopicsRequest":
            return Record(topics=list(self.topics))
        if name == "GetMessageReactionsListRequest" and self.audience is not None:
            return self.audience[0]
        if name == "GetMessageReadParticipantsRequest" and self.audience is not None:
            return self.audience[1]
        if name == "GetBlockedRequest":
            return Record(users=list(self.blocked_users))
        if name == "ImportContactsRequest":
            return Record(users=[self.public[contact.phone] for contact in request.contacts if contact.phone in self.public])
        if name == "SearchRequest":
            found = [entity for username, entity in self.public.items() if request.q in username]
            return Record(
                users=[entity for entity in found if isinstance(entity, types.User)],
                chats=[entity for entity in found if not isinstance(entity, types.User)]
            )
        if name == "CheckChatInviteRequest":
            return Record(title=self.invitation[0])
        if name == "ImportChatInviteRequest":
            return Record(chats=[self.invitation[1]])
        if name == "JoinChannelRequest":
            for entity in self.public.values():
                if telegram_client.get_peer_id(entity) == telegram_client.get_peer_id(request.channel):
                    entity.left = False
        if name == "GetDialogFiltersRequest":
            return Record(filters=self.folders)
        if name == "UpdateDialogFilterRequest":
            # As Telegram does: the folder of that number is replaced, or gone if none is given.
            type(self).folders = [folder for folder in self.folders if folder.id != request.id]
            if request.filter is not None:
                self.folders.append(request.filter)
        if name == "GetCommonChatsRequest":
            return Record(chats=list(self.common_chats))
        if name == "ReportRequest":
            if request.option == b"":
                return types.ReportResultChooseOption(title="Why?", options=[
                    types.MessageReportOption(text="Spam", option=b"spam"),
                    types.MessageReportOption(text="Other", option=b"other"),
                ])
            if request.option == b"other" and not request.message:
                return types.ReportResultAddComment(option=b"other", optional=False)
            return types.ReportResultReported()
        if name == "DeleteScheduledMessagesRequest":
            peer_id = telegram_client.get_peer_id(request.peer)
            self.scheduled[peer_id] = [m for m in self.scheduled.get(peer_id, []) if m.id not in request.id]
        if name == "GetPrivacyRequest":
            return Record(rules=[types.PrivacyValueAllowAll()])
        if name == "GetAuthorizationsRequest":
            return Record(authorizations=[])
        if name == "DeleteHistoryRequest":
            return Record(offset=0)
        if name == "ExportMessageLinkRequest":
            return Record(link="https://t.me/c/%d/%d" % (request.channel.channel_id, request.id))
        if name == "GetExportedChatInvitesRequest":
            if request.revoked:
                return Record(count=self.revoked_invites, invites=[])
            return Record(invites=list(self.invites))
        if name == "DeleteRevokedExportedChatInvitesRequest":
            type(self).revoked_invites = 0
        if name == "GetChatInviteImportersRequest" and request.link:
            users = self.link_joiners.get((request.link, bool(request.requested)), [])
            return Record(importers=[Record(user_id=user.id) for user in users], users=list(users))
        if name == "GetEmojiStickersRequest":
            return Record(sets=[Record(id=index, access_hash=1, title=title) for index, title in enumerate(self.emoji_sets)])
        if name == "GetChatInviteImportersRequest":
            return Record(
                importers=[Record(user_id=user.id) for user in self.join_requests], users=list(self.join_requests)
            )
        if name == "HideAllChatJoinRequestsRequest":
            type(self).join_requests = []
        if name == "GetBoostsStatusRequest":
            return Record(level=2, boosts=7, next_level_boosts=10, boost_url="https://t.me/boost/x")
        if name == "ExportChatInviteRequest":
            self.invites.append(types.ChatInviteExported(
                link="https://t.me/+new%d" % len(self.invites), admin_id=10, date=NOW,
                title=request.title, request_needed=request.request_needed,
                expire_date=request.expire_date, usage_limit=request.usage_limit
            ))
        if name == "EditExportedChatInviteRequest":
            self.invites[:] = [invite for invite in self.invites if invite.link != request.link]
        if name == "GetChannelsRequest":
            made = [entity for entity, _, _ in self.chats] + list(self.created)
            wanted = {getattr(channel, "channel_id", None) for channel in request.id}
            return Record(chats=[entity for entity in made if entity.id in wanted])
        if name == "CreateChannelRequest":
            made = make_channel(500, request.title, group=bool(request.megagroup), creator=True)
            self.created.append(made)
            return Record(chats=[made])
        if name == "GetFullChannelRequest":
            return Record(full_chat=Record(
                about="about text", participants_count=len(self.members), exported_invite=None, **self.full_chat
            ))
        if name in ("GetBroadcastStatsRequest", "GetMegagroupStatsRequest"):
            if self.stats is None:
                raise RPCError(None, "BROADCAST_REQUIRED", 400)
            return self.stats
        if name == "GetFullUserRequest":
            return Record(users=[make_user(1, "Me")], full_user=Record(about=""))
        return None

    def _find(self, entity, message_id):
        messages = self.history[telegram_client.get_peer_id(entity)]
        return next(message for message in messages if message.id == message_id)


class FakeChooser:
    """Stands in for wx's modal choice and text dialogs; tests script the answers on the class."""

    confirmed = True
    selection = 0
    selections = []
    picked = None     # what the window that picks chats answers; None for the one chat at `selection`
    values = []       # consumed in order by GetValue
    last_choices = None
    last_message = None

    def __init__(self, parent, message, caption="", choices=None, *args, **kwargs):
        FakeChooser.last_message = message
        if choices is not None:
            FakeChooser.last_choices = list(choices)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ShowModal(self):
        return wx.ID_OK if FakeChooser.confirmed else wx.ID_CANCEL

    def GetSelection(self):
        return FakeChooser.selection

    def SetSelection(self, index):
        pass

    def GetSelections(self):
        return list(FakeChooser.selections)

    def SetSelections(self, indexes):
        pass

    def GetValue(self):
        return FakeChooser.values.pop(0)

    def GetChildren(self):
        # No real list inside to type in.
        return []


class FakeChatPicker(FakeChooser):
    """Stands in for the window that picks chats from a searched list."""

    def __init__(self, parent, i18n, prompt, titles):
        FakeChooser.last_message = prompt
        FakeChooser.last_choices = list(titles)

    def chosen(self):
        return [FakeChooser.selection] if FakeChooser.picked is None else list(FakeChooser.picked)


class WindowTestCase(unittest.TestCase):
    """Base for tests that drive the real main window against FakeTelegramClient."""

    chats = []
    history = {}

    def setUp(self):
        get_app()
        import ui.chat_list
        import ui.main_frame as main_frame_module
        self.spoken = []
        self.played = []
        self.boxes = []
        self.box_answer = wx.YES
        settings_file = os.path.join(tempfile.mkdtemp(), "settings.json")
        FakeTelegramClient.reset(list(self.chats), {key: list(value) for key, value in self.history.items()})
        FakeChooser.confirmed, FakeChooser.selection, FakeChooser.values = True, 0, []
        FakeChooser.selections = []
        FakeChooser.picked = None

        def message_box(message, *args, **kwargs):
            self.boxes.append(message)
            return self.box_answer

        patches = [
            mock.patch.object(telegram_client, "TelegramClient", FakeTelegramClient),
            mock.patch.object(core.settings, "SETTINGS_FILE", settings_file),
            mock.patch.object(wx, "MessageBox", message_box),
            mock.patch.object(core.sounds, "play", self.played.append),
            # No test goes out to ask whether a newer release is published.
            mock.patch.object(core.updates, "UPDATE_INFO_URL", ""),
            # What other programs on the testing machine hold is no business of the tests.
            mock.patch.object(core.key_conflicts, "find", lambda texts: {}),
            mock.patch.object(wx, "SingleChoiceDialog", FakeChooser),
            mock.patch.object(wx, "MultiChoiceDialog", FakeChooser),
            mock.patch.object(wx, "TextEntryDialog", FakeChooser),
            mock.patch.object(ui.chat_list, "ChatPickerDialog", FakeChatPicker),
        ]
        # Every UI module imports speak() by name, so each copy has to be silenced.
        for module in self.speaking_modules():
            patches.append(mock.patch.object(module, "speak", self.spoken.append))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

        self.i18n = I18NManager("ar")
        self.manager = telegram_client.TelegramManager(lambda step, error_key=None: None)
        self.manager.start()
        self.addCleanup(self.manager.stop)
        self.frame = main_frame_module.MainFrame(self.i18n, self.manager, Settings(), lambda: None)
        self.addCleanup(self.destroy_frame)
        # Context menus would block waiting for a click; record what they offer instead.
        self.menu_labels = []
        self.frame.PopupMenu = lambda menu, *args: self.menu_labels.__setitem__(
            slice(None), [item.GetItemLabelText() for item in menu.GetMenuItems()]
        )
        self.assertTrue(
            pump(lambda: len(self.frame.all_dialogs) == len(self.chats)), "chat list did not load"
        )

    def speaking_modules(self):
        """Every loaded UI module that announces through the screen reader."""
        import pkgutil
        import importlib
        import ui
        modules = [importlib.import_module("ui." + info.name) for info in pkgutil.iter_modules(ui.__path__)]
        # And the speech module itself: the app's remarks of every kind go through its say().
        import core.speech
        return [module for module in modules if hasattr(module, "speak")] + [core.speech]

    def destroy_frame(self):
        if self.frame:
            self.frame.Destroy()
        pump(timeout=0.05)

    def text(self, key):
        return self.i18n.get_string(key)

    def open_chat(self, index=0):
        self.frame.dialogs_list.SetSelection(index)
        self.frame.on_open_dialog(None)
        chat_id = self.frame.dialogs[index]["id"]
        expected = len(FakeTelegramClient.history.get(chat_id, []))
        # The status bar turns "ready" last; the send button cannot be the sign,
        # since it stays disabled in a channel this account may not post to.
        # Or, for a chat entered with unread messages, the count of them that replaces it.
        unread = self.frame.dialogs[index]["unread"]
        done = (self.text("STATUS_READY"), self.text("MSG_NEW_MESSAGES_FORMAT").format(count=unread))
        self.assertTrue(pump(
            lambda: self.frame.current_dialog_id == chat_id and len(self.frame.messages) == min(expected, 50)
            and self.frame.GetStatusBar().GetStatusText() in done
        ), "chat did not open")

    def calls(self, name):
        return [call for call in FakeTelegramClient.calls if call[0] == name]

    def context_event(self, list_box):
        return wx.ContextMenuEvent(wx.wxEVT_CONTEXT_MENU, list_box.GetId(), wx.DefaultPosition)

    def press(self, key_code):
        event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        event.SetKeyCode(key_code)
        return self.frame.ProcessEvent(event)
