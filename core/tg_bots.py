"""Bots and buttons: pressing a message's buttons, inline bots, starting a bot and its commands, and writing as a channel.

Part of TelegramManager (core.telegram_client): its methods run as that thread's, on its event loop."""
from telethon.errors import RPCError, BotResponseTimeoutError
from telethon.tl import functions, types
from core.constants import BUTTON_NEEDS_PHONE, BUTTON_NEEDS_LOCATION, BOT_START_COMMAND, EMPTY_STRING


class BotsMixin:
    def press_button(self, dialog_id, message_id, index, on_result, share_phone=False, share_location=None):
        """Press the index-th button under a bot's message. The result is {"url", "answer", "needs"}:
        a link the button wants opened, or what it needs first (BUTTON_NEEDS_*) - in both cases nothing was
        pressed yet - or what the bot answered, if anything. `share_phone` and `share_location` (latitude,
        longitude) are the user's yes to a button that asks for them."""
        self._request(on_result, self._press_button_async, dialog_id, message_id, index, share_phone, share_location)

    def inline_query(self, dialog_id, username, query, on_result):
        """Ask a bot that answers from any chat (@gif, @vid...) for what it has for `query`. The result is
        [{"title", "description", "kind"}], or None if `username` is nobody who answers that way."""
        self._request(on_result, self._inline_query_async, dialog_id, username, query)

    def send_inline_result(self, dialog_id, index, on_result, reply_to=None):
        """Send the index-th of what inline_query found, in the chat it was asked for."""
        self._request(on_result, self._send_inline_result_async, dialog_id, index, reply_to)

    def start_bot(self, dialog_id, on_result, start_param=None):
        """Start a bot, with what a link to it carried after ?start= if it had anything."""
        self._request(on_result, self._start_bot_async, dialog_id, start_param)

    def load_bot_commands(self, dialog_id, on_result):
        """The result is [{"command", "description"}] for the bots of a chat: the bot itself, or a group's bots."""
        self._request(on_result, self._load_bot_commands_async, dialog_id)

    def load_send_as(self, dialog_id, on_result):
        """Who this account may write as in a group, shaped like chats; empty where only itself."""
        self._request(on_result, self._load_send_as_async, dialog_id)

    def set_send_as(self, dialog_id, sender_id, on_result):
        self._request(on_result, self._set_send_as_async, dialog_id, sender_id)

    async def _load_send_as_async(self, dialog_id):
        result = await self.client(functions.channels.GetSendAsRequest(peer=self.entities[dialog_id]))
        return [self._remember_chat(sender) for sender in list(result.chats) + list(result.users)]

    async def _set_send_as_async(self, dialog_id, sender_id):
        await self.client(functions.messages.SaveDefaultSendAsRequest(
            peer=self.entities[dialog_id], send_as=self.entities[sender_id]
        ))

    async def _press_button_async(self, dialog_id, message_id, index, share_phone=False, share_location=None):
        message = await self.client.get_messages(self.entities[dialog_id], ids=message_id)
        button = [button for row in message.buttons or [] for button in row][index]
        url = getattr(button, "url", None)
        if url:
            # Left to the UI: a link from a bot is opened only once the user has seen where it goes.
            return {"url": url, "answer": None, "needs": None}
        kind = getattr(getattr(button, "button", None), "type", None)
        # Your number or where you are goes to the bot only once you have said yes to it.
        if isinstance(kind, types.ButtonTypeRequestPhone) and not share_phone:
            return {"url": None, "answer": None, "needs": BUTTON_NEEDS_PHONE}
        if isinstance(kind, types.ButtonTypeRequestGeoLocation) and share_location is None:
            return {"url": None, "answer": None, "needs": BUTTON_NEEDS_LOCATION}
        shared = {}
        if share_phone:
            shared["share_phone"] = True
        if share_location is not None:
            # Telethon takes the place the other way round: longitude first.
            latitude, longitude = share_location
            shared["share_geo"] = (longitude, latitude)
        try:
            result = await button.click(**shared)
        except BotResponseTimeoutError:
            # The press went through; the bot just never answered it.
            result = None
        is_answer = isinstance(result, types.messages.BotCallbackAnswer)
        return {"url": None, "answer": result.message if is_answer else None, "needs": None}

    async def _inline_query_async(self, dialog_id, username, query):
        try:
            bot = await self.client.get_entity(username)
        except (ValueError, TypeError, RPCError):
            return None
        # Only bots that answer in any chat have something to say here; anyone else is a mention.
        if not isinstance(bot, types.User) or not bot.bot or not getattr(bot, "bot_inline_placeholder", None):
            return None
        self.inline_results = await self.client.inline_query(bot, query, entity=self.entities[dialog_id])
        return [
            {
                "title": getattr(result, "title", None) or EMPTY_STRING,
                "description": getattr(result, "description", None) or EMPTY_STRING,
                "kind": getattr(result, "type", None) or EMPTY_STRING,
            }
            for result in self.inline_results
        ]

    async def _send_inline_result_async(self, dialog_id, index, reply_to):
        await self.inline_results[index].click(self.entities[dialog_id], reply_to=reply_to)

    async def _start_bot_async(self, dialog_id, start_param):
        entity = self.entities[dialog_id]
        if start_param:
            await self.client(functions.messages.StartBotRequest(
                bot=entity, peer=entity, start_param=start_param
            ))
        else:
            # What Telegram's own Start button sends when the link carried nothing.
            await self.client.send_message(entity, BOT_START_COMMAND)

    async def _load_bot_commands_async(self, dialog_id):
        entity = await self.client.get_entity(self.entities[dialog_id])
        if isinstance(entity, types.User):
            full = await self.client(functions.users.GetFullUserRequest(entity))
            infos, in_group = [getattr(full.full_user, "bot_info", None)], False
        else:
            if isinstance(entity, types.Channel):
                full = await self.client(functions.channels.GetFullChannelRequest(entity))
            else:
                full = await self.client(functions.messages.GetFullChatRequest(entity.id))
            infos, in_group = list(getattr(full.full_chat, "bot_info", None) or []), True
        usernames = {user.id: getattr(user, "username", None) for user in getattr(full, "users", [])}
        commands = []
        for info in infos:
            for command in getattr(info, "commands", None) or []:
                # In a group, the bot's name goes after the command, so the right bot takes it.
                bot = usernames.get(getattr(info, "user_id", None)) if in_group else None
                commands.append({
                    "command": "/" + command.command + ("@" + bot if bot else EMPTY_STRING),
                    "description": command.description,
                })
        return commands
