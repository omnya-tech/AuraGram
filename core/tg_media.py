"""Files going up and coming down, sounds played as they arrive, stickers, contacts and places sent, and stories.

Part of TelegramManager (core.telegram_client): its methods run as that thread's, on its event loop."""
import os
from telethon.tl import functions, types
from telethon.utils import get_display_name, get_input_peer, get_peer_id
from core.constants import (
    STREAM_REQUEST_BYTES, EMPTY_STRING, DOWNLOADS_DIR, CHAT_FILES_LIMIT, DOWNLOADABLE_MEDIA, STORY_AUDIENCES,
    STORY_SECONDS,
)
from core.tg_shared import PhoneHiddenError, CHAT_FILE_FILTERS


class MediaMixin:
    def load_stories(self, on_result):
        """The result is [{"peer_id", "name", "stories": [{"id", "caption", "media", "date"}]}]."""
        self._request(on_result, self._load_stories_async)

    def open_story(self, peer_id, story_id, on_result):
        """Download a story listed by load_stories and count it as seen; the result is the file's path."""
        self._request(on_result, self._open_story_async, peer_id, story_id)

    def stream_media(self, dialog_id, message_id, buffer, on_result):
        """Hand a message's sound to `buffer` piece by piece as it comes from Telegram, for playing
        while the rest is still on its way. Returns the request, to cancel when the listening stops."""
        return self._request(on_result, self._stream_media_async, dialog_id, message_id, buffer)

    def fetch_media(self, dialog_id, message_id, on_result, on_progress=None):
        """The message's media as bytes, held in memory only: nothing is written to the disk."""
        self._request(on_result, self._fetch_media_async, dialog_id, message_id, self._percent_reporter(on_progress))

    def download_media(self, dialog_id, message_id, on_result, folder=None, on_progress=None):
        """Saves the message's media to `folder` (the downloads folder by default); the result is the file path.
        on_progress(percent) is called from this thread as the file comes in."""
        self._request(
            on_result, self._download_media_async, dialog_id, message_id, folder or DOWNLOADS_DIR,
            self._percent_reporter(on_progress)
        )

    def _percent_reporter(self, on_progress):
        """Turn Telethon's "bytes so far, bytes in all" into whole percents, each reported once."""
        if on_progress is None:
            return None
        last = [None]

        def report(done, total):
            percent = int(done * 100 / total) if total else 0
            if percent != last[0]:
                last[0] = percent
                on_progress(percent)
        return report

    def post_story(self, path, caption, audience, on_result, on_progress=None):
        """Post a picture as this account's story; `audience` is one of STORY_AUDIENCES."""
        self._request(on_result, self._post_story_async, path, caption, audience, self._percent_reporter(on_progress))

    def send_file(self, dialog_id, path, on_result, voice_note=False, on_progress=None, reply_to=None):
        self._request(
            on_result, self._send_file_async, dialog_id, path, voice_note, self._percent_reporter(on_progress), reply_to
        )

    def send_files(self, dialog_id, paths, caption, as_documents, on_result, reply_to=None, on_progress=None):
        """Send one or more files as one message; several pictures or videos become an album.
        on_progress(progress) is called from this thread as the files go up, with progress
        {"percent", "done", "total", "file", "files"}: bytes up and in all over every file,
        and which file of how many is on its way (counted from 1). Returns what cancels the sending."""
        return self._request(
            on_result, self._send_files_async, dialog_id, paths, caption, as_documents, reply_to,
            self._upload_reporter(on_progress, paths)
        )

    def _upload_reporter(self, on_progress, paths):
        """Turn Telethon's "bytes so far of this file" into the progress of all the files together,
        each whole percent reported once. Telethon sends the files of an album one after another,
        in the order given: a report after one file is whole, or a count that drops, is the next file's."""
        if on_progress is None:
            return None
        sizes = [os.path.getsize(path) if os.path.isfile(path) else 0 for path in paths]
        state = {"file": 0, "last": (0, 0), "percent": None}

        def report(done, total):
            last_done, last_total = state["last"]
            finished = last_total and last_done >= last_total and (done, total) != state["last"]
            if (finished or done < last_done) and state["file"] + 1 < len(sizes):
                state["file"] += 1
            state["last"] = (done, total)
            index = state["file"]
            # Telethon knows the size of the file it is sending better than the disk did a moment ago.
            sizes[index] = total or sizes[index]
            everything = sum(sizes)
            sent = sum(sizes[:index]) + min(done, sizes[index])
            percent = int(sent * 100 / everything) if everything else 0
            if percent != state["percent"]:
                state["percent"] = percent
                on_progress({"percent": percent, "done": sent, "total": everything, "file": index + 1, "files": len(sizes)})
        return report

    def load_sticker_sets(self, on_result):
        """The result is the installed sticker sets as [{"id", "title"}]."""
        self._request(on_result, self._load_sticker_sets_async)

    def load_stickers(self, set_id, on_result):
        """The result is the emoji each sticker of a set stands for; set_id None means the recently used."""
        self._request(on_result, self._load_stickers_async, set_id)

    def send_sticker(self, dialog_id, index, on_result, reply_to=None):
        """Send the index-th sticker of the list load_stickers gave last."""
        self._request(on_result, self._send_media_async, dialog_id, lambda: self.stickers[index], reply_to)

    def send_contact(self, dialog_id, contact_id, on_result, reply_to=None):
        """Share one of this account's contacts (loaded with load_contacts) as a contact card."""
        self._request(on_result, self._send_contact_async, dialog_id, contact_id, reply_to)

    def send_location(self, dialog_id, latitude, longitude, on_result, reply_to=None):
        point = types.InputMediaGeoPoint(types.InputGeoPoint(lat=latitude, long=longitude))
        self._request(on_result, self._send_media_async, dialog_id, lambda: point, reply_to)

    def load_chat_files(self, dialog_id, on_result):
        """Every message of a chat with a file that can be downloaded, as far back as
        CHAT_FILES_LIMIT of each kind, oldest first."""
        self._request(on_result, self._load_chat_files_async, dialog_id)

    async def _load_stories_async(self):
        result = await self.client(functions.stories.GetAllStoriesRequest())
        owners = list(getattr(result, "users", [])) + list(getattr(result, "chats", []))
        names = {get_peer_id(owner): get_display_name(owner) for owner in owners}
        self.story_peers = {get_peer_id(owner): get_input_peer(owner) for owner in owners}
        self.story_items = {}
        groups = []
        for peer_stories in getattr(result, "peer_stories", []):
            peer_id = get_peer_id(peer_stories.peer)
            stories = []
            for story in peer_stories.stories:
                # Stories Telegram only names by id (expired, or not loaded) have nothing to open.
                if getattr(story, "media", None) is None:
                    continue
                self.story_items[(peer_id, story.id)] = story
                is_photo = isinstance(story.media, types.MessageMediaPhoto)
                stories.append({
                    "id": story.id, "caption": getattr(story, "caption", None) or EMPTY_STRING,
                    "media": "MEDIA_PHOTO" if is_photo else "MEDIA_VIDEO", "date": story.date,
                })
            if stories:
                groups.append({"peer_id": peer_id, "name": names.get(peer_id, EMPTY_STRING), "stories": stories})
        return groups

    async def _open_story_async(self, peer_id, story_id):
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        path = await self.client.download_media(self.story_items[(peer_id, story_id)].media, file=DOWNLOADS_DIR + os.sep)
        if not path:
            raise ValueError("story has no downloadable media")
        try:
            await self.client(functions.stories.ReadStoriesRequest(peer=self.story_peers[peer_id], max_id=story_id))
        except Exception:
            # Best effort: the story was opened whether or not Telegram hears of it.
            pass
        return path

    async def _send_file_async(self, dialog_id, path, voice_note, report, reply_to):
        await self.client.send_file(
            self.entities[dialog_id], path, voice_note=voice_note, progress_callback=report, reply_to=reply_to
        )

    async def _send_files_async(self, dialog_id, paths, caption, as_documents, reply_to, report):
        await self.client.send_file(
            # A list, even of one, would be sent as an album.
            self.entities[dialog_id], paths if len(paths) > 1 else paths[0],
            caption=caption or None, force_document=as_documents, reply_to=reply_to, progress_callback=report
        )

    async def _send_media_async(self, dialog_id, get_media, reply_to):
        await self.client.send_file(self.entities[dialog_id], get_media(), reply_to=reply_to)

    async def _load_sticker_sets_async(self):
        result = await self.client(functions.messages.GetAllStickersRequest(hash=0))
        self.sticker_sets = {
            sticker_set.id: types.InputStickerSetID(id=sticker_set.id, access_hash=sticker_set.access_hash)
            for sticker_set in result.sets
        }
        return [{"id": sticker_set.id, "title": sticker_set.title} for sticker_set in result.sets]

    async def _load_stickers_async(self, set_id):
        if set_id is None:
            result = await self.client(functions.messages.GetRecentStickersRequest(hash=0))
            self.stickers = list(result.stickers)
        else:
            result = await self.client(functions.messages.GetStickerSetRequest(
                stickerset=self.sticker_sets[set_id], hash=0
            ))
            self.stickers = list(result.documents)
        return [self._sticker_emoji(document) for document in self.stickers]

    def _sticker_emoji(self, document):
        """The emoji a sticker stands for: the only words Telegram has for the picture."""
        for attribute in getattr(document, "attributes", None) or []:
            if isinstance(attribute, types.DocumentAttributeSticker):
                return attribute.alt or EMPTY_STRING
        return EMPTY_STRING

    async def _send_contact_async(self, dialog_id, contact_id, reply_to):
        user = await self.client.get_entity(self.entities[contact_id])
        if not getattr(user, "phone", None):
            raise PhoneHiddenError()
        await self.client.send_file(self.entities[dialog_id], types.InputMediaContact(
            phone_number=user.phone, first_name=user.first_name or EMPTY_STRING,
            last_name=user.last_name or EMPTY_STRING, vcard=EMPTY_STRING
        ), reply_to=reply_to)

    async def _load_chat_files_async(self, dialog_id):
        entity = self.entities[dialog_id]
        found = {}
        # Telegram finds each kind of file on its own; one message can turn up under two of them.
        for kind in CHAT_FILE_FILTERS:
            for message in await self.client.get_messages(entity, limit=CHAT_FILES_LIMIT, filter=kind):
                found.setdefault(message.id, message)
        described = [self._describe_message(found[message_id], found[message_id].sender) for message_id in sorted(found)]
        return [message for message in described if message["media"] in DOWNLOADABLE_MEDIA and message["file"]]

    async def _download_media_async(self, dialog_id, message_id, folder, report):
        message = await self.client.get_messages(self.entities[dialog_id], ids=message_id)
        os.makedirs(folder, exist_ok=True)
        path = await self.client.download_media(message, file=folder + os.sep, progress_callback=report)
        if not path:
            raise ValueError("message has no downloadable media")
        return path

    async def _stream_media_async(self, dialog_id, message_id, buffer):
        try:
            message = await self.client.get_messages(self.entities[dialog_id], ids=message_id)
            async for piece in self.client.iter_download(getattr(message, "media", None) or message, request_size=STREAM_REQUEST_BYTES):
                if buffer.abandoned:
                    break
                buffer.feed(piece)
        except BaseException as error:
            buffer.finish(error)
            raise
        buffer.finish()

    async def _fetch_media_async(self, dialog_id, message_id, report):
        message = await self.client.get_messages(self.entities[dialog_id], ids=message_id)
        data = await self.client.download_media(message, file=bytes, progress_callback=report)
        if not data:
            raise ValueError("message has no downloadable media")
        return data

    async def _post_story_async(self, path, caption, audience, report):
        rules = dict(zip(STORY_AUDIENCES, (
            types.InputPrivacyValueAllowAll, types.InputPrivacyValueAllowContacts,
            types.InputPrivacyValueAllowCloseFriends,
        )))
        photo = types.InputMediaUploadedPhoto(file=await self.client.upload_file(path, progress_callback=report))
        await self.client(functions.stories.SendStoryRequest(
            peer=types.InputPeerSelf(), media=photo, privacy_rules=[rules[audience]()],
            caption=caption or None, period=STORY_SECONDS
        ))
