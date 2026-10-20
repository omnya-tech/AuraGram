import os
import wx
from core import sounds
from core.settings import (
    SETTING_DOWNLOAD_FOLDER, SETTING_DOWNLOAD_PER_CHAT, SETTING_DOWNLOAD_SKIP, SETTING_DOWNLOAD_SPEAK_EACH,
    SETTING_DOWNLOAD_DONE_SOUND, SETTING_DOWNLOAD_CHECK_ALL, SETTING_DOWNLOAD_KINDS
)
from ui.download_files_dialog import DownloadFilesDialog
from core.constants import (
    FEEDBACK_RESULT,
    FEEDBACK_CONFIRM,
    DOWNLOAD_KINDS, MSG_FILE_DOWNLOADED_FORMAT_KEY, SOUND_SENT,
    DOWNLOADS_DIR, FOLDER_NAME_FORBIDDEN, DOWNLOAD_FILE_ROW_FORMAT_KEY, MSG_LOADING_FILES_KEY, MSG_NO_FILES_KEY,
    MSG_NO_CHAT_SELECTED_KEY, MSG_DOWNLOADS_QUEUED_FORMAT_KEY, MSG_DOWNLOAD_QUEUE_PROGRESS_FORMAT_KEY,
    MSG_DOWNLOADS_DONE_FORMAT_KEY, MSG_DOWNLOADS_DONE_FAILED_FORMAT_KEY, MSG_DOWNLOADS_CANCELLED_KEY,
    MSG_NO_DOWNLOADS_KEY, STATUS_READY_KEY
)

def folder_name(title):
    """A chat's name made fit to name a folder after."""
    name = "".join("_" if char in FOLDER_NAME_FORBIDDEN or ord(char) < 32 else char for char in title)
    # Windows drops a trailing dot or space without a word, and then cannot find the folder.
    return name.strip().rstrip(".") or "_"

class DownloadsMixin:
    """The download manager: the files of a chat to pick from, and a queue that fetches
    the picked ones one after another, while the rest of the app stays in use.

    Each queued item is {"chat_id", "folder", "message"}; `download_index` counts the
    files started since the queue was last empty, and `download_total` all queued in that time.
    """

    def init_downloads(self):
        self.download_queue = []
        self.download_current = None
        self.download_total = 0
        self.download_index = 0
        self.download_failed = 0
        self.download_percent = 0

    def downloads_folder(self):
        """Where what the user downloads is saved: the folder chosen in the settings, or the usual one."""
        return self.settings.get(SETTING_DOWNLOAD_FOLDER) or DOWNLOADS_DIR

    def on_download_files_menu(self, event):
        chat = self.find_known_dialog(self.current_dialog_id) if self.current_dialog_id is not None else self.selected_dialog()
        if chat is None:
            self.notify(MSG_NO_CHAT_SELECTED_KEY)
            return
        self.notify(MSG_LOADING_FILES_KEY)
        self.telegram_manager.load_chat_files(chat["id"], self.on_ui_thread(self.choose_chat_files, chat))

    def choose_chat_files(self, files, chat):
        self.set_status(STATUS_READY_KEY)
        kinds = DOWNLOAD_KINDS[self.settings.get(SETTING_DOWNLOAD_KINDS)]
        if kinds is not None:
            files = [message for message in files if message["media"] in kinds]
        if not files:
            self.notify(MSG_NO_FILES_KEY)
            return
        row = self.i18n.get_string(DOWNLOAD_FILE_ROW_FORMAT_KEY)
        rows = [row.format(file=self.media_label(message), time=self.time_text(message["date"], True)) for message in files]
        with DownloadFilesDialog(
            self, self.i18n, chat["title"], rows, checked=self.settings.get(SETTING_DOWNLOAD_CHECK_ALL)
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            chosen = [files[index] for index in dialog.chosen()]
        folder = self.downloads_folder()
        if self.settings.get(SETTING_DOWNLOAD_PER_CHAT):
            folder = os.path.join(folder, folder_name(chat["title"]))
        self.download_queue.extend({"chat_id": chat["id"], "folder": folder, "message": message} for message in chosen)
        self.download_total += len(chosen)
        self.announce(self.i18n.get_string(MSG_DOWNLOADS_QUEUED_FORMAT_KEY).format(count=len(chosen)), FEEDBACK_CONFIRM)
        if self.download_current is None:
            self.download_next()

    def download_next(self):
        """Start the next file of the queue, passing over any already saved whole; say so once all are done."""
        while self.download_queue:
            item = self.download_queue.pop(0)
            self.download_index += 1
            attached = item["message"]["file"]
            saved = os.path.join(item["folder"], attached["name"]) if attached["name"] else None
            if self.settings.get(SETTING_DOWNLOAD_SKIP) and saved and os.path.exists(saved) \
                    and os.path.getsize(saved) == attached["size"]:
                # Fetched on an earlier go: a second copy would only take up room.
                continue
            self.download_current = item
            self.download_percent = 0
            self.show_download_status(spoken=False)
            self.telegram_manager.download_media(
                item["chat_id"], item["message"]["id"],
                # Not through on_ui_thread: one file failing is no reason for a message box, nor to stop the rest.
                lambda result, error_key: wx.CallAfter(self.on_queued_file_done, error_key),
                folder=item["folder"],
                on_progress=lambda percent: wx.CallAfter(self.on_queued_file_progress, percent)
            )
            return
        self.finish_downloads()

    def on_queued_file_progress(self, percent):
        if not self or self.download_current is None:
            return
        self.download_percent = percent
        self.show_download_status(spoken=False)

    def on_queued_file_done(self, error_key):
        if not self:
            return
        if error_key:
            self.download_failed += 1
        elif self.settings.get(SETTING_DOWNLOAD_SPEAK_EACH) and self.download_current is not None:
            message = self.download_current["message"]
            self.announce(self.i18n.get_string(MSG_FILE_DOWNLOADED_FORMAT_KEY).format(
                name=message["file"]["name"] or self.i18n.get_string(message["media"])
            ), FEEDBACK_RESULT)
        self.download_current = None
        self.download_next()

    def finish_downloads(self):
        total, failed = self.download_total, self.download_failed
        self.init_downloads()
        if not total:
            return
        if self.settings.get(SETTING_DOWNLOAD_DONE_SOUND):
            sounds.play(SOUND_SENT)
        if failed:
            text = self.i18n.get_string(MSG_DOWNLOADS_DONE_FAILED_FORMAT_KEY).format(
                done=total - failed, total=total, failed=failed
            )
        else:
            text = self.i18n.get_string(MSG_DOWNLOADS_DONE_FORMAT_KEY).format(total=total)
        self.announce(text, FEEDBACK_RESULT)

    def show_download_status(self, spoken):
        """Put where the queue is on the status bar; `spoken` says it out loud too."""
        if self.download_current is None:
            if spoken:
                self.notify(MSG_NO_DOWNLOADS_KEY)
            return
        message = self.download_current["message"]
        text = self.i18n.get_string(MSG_DOWNLOAD_QUEUE_PROGRESS_FORMAT_KEY).format(
            index=self.download_index, total=self.download_total,
            name=message["file"]["name"] or self.i18n.get_string(message["media"]), percent=self.download_percent
        )
        if spoken:
            self.announce(text, FEEDBACK_RESULT)
        else:
            self.SetStatusText(text)

    def on_download_status_menu(self, event):
        self.show_download_status(spoken=True)

    def on_cancel_downloads_menu(self, event):
        if self.download_current is None:
            self.notify(MSG_NO_DOWNLOADS_KEY)
            return
        # The file coming down now cannot be stopped half way; nothing after it starts.
        self.download_total -= len(self.download_queue)
        self.download_queue = []
        self.notify(MSG_DOWNLOADS_CANCELLED_KEY)
