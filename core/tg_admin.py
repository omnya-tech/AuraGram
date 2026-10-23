"""Running a channel or group: its information and members, management settings, permissions, invite links, topics, statistics and the admin log.

Part of TelegramManager (core.telegram_client): its methods run as that thread's, on its event loop."""
import datetime
from telethon.password import compute_check
from telethon.errors import (
    FloodWaitError, ChatAdminRequiredError, ChatNotModifiedError, ChatAboutNotModifiedError, RPCError,
)
from telethon.tl import functions, types
from telethon.utils import get_display_name, get_input_peer
from core.constants import (
    MEDIA_PERMISSIONS, SENDING_PERMISSIONS, SETTING_ANTISPAM, SETTING_HIDE_MEMBERS,
    SETTING_SIGNATURE_PROFILES, SETTING_AUTOTRANSLATION, SETTING_NAME_COLOR, SETTING_PROFILE_COLOR,
    ANTISPAM_USER_ID, EMPTY_STRING, CHAT_KIND_USER, CHAT_KIND_GROUP, CHAT_KIND_SUPERGROUP, CHAT_KIND_CHANNEL,
    MEMBER_ROLE_OWNER, MEMBER_ROLE_ADMIN, MEMBERS_LIMIT, MEMBER_ACTION_KICK, MEMBER_ACTION_BAN,
    MEMBER_ACTION_PROMOTE, MEMBER_ACTION_DEMOTE, MEMBER_ACTION_UNBAN, MEMBER_ROLE_BANNED, ADMIN_RIGHTS,
    MEMBERS_CURRENT, MEMBERS_BANNED, MEMBERS_REQUESTS, MEMBER_ROLE_PENDING, MEMBER_ROLE_RESTRICTED,
    MEMBER_ACTION_MUTE, MEMBER_ACTION_UNMUTE, MEMBER_ACTION_APPROVE, MEMBER_ACTION_DECLINE, ADMIN_LOG_LIMIT,
    MEMBER_PERMISSIONS, INVITE_LINKS_LIMIT, MEMBER_ACTION_RESTRICT, MEMBER_ACTION_TITLE,
    MEMBER_ACTION_DELETE_MESSAGES, SETTING_USERNAME, SETTING_SIGNATURES, SETTING_HISTORY_HIDDEN,
    SETTING_PROTECTED, SETTING_JOIN_TO_SEND, SETTING_JOIN_REQUEST, SETTING_FORUM, SETTING_SLOW_MODE,
    SETTING_TTL, SETTING_REACTIONS, REACTIONS_ALL, REACTIONS_NONE, REACTIONS_SOME, COMMON_CHATS_LIMIT,
)
from core.tg_shared import StatsUnavailableError, NoInviteLinkError, ADMIN_LOG_ACTION_PREFIX, BANNED_RIGHT_NAMES, KEPT_BANNED_RIGHTS


class AdminMixin:
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

    def load_admin_log(self, dialog_id, on_result, kinds=(), admin_id=None):
        """The result is the recent admin actions in a channel or large group, newest first. `kinds` narrows
        them to some of Telegram's kinds of event (ADMIN_LOG_FILTERS); `admin_id` to one admin's, from load_admins."""
        self._request(on_result, self._load_admin_log_async, dialog_id, kinds, admin_id)

    def load_admins(self, dialog_id, on_result):
        """The result is the chat's admins as [{"id", "name"}]."""
        self._request(on_result, self._load_admins_async, dialog_id)

    def decide_all_requests(self, dialog_id, approved, on_result):
        """Approve every request to join, or decline every one."""
        self._request(on_result, self._decide_all_requests_async, dialog_id, approved)

    def count_revoked_links(self, dialog_id, on_result):
        """The result is how many invite links this account made for the chat and then revoked."""
        self._request(on_result, self._count_revoked_links_async, dialog_id)

    def delete_revoked_links(self, dialog_id, on_result):
        self._request(on_result, self._delete_revoked_links_async, dialog_id)

    def set_group_stickers(self, dialog_id, set_id, on_result):
        """Give a large group one of the sticker sets load_sticker_sets listed; None for none of its own."""
        self._request(on_result, self._set_group_stickers_async, dialog_id, set_id)

    def load_emoji_sets(self, on_result):
        """The result is the emoji packs added to the account as [{"id", "title"}]."""
        self._request(on_result, self._load_emoji_sets_async)

    def set_group_emoji(self, dialog_id, set_id, on_result):
        """Give a large group one of the packs load_emoji_sets listed; None for none of its own."""
        self._request(on_result, self._set_group_emoji_async, dialog_id, set_id)

    def load_link_joiners(self, dialog_id, link, on_result):
        """The result is {"joined": [names], "waiting": [names]} for one of the chat's invite links."""
        self._request(on_result, self._load_link_joiners_async, dialog_id, link)

    def report_not_spam(self, dialog_id, message_id, on_result):
        """Tell Telegram its anti-spam deleted a message (from the admin log) by mistake."""
        self._request(on_result, self._report_not_spam_async, dialog_id, message_id)

    def load_boosts(self, dialog_id, on_result):
        """The result is {"level", "boosts", "next" (boosts the next level needs in all, None at the top), "link"}."""
        self._request(on_result, self._load_boosts_async, dialog_id)

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

    def load_member_permissions(self, dialog_id, on_result):
        """The result is the set of MEMBER_PERMISSIONS names ordinary members currently have."""
        self._request(on_result, self._load_member_permissions_async, dialog_id)

    def save_member_permissions(self, dialog_id, allowed, on_result):
        self._request(on_result, self._save_member_permissions_async, dialog_id, allowed)

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

    def revoke_invite_link(self, dialog_id, link, on_result):
        """Stops a link from working; people who already joined with it stay."""
        self._request(on_result, self._revoke_invite_link_async, dialog_id, link)

    def pin_topic(self, dialog_id, topic_id, pinned, on_result):
        self._request(on_result, self._pin_topic_async, dialog_id, topic_id, pinned)

    async def _default_rights(self, dialog_id):
        entity = await self.client.get_entity(self.entities[dialog_id])
        return getattr(entity, "default_banned_rights", None)

    def _allowed_by(self, banned_rights):
        """The MEMBER_PERMISSIONS members have, read from Telegram's "banned" flags. A flag for a whole
        group of them (all writing, all media) takes each of them away."""
        def banned(field):
            return bool(getattr(banned_rights, field, False))
        allowed = set()
        for name in MEMBER_PERMISSIONS:
            taken = banned(BANNED_RIGHT_NAMES.get(name, name)) \
                or (name in SENDING_PERMISSIONS and banned("send_messages")) \
                or (name in MEDIA_PERMISSIONS and banned("send_media"))
            if not taken:
                allowed.add(name)
        return allowed

    def _banned_rights(self, allowed, current=None, until=None):
        """Telegram's "banned" flags for members who may do what `allowed` names, and nothing more of it.
        The flags for whole groups of permissions follow from those; the ones the app shows no
        permission for are kept from `current`, or, without it, go with stickers, as in Telegram's own apps."""
        flags = {BANNED_RIGHT_NAMES.get(name, name): name not in allowed for name in MEMBER_PERMISSIONS}
        flags["send_media"] = not any(name in allowed for name in MEDIA_PERMISSIONS)
        flags["send_messages"] = not any(name in allowed for name in SENDING_PERMISSIONS)
        for field in KEPT_BANNED_RIGHTS:
            if current is not None:
                flags[field] = getattr(current, field, None)
            elif field in ("send_games", "send_inline"):
                flags[field] = "send_stickers" not in allowed
        return types.ChatBannedRights(until_date=until, view_messages=False, **flags)

    async def _load_member_permissions_async(self, dialog_id):
        return self._allowed_by(await self._default_rights(dialog_id))

    async def _save_member_permissions_async(self, dialog_id, allowed):
        # Telegram's flags the app shows no permission for stay as they are now.
        current = await self._default_rights(dialog_id)
        await self.client(functions.messages.EditChatDefaultBannedRightsRequest(
            peer=self.entities[dialog_id], banned_rights=self._banned_rights(allowed, current)
        ))

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

    async def _revoke_invite_link_async(self, dialog_id, link):
        await self.client(functions.messages.EditExportedChatInviteRequest(
            peer=self.entities[dialog_id], link=link, revoked=True
        ))

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
                "is_bot": bool(getattr(user, "bot", False)),
                # Online, or when last seen, as far as the member lets it be known.
                "status": self._describe_status(getattr(user, "status", None)),
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
            values[SETTING_NAME_COLOR] = getattr(getattr(entity, "color", None), "color", None)
            values[SETTING_PROFILE_COLOR] = getattr(getattr(entity, "profile_color", None), "color", None)
            if entity.megagroup:
                values[SETTING_ANTISPAM] = bool(getattr(full, "antispam", False))
                values[SETTING_HIDE_MEMBERS] = bool(getattr(full, "participants_hidden", False))
                values[SETTING_SLOW_MODE] = getattr(full, "slowmode_seconds", None) or 0
                values[SETTING_HISTORY_HIDDEN] = bool(getattr(full, "hidden_prehistory", False))
                values[SETTING_JOIN_TO_SEND] = bool(getattr(entity, "join_to_send", False))
                values[SETTING_JOIN_REQUEST] = bool(getattr(entity, "join_request", False))
                values[SETTING_FORUM] = bool(getattr(entity, "forum", False))
            else:
                values[SETTING_SIGNATURES] = bool(getattr(entity, "signatures", False))
                values[SETTING_SIGNATURE_PROFILES] = bool(getattr(entity, "signature_profiles", False))
                values[SETTING_AUTOTRANSLATION] = bool(getattr(entity, "autotranslation", False))
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
            # A large group's own sticker set: whether it may be set, and which it is now.
            "can_set_stickers": bool(getattr(full, "can_set_stickers", False)),
            "stickers": getattr(getattr(full, "stickerset", None), "title", None),
            # A large group's own emoji pack, which needs boosts; Telegram says so if there are too few.
            "is_large_group": is_channel and bool(entity.megagroup),
            "emoji": getattr(getattr(full, "emojiset", None), "title", None),
            # Boosts belong to channels and large groups, and are shown to their admins.
            "has_boosts": is_channel and (is_owner or rights is not None),
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
            SETTING_ANTISPAM: lambda value: functions.channels.ToggleAntiSpamRequest(entity, value),
            SETTING_HIDE_MEMBERS: lambda value: functions.channels.ToggleParticipantsHiddenRequest(entity, value),
            SETTING_AUTOTRANSLATION: lambda value: functions.channels.ToggleAutotranslationRequest(entity, value),
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
        # The author's account goes with the signature: both are one switch to Telegram.
        if SETTING_SIGNATURES in changes or SETTING_SIGNATURE_PROFILES in changes:
            signatures = changes.pop(SETTING_SIGNATURES, None)
            profiles = changes.pop(SETTING_SIGNATURE_PROFILES, None)
            entity_now = await self.client.get_entity(entity)
            if signatures is None:
                signatures = bool(getattr(entity_now, "signatures", False))
            if profiles is None:
                profiles = bool(getattr(entity_now, "signature_profiles", False))
            await self.client(functions.channels.ToggleSignaturesRequest(
                entity, signatures_enabled=signatures, profiles_enabled=profiles and signatures
            ))
        # A colour keeps the emoji drawn behind it, which Telegram would otherwise drop.
        for name, field in ((SETTING_NAME_COLOR, "color"), (SETTING_PROFILE_COLOR, "profile_color")):
            if name in changes:
                color = changes.pop(name)
                entity_now = await self.client.get_entity(entity)
                emoji_id = getattr(getattr(entity_now, field, None), "background_emoji_id", None)
                await self.client(functions.channels.UpdateColorRequest(
                    entity, for_profile=name == SETTING_PROFILE_COLOR or None, color=color,
                    background_emoji_id=emoji_id if color is not None else None
                ))
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
            until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds) if seconds else None
            await self.client(functions.channels.EditBannedRequest(
                channel=entity, participant=user, banned_rights=self._banned_rights(rights, until=until)
            ))
        elif action == MEMBER_ACTION_DELETE_MESSAGES:
            await self.client(functions.channels.DeleteParticipantHistoryRequest(channel=entity, participant=user))
        elif action == MEMBER_ACTION_DEMOTE:
            await self.client.edit_admin(entity, user, is_admin=False)

    def _member_role(self, participant):
        if isinstance(participant, (types.ChannelParticipantCreator, types.ChatParticipantCreator)):
            return MEMBER_ROLE_OWNER
        if isinstance(participant, (types.ChannelParticipantAdmin, types.ChatParticipantAdmin)):
            return MEMBER_ROLE_ADMIN
        # Still a member, but with some permission taken away.
        if isinstance(participant, types.ChannelParticipantBanned) and not participant.left:
            return MEMBER_ROLE_RESTRICTED
        return None

    async def _pin_topic_async(self, dialog_id, topic_id, pinned):
        await self.client(functions.messages.UpdatePinnedForumTopicRequest(
            peer=self.entities[dialog_id], topic_id=topic_id, pinned=pinned
        ))

    async def _load_admins_async(self, dialog_id):
        admins = []
        for user in await self.client.get_participants(self.entities[dialog_id], filter=types.ChannelParticipantsAdmins):
            self.admin_entities[user.id] = get_input_peer(user)
            admins.append({"id": user.id, "name": get_display_name(user)})
        return admins

    async def _decide_all_requests_async(self, dialog_id, approved):
        await self.client(functions.messages.HideAllChatJoinRequestsRequest(peer=self.entities[dialog_id], approved=approved))

    async def _count_revoked_links_async(self, dialog_id):
        result = await self.client(functions.messages.GetExportedChatInvitesRequest(
            peer=self.entities[dialog_id], admin_id=types.InputUserSelf(), limit=INVITE_LINKS_LIMIT, revoked=True
        ))
        return getattr(result, "count", None) or len(getattr(result, "invites", []))

    async def _delete_revoked_links_async(self, dialog_id):
        await self.client(functions.messages.DeleteRevokedExportedChatInvitesRequest(
            peer=self.entities[dialog_id], admin_id=types.InputUserSelf()
        ))

    async def _set_group_stickers_async(self, dialog_id, set_id):
        sticker_set = types.InputStickerSetEmpty() if set_id is None else self.sticker_sets[set_id]
        await self.client(functions.channels.SetStickersRequest(channel=self.entities[dialog_id], stickerset=sticker_set))

    async def _load_emoji_sets_async(self):
        result = await self.client(functions.messages.GetEmojiStickersRequest(hash=0))
        self.emoji_sets = {
            emoji_set.id: types.InputStickerSetID(id=emoji_set.id, access_hash=emoji_set.access_hash)
            for emoji_set in result.sets
        }
        return [{"id": emoji_set.id, "title": emoji_set.title} for emoji_set in result.sets]

    async def _set_group_emoji_async(self, dialog_id, set_id):
        emoji_set = types.InputStickerSetEmpty() if set_id is None else self.emoji_sets[set_id]
        await self.client(functions.channels.SetEmojiStickersRequest(channel=self.entities[dialog_id], stickerset=emoji_set))

    async def _load_link_joiners_async(self, dialog_id, link):
        joiners = {}
        for name, requested in (("joined", None), ("waiting", True)):
            result = await self.client(functions.messages.GetChatInviteImportersRequest(
                peer=self.entities[dialog_id], link=link, requested=requested,
                offset_date=None, offset_user=types.InputUserEmpty(), limit=MEMBERS_LIMIT
            ))
            users = {user.id: user for user in result.users}
            joiners[name] = [
                get_display_name(users[importer.user_id]) for importer in result.importers if importer.user_id in users
            ]
        return joiners

    async def _report_not_spam_async(self, dialog_id, message_id):
        await self.client(functions.channels.ReportAntiSpamFalsePositiveRequest(
            channel=self.entities[dialog_id], msg_id=message_id
        ))

    async def _load_boosts_async(self, dialog_id):
        status = await self.client(functions.premium.GetBoostsStatusRequest(peer=self.entities[dialog_id]))
        return {
            "level": status.level, "boosts": status.boosts,
            "next": getattr(status, "next_level_boosts", None), "link": getattr(status, "boost_url", None) or EMPTY_STRING,
        }

    async def _load_admin_log_async(self, dialog_id, kinds=(), admin_id=None):
        events = []
        narrowed = {kind: True for kind in kinds}
        if admin_id is not None:
            narrowed["admins"] = [self.admin_entities[admin_id]]
        async for event in self.client.iter_admin_log(self.entities[dialog_id], limit=ADMIN_LOG_LIMIT, **narrowed):
            # A deleted message is kept in the log, and anti-spam's mistakes can be reported from there.
            deleted = getattr(event.action, "message", None) if isinstance(
                event.action, types.ChannelAdminLogEventActionDeleteMessage
            ) else None
            events.append({
                "user": get_display_name(event.user) if event.user else EMPTY_STRING,
                "date": event.date,
                "message_id": getattr(deleted, "id", None),
                "text": getattr(deleted, "message", None) or EMPTY_STRING,
                "by_antispam": getattr(event, "user_id", None) == ANTISPAM_USER_ID,
                # E.g. "ChannelAdminLogEventActionParticipantInvite" -> "ParticipantInvite".
                "action": type(event.action).__name__.replace(ADMIN_LOG_ACTION_PREFIX, EMPTY_STRING),
            })
        return events
