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
from telethon.tl import types

import core.settings
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
    calls = []

    @classmethod
    def reset(cls, chats, history=None):
        cls.chats = chats
        cls.history = history or {}
        cls.scheduled = {}
        cls.folders = []
        cls.members = []
        cls.banned = []
        cls.calls = []

    def __init__(self, *args, **kwargs):
        self.connected = False
        self.handlers = {}

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

    async def get_dialogs(self, limit):
        return [
            Record(
                id=telegram_client.get_peer_id(entity), entity=entity, unread_count=unread,
                pinned=False, archived=archived, input_entity=telegram_client.get_input_peer(entity),
                dialog=Record(notify_settings=Record(mute_until=None))
            )
            for entity, unread, archived in self.chats
        ]

    async def get_messages(self, entity, limit=None, max_id=0, ids=None, search=None, filter=None, scheduled=False):
        peer_id = telegram_client.get_peer_id(entity)
        messages = (self.scheduled if scheduled else self.history).get(peer_id, [])
        if ids is not None:
            return next(message for message in messages if message.id == ids)
        if search:
            messages = [message for message in messages if search in message.message]
        if filter is types.InputMessagesFilterPinned:
            messages = [message for message in messages if message.pinned]
        if max_id:
            messages = [message for message in messages if message.id < max_id]
        newest_first = list(reversed(messages))
        return newest_first[:limit] if limit else newest_first

    async def send_read_acknowledge(self, entity):
        self.calls.append(("read", telegram_client.get_peer_id(entity)))

    async def send_message(self, entity, text=None, reply_to=None, schedule=None, file=None):
        peer_id = telegram_client.get_peer_id(entity)
        self.calls.append(("send", peer_id, text, reply_to, schedule))
        if schedule is None and text is not None:
            messages = self.history.setdefault(peer_id, [])
            next_id = max((message.id for message in messages), default=0) + 1
            messages.append(make_message(next_id, text, outgoing=True, reply_to_msg_id=reply_to))

    async def edit_message(self, entity, message_id, text):
        self.calls.append(("edit", message_id, text))
        self._find(entity, message_id).message = text

    async def delete_messages(self, entity, message_ids):
        peer_id = telegram_client.get_peer_id(entity)
        self.calls.append(("delete", peer_id, list(message_ids)))
        self.history[peer_id] = [m for m in self.history.get(peer_id, []) if m.id not in message_ids]

    async def pin_message(self, entity, message_id, notify=False):
        self.calls.append(("pin", message_id))

    async def unpin_message(self, entity, message_id):
        self.calls.append(("unpin", message_id))

    async def forward_messages(self, to_entity, message_ids, from_entity):
        self.calls.append((
            "forward", telegram_client.get_peer_id(to_entity), message_ids,
            telegram_client.get_peer_id(from_entity)
        ))

    async def delete_dialog(self, entity):
        self.calls.append(("leave", telegram_client.get_peer_id(entity)))

    async def get_entity(self, peer):
        peer_id = telegram_client.get_peer_id(peer)
        return next(entity for entity, _, _ in self.chats if telegram_client.get_peer_id(entity) == peer_id)

    async def get_participants(self, entity, limit=None, search="", filter=None):
        if filter is types.ChannelParticipantsKicked:
            return list(self.banned)
        return [member for member in self.members if search.lower() in member.first_name.lower()]

    async def kick_participant(self, entity, user):
        self.calls.append(("kick", user.user_id))

    async def edit_permissions(self, entity, user=None, **permissions):
        self.calls.append(("permissions", getattr(user, "user_id", None), permissions))

    async def edit_admin(self, entity, user, **rights):
        self.calls.append(("admin", user.user_id, rights))

    async def __call__(self, request):
        name = type(request).__name__
        self.calls.append((name, request))
        if name == "GetDialogFiltersRequest":
            return Record(filters=self.folders)
        if name == "DeleteScheduledMessagesRequest":
            peer_id = telegram_client.get_peer_id(request.peer)
            self.scheduled[peer_id] = [m for m in self.scheduled.get(peer_id, []) if m.id not in request.id]
        if name == "CreateChannelRequest":
            return Record(chats=[make_channel(500, request.title, group=bool(request.megagroup), creator=True)])
        if name == "GetFullChannelRequest":
            return Record(full_chat=Record(about="about text", participants_count=len(self.members), exported_invite=None))
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


class WindowTestCase(unittest.TestCase):
    """Base for tests that drive the real main window against FakeTelegramClient."""

    chats = []
    history = {}

    def setUp(self):
        get_app()
        import ui.main_frame as main_frame_module
        self.spoken = []
        self.boxes = []
        self.box_answer = wx.YES
        settings_file = os.path.join(tempfile.mkdtemp(), "settings.json")
        FakeTelegramClient.reset(list(self.chats), {key: list(value) for key, value in self.history.items()})
        FakeChooser.confirmed, FakeChooser.selection, FakeChooser.values = True, 0, []

        def message_box(message, *args, **kwargs):
            self.boxes.append(message)
            return self.box_answer

        patches = [
            mock.patch.object(telegram_client, "TelegramClient", FakeTelegramClient),
            mock.patch.object(core.settings, "SETTINGS_FILE", settings_file),
            mock.patch.object(wx, "MessageBox", message_box),
            mock.patch.object(wx, "Bell", lambda: None),
            mock.patch.object(wx, "SingleChoiceDialog", FakeChooser),
            mock.patch.object(wx, "MultiChoiceDialog", FakeChooser),
            mock.patch.object(wx, "TextEntryDialog", FakeChooser),
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
        return [module for module in modules if hasattr(module, "speak")]

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
        self.assertTrue(pump(
            lambda: self.frame.current_dialog_id == chat_id and len(self.frame.messages) == min(expected, 50)
            and self.frame.send_btn.IsEnabled()
        ), "chat did not open")

    def calls(self, name):
        return [call for call in FakeTelegramClient.calls if call[0] == name]

    def context_event(self, list_box):
        return wx.ContextMenuEvent(wx.wxEVT_CONTEXT_MENU, list_box.GetId(), wx.DefaultPosition)

    def press(self, key_code):
        event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        event.SetKeyCode(key_code)
        return self.frame.ProcessEvent(event)
