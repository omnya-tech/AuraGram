"""Messages: loading them, writing, editing, deleting, forwarding, reacting, polls, searching, and putting each one into words.

Part of TelegramManager (core.telegram_client): its methods run as that thread's, on its event loop."""
from telethon.errors import FloodWaitError, MessageNotModifiedError, RPCError
from telethon.tl import functions, types
from telethon.utils import get_display_name, get_input_peer, get_peer_id
from core.constants import (
    SERVICE_GROUP_CREATE_FORMAT_KEY, SERVICE_KEYS, SERVICE_JOINED_KEY, SERVICE_ADDED_FORMAT_KEY,
    SERVICE_LEFT_KEY, SERVICE_REMOVED_FORMAT_KEY, SERVICE_CALL_STARTED_KEY, SERVICE_CALL_ENDED_KEY,
    MEDIA_SERVICE_KEY, EMPTY_STRING, MESSAGES_LIMIT, MEDIA_KINDS, CHAT_EXPORT_LIMIT, CHAT_EXPORT_PAGE,
    MESSAGE_VIEW_SCHEDULED, GLOBAL_SEARCH_LIMIT, MAP_LINK_FORMAT, TOPICS_LIMIT, AUDIENCE_LIMIT,
    MESSAGE_VIEW_COMMENTS, MESSAGE_VIEW_MENTIONS, VOTERS_PAGE, VOTERS_LIMIT,
)
from core.tg_shared import MESSAGE_VIEW_FILTERS


class MessagesMixin:
    def load_messages(self, dialog_id, on_result, before_id=None, mark_read=True):
        """Loads the latest page of a chat, or the page before message `before_id`."""
        self._request(on_result, self._load_messages_async, dialog_id, before_id, mark_read)

    def translate(self, dialog_id, message_id, on_result):
        """The result is the message's text in the interface language."""
        self._request(on_result, self._translate_async, dialog_id, message_id)

    def load_message_link(self, dialog_id, message_id, on_result):
        """The web address of a message in a channel or large group."""
        self._request(on_result, self._load_message_link_async, dialog_id, message_id)

    def load_message_view(self, dialog_id, view, on_result):
        """Loads one of the MESSAGE_VIEW_* lists of a chat: pinned, scheduled, or one kind of shared media."""
        self._request(on_result, self._load_message_view_async, dialog_id, view)

    def delete_scheduled(self, dialog_id, message_id, on_result):
        """Cancels a scheduled message before it is sent."""
        self._request(on_result, self._delete_scheduled_async, dialog_id, message_id)

    def vote(self, dialog_id, message_id, option_indexes, on_result):
        """Votes in a poll (an empty list retracts the vote); the result is the refreshed message."""
        self._request(on_result, self._vote_async, dialog_id, message_id, option_indexes)

    def send_poll(self, dialog_id, question, options, on_result, reply_to=None, settings=None):
        """`settings`: {"anonymous", "multiple", "quiz_answer" (index of the right option, or None),
        "explanation"}; None for an anonymous poll with one answer."""
        self._request(on_result, self._send_poll_async, dialog_id, question, options, reply_to, settings)

    def load_poll_voters(self, dialog_id, message_id, on_result):
        """The result is [(option text, [names of who chose it])], in the poll's own order. Only a poll
        whose votes are public has them; Telegram may ask this account to vote first."""
        self._request(on_result, self._load_poll_voters_async, dialog_id, message_id)

    def close_poll(self, dialog_id, message_id, on_result):
        """Stop a poll taking votes, for good; the result is the message as it is then."""
        self._request(on_result, self._close_poll_async, dialog_id, message_id)

    def react(self, dialog_id, message_id, emoji, on_result):
        """Sets this account's reaction (None removes it); the result is the refreshed message."""
        self._request(on_result, self._react_async, dialog_id, message_id, emoji)

    def forward_message(self, from_dialog_id, message_id, to_dialog_id, on_result):
        """Forwards a message, or a list of message ids, to another chat."""
        self._request(on_result, self._forward_message_async, from_dialog_id, message_id, to_dialog_id)

    def set_pinned(self, dialog_id, message_id, pinned, on_result):
        self._request(on_result, self._set_pinned_async, dialog_id, message_id, pinned)

    def send_message(self, dialog_id, text, on_result, reply_to=None, schedule=None, silent=False):
        """`schedule` is a datetime to deliver the message at, instead of now;
        `silent` delivers it without the sound of a notification on the other side."""
        self._request(on_result, self._send_message_async, dialog_id, text, reply_to, schedule, silent)

    def load_thread(self, dialog_id, thread_id, view, on_result):
        """The comments under a channel post (view MESSAGE_VIEW_COMMENTS) or the messages of a forum topic.

        The result is {"peer", "root", "messages"}: the chat those messages live in and the message
        they all answer, which is where anything written into the thread has to go. For a topic that
        is the group and the topic itself; comments live in the channel's discussion group.
        """
        self._request(on_result, self._load_thread_async, dialog_id, thread_id, view)

    def load_topics(self, dialog_id, on_result):
        """The result is a forum group's topics as [{"id", "title", "unread"}]."""
        self._request(on_result, self._load_topics_async, dialog_id)

    def load_audience(self, dialog_id, message_id, on_result):
        """Who read a message and who reacted to it. The result is {"readers": names, or None where
        Telegram does not tell, "reactions": [(name, emoji), ...]}."""
        self._request(on_result, self._load_audience_async, dialog_id, message_id)

    def edit_message(self, dialog_id, message_id, text, on_result):
        self._request(on_result, self._edit_message_async, dialog_id, message_id, text)

    def delete_message(self, dialog_id, message_id, on_result, for_everyone=True):
        """Deletes a message, or a list of message ids: for everyone in the chat, or from this account's side only."""
        self._request(on_result, self._delete_message_async, dialog_id, message_id, for_everyone)

    def report(self, dialog_id, message_ids, option, comment, on_result):
        """One step of reporting messages to Telegram, which asks its questions one at a time.

        Start with option b"". The result is {"done": True}, or {"title", "options": [(text, option), ...]}
        to choose from and call again with, or {"comment": option} to call again with a comment added.
        """
        self._request(on_result, self._report_async, dialog_id, message_ids, option, comment)

    def load_messages_around(self, dialog_id, message_id, on_result):
        """A page of the conversation with that message in the middle of it, oldest first."""
        self._request(on_result, self._load_messages_around_async, dialog_id, message_id)

    def load_messages_from(self, dialog_id, date, on_result):
        """The first page of the conversation from a day onwards, oldest first."""
        self._request(on_result, self._load_messages_from_async, dialog_id, date)

    def search_all(self, query, on_result):
        """Look through the messages of every chat. The result is [{"chat", "message"}], newest first."""
        self._request(on_result, self._search_all_async, query)

    def export_messages(self, dialog_id, on_result, on_progress=None):
        """Every message of a chat, as far back as CHAT_EXPORT_LIMIT, oldest first.
        on_progress(count) is called from this thread as each batch of them comes in."""
        self._request(on_result, self._export_messages_async, dialog_id, on_progress)

    def search_messages(self, dialog_id, query, on_result):
        """Finds the latest messages of a chat that contain `query`."""
        self._request(on_result, self._search_messages_async, dialog_id, query)

    async def _forward_message_async(self, from_dialog_id, message_id, to_dialog_id):
        await self.client.forward_messages(
            self.entities[to_dialog_id], message_id, self.entities[from_dialog_id]
        )

    async def _translate_async(self, dialog_id, message_id):
        result = await self.client(functions.messages.TranslateTextRequest(
            to_lang=self.translate_lang, peer=self.entities[dialog_id], id=[message_id]
        ))
        return result.result[0].text

    async def _load_message_link_async(self, dialog_id, message_id):
        result = await self.client(functions.channels.ExportMessageLinkRequest(
            channel=self.entities[dialog_id], id=message_id
        ))
        return result.link

    async def _set_pinned_async(self, dialog_id, message_id, pinned):
        entity = self.entities[dialog_id]
        if pinned:
            await self.client.pin_message(entity, message_id, notify=False)
        else:
            await self.client.unpin_message(entity, message_id)

    async def _load_messages_async(self, dialog_id, before_id, mark_read):
        entity = self.entities[dialog_id]
        messages = await self.client.get_messages(entity, limit=MESSAGES_LIMIT, max_id=before_id or 0)
        if before_id is None:
            self.read_outbox[dialog_id] = await self._load_read_outbox_async(entity)
        if before_id is None and mark_read:
            await self._mark_read_async(dialog_id)
        # Telegram returns newest first; the UI reads oldest first.
        return [self._describe_message(message, message.sender) for message in reversed(messages)]

    async def _load_read_outbox_async(self, entity):
        """Id of the newest message of ours that was read in this chat; None if Telegram does not say."""
        result = await self.client(functions.messages.GetPeerDialogsRequest(peers=[types.InputDialogPeer(entity)]))
        try:
            return result.dialogs[0].read_outbox_max_id
        except (AttributeError, IndexError):
            return None

    async def _edit_message_async(self, dialog_id, message_id, text):
        try:
            await self.client.edit_message(self.entities[dialog_id], message_id, text)
        except MessageNotModifiedError:
            # Saving the same text again is not a failure.
            pass

    async def _delete_message_async(self, dialog_id, message_id, for_everyone):
        message_ids = message_id if isinstance(message_id, list) else [message_id]
        await self.client.delete_messages(self.entities[dialog_id], message_ids, revoke=for_everyone)

    async def _report_async(self, dialog_id, message_ids, option, comment):
        result = await self.client(functions.messages.ReportRequest(
            peer=self.entities[dialog_id], id=message_ids, option=option, message=comment
        ))
        if isinstance(result, types.ReportResultChooseOption):
            return {"title": result.title, "options": [(choice.text, choice.option) for choice in result.options]}
        if isinstance(result, types.ReportResultAddComment):
            return {"comment": result.option}
        return {"done": True}

    async def _load_messages_around_async(self, dialog_id, message_id):
        messages = await self.client.get_messages(
            self.entities[dialog_id], limit=MESSAGES_LIMIT, offset_id=message_id, add_offset=-(MESSAGES_LIMIT // 2)
        )
        return [
            self._describe_message(message, message.sender)
            for message in sorted(messages, key=lambda message: message.id)
        ]

    async def _load_messages_from_async(self, dialog_id, date):
        messages = await self.client.get_messages(
            self.entities[dialog_id], limit=MESSAGES_LIMIT, offset_date=date, reverse=True
        )
        return [self._describe_message(message, message.sender) for message in messages]

    async def _search_all_async(self, query):
        messages = await self.client.get_messages(None, limit=GLOBAL_SEARCH_LIMIT, search=query)
        return [
            {"chat": self._remember_chat(message.chat), "message": self._describe_message(message, message.sender)}
            # A hit in a chat Telegram sent no details of cannot be opened from here.
            for message in messages if getattr(message, "chat", None) is not None
        ]

    async def _search_messages_async(self, dialog_id, query):
        messages = await self.client.get_messages(
            self.entities[dialog_id], limit=MESSAGES_LIMIT, search=query
        )
        return [self._describe_message(message, message.sender) for message in reversed(messages)]

    async def _export_messages_async(self, dialog_id, on_progress):
        entity = self.entities[dialog_id]
        found = []
        oldest = 0
        while len(found) < CHAT_EXPORT_LIMIT:
            page = await self.client.get_messages(entity, limit=CHAT_EXPORT_PAGE, max_id=oldest)
            if not page:
                break
            found.extend(self._describe_message(message, message.sender) for message in page)
            oldest = page[-1].id
            if on_progress is not None:
                on_progress(len(found))
            if len(page) < CHAT_EXPORT_PAGE:
                break
        # Telegram gives the newest first; a file is read from the start.
        return list(reversed(found))

    def _describe_message(self, message, sender):
        return {
            "id": message.id,
            "sender": get_display_name(sender) if sender else EMPTY_STRING,
            # Set when a person wrote it, and so can be written to; None for a channel or a group writing as itself.
            "sender_id": sender.id if isinstance(sender, types.User) else None,
            "text": message.message or EMPTY_STRING,
            # Words for an attachment that has no text of its own: a sticker's emoji, a contact's name and number.
            "detail": self._describe_detail(message),
            # For a message from Telegram itself: (locale key, its fields), what happened; None otherwise.
            "service": self._describe_service(message, sender),
            # What an attached file is: {"name", "size", "duration"}; None for a message without one.
            "file": self._describe_file(message),
            "media": self._describe_media(message),
            "date": message.date,
            "outgoing": message.out,
            "pinned": bool(getattr(message, "pinned", False)),
            "reply_to": getattr(message, "reply_to_msg_id", None),
            # The topic or post this message sits under: the top of its chain of replies.
            "thread_id": getattr(getattr(message, "reply_to", None), "reply_to_top_id", None)
            or getattr(message, "reply_to_msg_id", None),
            "reactions": self._describe_reactions(message),
            "poll": self._describe_poll(message),
            "buttons": [button.text for row in getattr(message, "buttons", None) or [] for button in row],
            "links": self._describe_links(message),
            # How many comments a channel post has; None for anything that takes no comments.
            "comments": self._count_comments(message),
            # Changed by its author after sending. Telegram also stamps a post when its reactions change; that is not an edit.
            "edited": bool(getattr(message, "edit_date", None)) and not getattr(message, "edit_hide", False),
            # Whose message this was before it was passed on: a name, "" if hidden, None if not forwarded.
            "forwarded_from": self._describe_forward(message),
            "views": getattr(message, "views", None) if getattr(message, "post", False) else None,
            "forwards": getattr(message, "forwards", None) if getattr(message, "post", False) else None,
            "read": self._is_read(message),
        }

    def _describe_forward(self, message):
        forward = getattr(message, "forward", None)
        if forward is None:
            return None
        origin = getattr(forward, "sender", None) or getattr(forward, "chat", None)
        return getattr(forward, "from_name", None) or (get_display_name(origin) if origin else EMPTY_STRING)

    def _count_comments(self, message):
        replies = getattr(message, "replies", None)
        return replies.replies if replies is not None and getattr(replies, "comments", False) else None

    def _describe_file(self, message):
        attached = getattr(message, "file", None)
        if attached is None or getattr(message, "sticker", None):
            return None
        return {
            "name": getattr(attached, "name", None) or EMPTY_STRING,
            "size": getattr(attached, "size", None) or 0,
            # Seconds, for sound and video.
            "duration": getattr(attached, "duration", None) or 0,
        }

    def _describe_service(self, message, sender):
        """What a message from Telegram itself says happened, as (locale key, fields); None for any other message."""
        action = getattr(message, "action", None)
        if action is None:
            return None
        kind = type(action).__name__
        title = getattr(action, "title", None) or EMPTY_STRING
        # Those the action names: who was added or removed.
        names = [get_display_name(entity) for entity in getattr(message, "action_entities", None) or []]
        sender_id = getattr(sender, "id", None)
        if kind == "MessageActionChatAddUser":
            others = [name for entity, name in zip(message.action_entities or [], names) if entity.id != sender_id]
            return (SERVICE_ADDED_FORMAT_KEY, {"names": others}) if others else (SERVICE_JOINED_KEY, {})
        if kind == "MessageActionChatDeleteUser":
            if getattr(action, "user_id", None) == sender_id:
                return SERVICE_LEFT_KEY, {}
            return SERVICE_REMOVED_FORMAT_KEY, {"names": names}
        if kind == "MessageActionGroupCall":
            return (SERVICE_CALL_ENDED_KEY if getattr(action, "duration", None) else SERVICE_CALL_STARTED_KEY), {}
        if kind == "MessageActionChannelCreate" and getattr(getattr(message, "chat", None), "megagroup", False):
            # Telegram makes a large group the way it makes a channel, and says so the same way.
            return SERVICE_GROUP_CREATE_FORMAT_KEY, {"title": title}
        if kind in SERVICE_KEYS:
            return SERVICE_KEYS[kind], {"title": title}
        return MEDIA_SERVICE_KEY, {}

    def _describe_detail(self, message):
        contact = getattr(message, "contact", None)
        if contact:
            return " ".join(filter(None, [contact.first_name, contact.last_name, contact.phone_number]))
        geo = getattr(message, "geo", None)
        if geo:
            return "%s, %s" % (geo.lat, geo.long)
        if getattr(message, "sticker", None):
            return self._sticker_emoji(message.sticker)
        return EMPTY_STRING

    def _describe_links(self, message):
        """Every address a message points to: written out, hidden behind words, or an @mention."""
        get_entities_text = getattr(message, "get_entities_text", None)
        links = []
        for entity, text in get_entities_text() if get_entities_text else []:
            if isinstance(entity, types.MessageEntityTextUrl):
                links.append(entity.url)
            elif isinstance(entity, types.MessageEntityUrl):
                links.append(text)
            elif isinstance(entity, types.MessageEntityMention):
                links.append("https://t.me/" + text.lstrip("@"))
        geo = getattr(message, "geo", None)
        if geo:
            # A place has no address of its own; a map of it is the nearest thing to open.
            links.append(MAP_LINK_FORMAT.format(latitude=geo.lat, longitude=geo.long))
        return links

    def _is_read(self, message):
        """Whether a message of ours was read by the other side; None where that is not known
        or means nothing (someone else's message, a channel post)."""
        read_up_to = self.read_outbox.get(getattr(message, "chat_id", None))
        # What Telegram itself says happened is nobody's to read.
        if read_up_to is None or not message.out or getattr(message, "post", False) or getattr(message, "action", None):
            return None
        return message.id <= read_up_to

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

    async def _send_message_async(self, dialog_id, text, reply_to, schedule, silent):
        """The result is the id of the message sent, for what is sent as a reply to it."""
        sent = await self.client.send_message(
            # None, not False: unasked, the chat's own setting for this decides.
            self.entities[dialog_id], text, reply_to=reply_to, schedule=schedule, silent=silent or None
        )
        return getattr(sent, "id", None)

    async def _load_thread_async(self, dialog_id, thread_id, view):
        peer, root = dialog_id, thread_id
        if view == MESSAGE_VIEW_COMMENTS:
            # The post has a twin in the discussion group, and the comments are the answers to that twin.
            discussion = await self.client(functions.messages.GetDiscussionMessageRequest(
                peer=self.entities[dialog_id], msg_id=thread_id
            ))
            twin = discussion.messages[0]
            peer, root = get_peer_id(twin.peer_id), twin.id
            for chat in discussion.chats:
                self.entities.setdefault(get_peer_id(chat), get_input_peer(chat))
        messages = await self.client.get_messages(self.entities[peer], limit=MESSAGES_LIMIT, reply_to=root)
        return {
            "peer": peer, "root": root,
            "messages": [self._describe_message(message, message.sender) for message in reversed(messages)],
        }

    async def _load_topics_async(self, dialog_id):
        result = await self.client(functions.messages.GetForumTopicsRequest(
            peer=self.entities[dialog_id], offset_date=None, offset_id=0, offset_topic=0, limit=TOPICS_LIMIT
        ))
        return [
            {
                "id": topic.id, "title": topic.title, "unread": getattr(topic, "unread_count", 0),
                "closed": bool(getattr(topic, "closed", False)),
                "pinned": bool(getattr(topic, "pinned", False)),
            }
            # A deleted topic is still listed, as a bare id with no title.
            for topic in result.topics if getattr(topic, "title", None)
        ]

    async def _load_audience_async(self, dialog_id, message_id):
        entity = self.entities[dialog_id]
        try:
            result = await self.client(functions.messages.GetMessageReactionsListRequest(
                peer=entity, id=message_id, limit=AUDIENCE_LIMIT
            ))
        except FloodWaitError:
            raise
        except RPCError:
            # Channels do not tell who reacted, only how many.
            result = None
        names = {
            get_peer_id(reactor): get_display_name(reactor)
            for reactor in list(getattr(result, "users", [])) + list(getattr(result, "chats", []))
        }
        reactions = [
            (names.get(get_peer_id(reaction.peer_id), EMPTY_STRING), reaction.reaction.emoticon)
            for reaction in getattr(result, "reactions", [])
            if isinstance(reaction.reaction, types.ReactionEmoji)
        ]
        try:
            read = await self.client(functions.messages.GetMessageReadParticipantsRequest(peer=entity, msg_id=message_id))
            readers = []
            for reader in read or []:
                try:
                    readers.append(get_display_name(await self.client.get_entity(reader.user_id)))
                except ValueError:
                    # Someone this session has never seen: counted by Telegram, but nameless here.
                    pass
        except FloodWaitError:
            raise
        except RPCError:
            # Only for this account's own recent messages in small groups.
            readers = None
        return {"readers": readers, "reactions": reactions}

    async def _load_message_view_async(self, dialog_id, view):
        entity = self.entities[dialog_id]
        if view == MESSAGE_VIEW_SCHEDULED:
            messages = await self.client.get_messages(entity, scheduled=True)
        else:
            messages = await self.client.get_messages(
                entity, limit=MESSAGES_LIMIT, filter=MESSAGE_VIEW_FILTERS[view]
            )
        if view == MESSAGE_VIEW_MENTIONS:
            # Seen now. Best effort: the list is what was asked for.
            try:
                await self.client(functions.messages.ReadMentionsRequest(peer=entity))
            except Exception:
                pass
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
        solution = getattr(results, "solution", None)
        return {
            # Newer Telegram layers wrap these texts in a formatted-text object.
            "question": getattr(poll.question, "text", poll.question),
            "options": [
                {
                    "text": getattr(answer.text, "text", answer.text),
                    # None while Telegram hides the results (before voting).
                    "voters": getattr(votes.get(answer.option), "voters", None),
                    "chosen": bool(getattr(votes.get(answer.option), "chosen", False)),
                    # A quiz's right answer, once Telegram shows it (after voting).
                    "correct": bool(getattr(votes.get(answer.option), "correct", False)),
                }
                for answer in poll.answers
            ],
            # How many people voted, which the shares are of; None while the results are hidden.
            "total": getattr(results, "total_voters", None),
            "closed": bool(poll.closed),
            "multiple": bool(poll.multiple_choice),
            # Whether who voted for what can be seen; never in an anonymous poll.
            "public": bool(getattr(poll, "public_voters", False)),
            "quiz": bool(getattr(poll, "quiz", False)),
            # What explains a quiz's right answer, shown once it has been answered; "" if none.
            "explanation": solution or "",
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

    async def _load_poll_voters_async(self, dialog_id, message_id):
        entity = self.entities[dialog_id]
        message = await self.client.get_messages(entity, ids=message_id)
        answers = message.poll.poll.answers
        chose = {answer.option: [] for answer in answers}
        offset, seen = None, 0
        while seen < VOTERS_LIMIT:
            page = await self.client(functions.messages.GetPollVotesRequest(
                peer=entity, id=message_id, limit=VOTERS_PAGE, offset=offset
            ))
            names = {get_peer_id(who): get_display_name(who) for who in list(page.users) + list(page.chats)}
            for vote in page.votes:
                name = names.get(get_peer_id(vote.peer), EMPTY_STRING)
                # One option, or several where the poll lets more than one be chosen.
                for option in getattr(vote, "options", None) or [getattr(vote, "option", None)]:
                    if option in chose:
                        chose[option].append(name)
            seen += len(page.votes)
            offset = page.next_offset
            if not offset or not page.votes:
                break
        return [(getattr(answer.text, "text", answer.text), chose[answer.option]) for answer in answers]

    async def _close_poll_async(self, dialog_id, message_id):
        entity = self.entities[dialog_id]
        message = await self.client.get_messages(entity, ids=message_id)
        poll = message.poll.poll
        poll.closed = True
        await self.client(functions.messages.EditMessageRequest(
            peer=entity, id=message_id, media=types.InputMediaPoll(poll=poll)
        ))
        message = await self.client.get_messages(entity, ids=message_id)
        return self._describe_message(message, message.sender)

    async def _send_poll_async(self, dialog_id, question, options, reply_to, settings=None):
        settings = settings or {}
        quiz_answer = settings.get("quiz_answer")
        explanation = settings.get("explanation") or None

        def formatted(text):
            return types.TextWithEntities(text, [])
        poll = types.Poll(
            id=0, hash=0, question=formatted(question),
            answers=[types.PollAnswer(formatted(text), bytes([index])) for index, text in enumerate(options)],
            public_voters=not settings.get("anonymous", True) or None,
            multiple_choice=bool(settings.get("multiple")) or None,
            quiz=quiz_answer is not None or None,
            shuffle_answers=bool(settings.get("shuffle")) or None,
            hide_results_until_close=bool(settings.get("hide_results")) or None,
            revoting_disabled=bool(settings.get("no_revote")) or None,
            close_period=settings.get("close_after") or None,
        )
        media = types.InputMediaPoll(
            poll, correct_answers=[bytes([quiz_answer])] if quiz_answer is not None else None,
            solution=explanation, solution_entities=[] if explanation else None,
        )
        await self.client.send_message(self.entities[dialog_id], file=media, reply_to=reply_to)

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
