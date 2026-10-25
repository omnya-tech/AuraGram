"""The Help menu: the user guide, the shortcuts guide, the connection, updates, problem reports,
About and the licence.

Part of MainFrame (ui.main_frame), whose state and helpers its methods use."""
import os
import threading
import wx
from core import diagnostics, shortcut_guide, shortcuts, updates, user_guide
from core.speech import speak
from core.settings import SETTING_CHECK_UPDATES, SETTING_LANGUAGE
from ui.layout import file_size
from core.constants import (
    GUIDE_NO_SHORTCUT_KEY, MSG_GUIDE_OPENED_KEY, ERR_GUIDE_KEY, FEEDBACK_RESULT, FEEDBACK_PERCENT,
    SHORTCUTS_TITLE_KEY, SHORTCUTS_TEXT_KEY, SHORTCUT_SHOW_WINDOW, SHORTCUTS_HELP_LINE_FORMAT_KEY,
    SHORTCUTS_HELP_ANYWHERE_KEY, ABOUT_FORMAT_KEY, APP_NAME, APP_VERSION, DEVELOPER_NAME_KEY, MENU_SEARCH_KEY,
    APP_TITLE_KEY, STATUS_READY_KEY, INPUT_MENU_TITLE_KEY, MESSAGE_MENU_TITLE_KEY, DOWNLOADS_DIR,
    TRAY_STATUS_FORMAT_KEY, CONNECTION_STATE_KEYS, CONNECTION_CONNECTING, MSG_UPDATE_CHOICE_FORMAT_KEY,
    UPDATE_CHOICE_FORMAT_KEYS, UPDATE_CHOICE_PAGE_KEY, PACKAGE_FILE_FORMATS,
    MSG_UPDATE_DOWNLOADING_FORMAT_KEY, MSG_UPDATE_BUSY_KEY, MSG_UPDATE_READY_FORMAT_KEY,
    MSG_UPDATE_KEPT_FORMAT_KEY, UPDATE_PROGRESS_STEP, MSG_UP_TO_DATE_FORMAT_KEY, ERR_UPDATE_CHECK_KEY,
    MSG_PROBLEM_REPORT_PROMPT_KEY, MSG_PROBLEM_REPORT_SAVED_FORMAT_KEY, ERR_PROBLEM_REPORT_KEY,
    REPORT_LANGUAGE_FORMAT_KEY, LICENSE_TITLE_KEY, LICENSE_FILE_NAME, NOTICES_FILE_NAME, RESOURCE_DIR,
    LICENSE_NOTICE_KEY, LICENSE_SOURCE_FORMAT_KEY, SOURCE_CODE_URL, GUIDE_HTML_FILES_KEY,
    GUIDE_TEXT_FILES_KEY, GUIDE_EXTENSIONS, MSG_EXPORT_GUIDE_PROMPT_KEY, GUIDE_FILE_NAME_KEY,
    GUIDE_SHORTCUT_COLUMN_KEY, GUIDE_COMMAND_COLUMN_KEY, MSG_GUIDE_EXPORTED_FORMAT_KEY, ERR_GUIDE_EXPORT_KEY,
    TEXT_DIRECTION_KEY, ENCODING_UTF8,
)

from ui.menu_bar import EVERY_CHAT


class HelpMenuMixin:
    def on_connection_menu(self, event):
        state = self.telegram_manager.connection_state or CONNECTION_CONNECTING
        text = self.i18n.get_string(TRAY_STATUS_FORMAT_KEY).format(
            app=APP_NAME, status=self.i18n.get_string(CONNECTION_STATE_KEYS[state])
        )
        self.SetStatusText(text)
        # Asked for by name, so it is spoken whatever the setting for passing remarks says.
        speak(text)

    def check_updates_once(self):
        """Look for a newer release, by itself and at most once a run, the first time the window is seen."""
        if self.updates_checked or not self.settings.get(SETTING_CHECK_UPDATES) or not updates.is_configured():
            return
        self.updates_checked = True
        self.check_for_updates(quiet=True)

    def check_for_updates(self, quiet):
        """Ask whether a newer release is out. `quiet` says nothing unless there is one."""
        language = self.settings.get(SETTING_LANGUAGE)

        def work():
            release = updates.fetch_release(language)
            wx.CallAfter(self.on_update_checked, release, quiet)
        threading.Thread(target=work, daemon=True).start()

    def on_update_checked(self, release, quiet):
        if not self:
            return
        if release is None or not updates.is_newer(release["version"]):
            if not quiet:
                self.announce(
                    self.i18n.get_string(ERR_UPDATE_CHECK_KEY) if release is None
                    else self.i18n.get_string(MSG_UP_TO_DATE_FORMAT_KEY).format(current=APP_VERSION)
                , FEEDBACK_RESULT)
            return
        self.offer_update(release)

    def offer_update(self, release):
        """Say what is out, and let the user pick what to fetch: the small update, the whole installer, or neither."""
        if self.update_downloading:
            self.notify(MSG_UPDATE_BUSY_KEY)
            return
        text = self.i18n.get_string
        # The small one first: it is what most people want. Only what this copy can install is offered.
        kinds = [kind for kind in UPDATE_CHOICE_FORMAT_KEYS if kind in release["packages"]]
        labels = [
            text(UPDATE_CHOICE_FORMAT_KEYS[kind]).format(size=file_size(self.i18n, release["packages"][kind]["size"]))
            for kind in kinds
        ] + [text(UPDATE_CHOICE_PAGE_KEY)]
        index = self.pick(text(MSG_UPDATE_CHOICE_FORMAT_KEY).format(
            version=release["version"], current=APP_VERSION, notes=release["notes"]
        ), labels)
        if index is None:
            return
        if index == len(kinds):
            wx.LaunchDefaultBrowser(release["url"])
        else:
            self.download_update(release, kinds[index])

    def download_update(self, release, kind):
        self.update_downloading = True
        self.update_percent = None
        target = os.path.join(DOWNLOADS_DIR, PACKAGE_FILE_FORMATS[kind].format(version=release["version"]))
        package = release["packages"][kind]

        def work():
            try:
                updates.download_package(
                    package, target, lambda percent: wx.CallAfter(self.show_update_progress, percent)
                )
                error_key = None
            except updates.DownloadError as error:
                error_key = error.error_key
            wx.CallAfter(self.on_update_downloaded, release, target, error_key)
        self.show_update_progress(0)
        threading.Thread(target=work, daemon=True).start()

    def show_update_progress(self, percent):
        if not self or not self.update_downloading or percent == self.update_percent:
            return
        self.update_percent = percent
        text = self.i18n.get_string(MSG_UPDATE_DOWNLOADING_FORMAT_KEY).format(percent=percent)
        # Spoken now and then, not at every percent: the chats stay usable meanwhile.
        if percent % UPDATE_PROGRESS_STEP == 0 and percent < 100:
            self.announce(text, FEEDBACK_PERCENT)
        else:
            self.SetStatusText(text)

    def on_update_downloaded(self, release, path, error_key):
        if not self:
            return
        self.update_downloading = False
        self.set_status(STATUS_READY_KEY)
        title = self.i18n.get_string(APP_TITLE_KEY)
        if error_key:
            wx.MessageBox(self.i18n.get_string(error_key), title, wx.OK | wx.ICON_ERROR, self)
            return
        if self.confirm(self.i18n.get_string(MSG_UPDATE_READY_FORMAT_KEY).format(version=release["version"])):
            # Windows asks for permission, then the installer itself closes this program when it is ready to.
            try:
                os.startfile(path)
                return
            except OSError:
                # Turned down when Windows asked for permission: the file stays, to be run later.
                pass
        wx.MessageBox(
            self.i18n.get_string(MSG_UPDATE_KEPT_FORMAT_KEY).format(path=path), title,
            wx.OK | wx.ICON_INFORMATION, self
        )

    def on_problem_report_menu(self, event):
        description = self.ask_text(MSG_PROBLEM_REPORT_PROMPT_KEY)
        if description is None:
            return
        try:
            path = diagnostics.write_report(DOWNLOADS_DIR, description, self.i18n.get_string, [
                self.i18n.get_string(REPORT_LANGUAGE_FORMAT_KEY).format(language=self.settings.get(SETTING_LANGUAGE))
            ])
        except OSError:
            self.show_error(ERR_PROBLEM_REPORT_KEY)
            return
        wx.MessageBox(
            self.i18n.get_string(MSG_PROBLEM_REPORT_SAVED_FORMAT_KEY).format(path=path),
            self.i18n.get_string(APP_TITLE_KEY), wx.OK | wx.ICON_INFORMATION, self
        )
        try:
            os.startfile(os.path.dirname(path))
        except OSError:
            # The report is saved and its path was just said; only showing its folder failed.
            pass

    def on_user_guide_menu(self, event):
        """Write the guide in the user's language, with the app's own shortcuts, and open it in the browser.
        The ones the user changed are on the shortcuts guide; this one says so."""
        try:
            path = user_guide.write(
                self.settings.get(SETTING_LANGUAGE), shortcuts.defaults(), self.i18n.get_string(GUIDE_NO_SHORTCUT_KEY)
            )
            os.startfile(path)
        except OSError:
            self.show_error(ERR_GUIDE_KEY)
            return
        self.notify(MSG_GUIDE_OPENED_KEY)

    def on_shortcuts_menu(self, event):
        self.show_text(SHORTCUTS_TITLE_KEY, self.shortcuts_text(), on_export=self.export_shortcuts)

    def shortcuts_guide(self):
        """(the keys that never change, [(menu, [(shortcut, command), ...]), ...]) with the shortcuts as they are now."""
        sections = []
        table = shortcuts.current(self.settings)
        # Every menu of both screens, each command once: the list's menus, then those only a chat has.
        merged, seen = {}, set()
        for layout in (self.menu_layout(None), self.menu_layout(EVERY_CHAT)):
            for title_key, entries in layout:
                rows = merged.setdefault(title_key, [])
                for entry in entries:
                    if entry is not None and entry[0] not in seen and table.get(entry[0]):
                        seen.add(entry[0])
                        rows.append((table[entry[0]], self.i18n.get_string(entry[0])))
        for title_key, rows in merged.items():
            if rows:
                sections.append((wx.MenuItem.GetLabelText(self.i18n.get_string(title_key)), rows))
        # Where the Message and Send menus used to be: just before the search menu.
        titles = [title for title, rows in sections]
        search = wx.MenuItem.GetLabelText(self.i18n.get_string(MENU_SEARCH_KEY))
        place = titles.index(search) if search in titles else len(sections)
        for title_key, entries in ((INPUT_MENU_TITLE_KEY, self.send_entries()), (MESSAGE_MENU_TITLE_KEY, self.message_entries())):
            rows = [
                (table[entry[0]], self.i18n.get_string(entry[0]))
                for entry in entries if entry is not None and table[entry[0]]
            ]
            if rows:
                sections.insert(place, (self.i18n.get_string(title_key), rows))
        hotkey = self.show_window_shortcut()
        if hotkey:
            sections.append((
                self.i18n.get_string(SHORTCUTS_HELP_ANYWHERE_KEY),
                [(hotkey, shortcuts.label(self.i18n, SHORTCUT_SHOW_WINDOW))]
            ))
        return self.i18n.get_string(SHORTCUTS_TEXT_KEY), sections

    def shortcuts_text(self):
        """The keys that never change, then every menu with the shortcuts its entries have now."""
        return shortcut_guide.to_text(*self.shortcuts_guide(), self.i18n.get_string(SHORTCUTS_HELP_LINE_FORMAT_KEY))

    def on_export_shortcuts_menu(self, event):
        self.export_shortcuts()

    def export_shortcuts(self):
        """Save the guide where the user says, as a web page or as text."""
        text = self.i18n.get_string
        wildcard = "|".join(
            "%s (*%s)|*%s" % (text(label_key), extension, extension)
            for label_key, extension in zip((GUIDE_HTML_FILES_KEY, GUIDE_TEXT_FILES_KEY), GUIDE_EXTENSIONS)
        )
        with wx.FileDialog(
            self, text(MSG_EXPORT_GUIDE_PROMPT_KEY), self.downloads_folder(), text(GUIDE_FILE_NAME_KEY), wildcard,
            wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_OK:
                return
            path, kind = file_dialog.GetPath(), file_dialog.GetFilterIndex()
        self.write_shortcuts_guide(path, GUIDE_EXTENSIONS[kind])

    def write_shortcuts_guide(self, path, extension):
        """Write the guide to `path`, given the extension of its kind if it has none of its own."""
        if os.path.splitext(path)[1].lower() not in GUIDE_EXTENSIONS:
            path += extension
        intro, sections = self.shortcuts_guide()
        if path.lower().endswith(".html"):
            content = shortcut_guide.to_html(
                self.i18n.get_string(SHORTCUTS_TITLE_KEY), intro, sections, self.settings.get(SETTING_LANGUAGE),
                self.i18n.get_string(TEXT_DIRECTION_KEY), self.i18n.get_string(GUIDE_SHORTCUT_COLUMN_KEY),
                self.i18n.get_string(GUIDE_COMMAND_COLUMN_KEY)
            )
            encoding = ENCODING_UTF8
        else:
            content = shortcut_guide.to_text(intro, sections, self.i18n.get_string(SHORTCUTS_HELP_LINE_FORMAT_KEY))
            # With a byte order mark, so Notepad and every other editor see Arabic as Arabic.
            encoding = ENCODING_UTF8 + "-sig"
        try:
            with open(path, "w", encoding=encoding) as guide_file:
                guide_file.write(content)
        except OSError:
            self.show_error(ERR_GUIDE_EXPORT_KEY)
            return None
        self.announce(self.i18n.get_string(MSG_GUIDE_EXPORTED_FORMAT_KEY).format(path=path), FEEDBACK_RESULT)
        return path

    def on_about_menu(self, event):
        wx.MessageBox(
            self.i18n.get_string(ABOUT_FORMAT_KEY).format(
                name=APP_NAME, version=APP_VERSION, developer=self.i18n.get_string(DEVELOPER_NAME_KEY)
            ),
            self.i18n.get_string(APP_TITLE_KEY), wx.OK | wx.ICON_INFORMATION, self
        )

    def on_license_menu(self, event):
        """What the licence means, in the interface language; then other people's software inside; then the licence itself."""
        texts = [self.i18n.get_string(LICENSE_NOTICE_KEY)]
        if SOURCE_CODE_URL:
            texts.append(self.i18n.get_string(LICENSE_SOURCE_FORMAT_KEY).format(url=SOURCE_CODE_URL))
        for name in (NOTICES_FILE_NAME, LICENSE_FILE_NAME):
            try:
                with open(os.path.join(RESOURCE_DIR, name), encoding="utf-8-sig") as legal_file:
                    texts.append(legal_file.read().strip())
            except OSError:
                pass
        self.show_text(LICENSE_TITLE_KEY, "\n\n\n".join(texts))
