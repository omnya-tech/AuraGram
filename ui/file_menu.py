"""The File menu: the downloads folder, accounts, a copy of the settings, signing out and quitting.

Part of MainFrame (ui.main_frame), whose state and helpers its methods use."""
import os
import wx
from core import restart
from core.settings import (
    SETTING_ACCOUNTS, SETTING_CURRENT_ACCOUNT, SPEECH_LEVEL_ASKED, SETTING_FAVORITES, SETTING_LANGUAGE,
)
from core.constants import (
    MSG_CHOOSE_ACCOUNT_KEY, ACCOUNT_ROW_FORMAT_KEY, ACCOUNT_CURRENT_FORMAT_KEY, ACCOUNT_UNNAMED_KEY,
    ACCOUNT_ADD_KEY, MSG_CHOOSE_SPEECH_LEVEL_KEY, MSG_SPEECH_LEVEL_SET_FORMAT_KEY, MENU_EXPORT_SETTINGS_KEY,
    MENU_IMPORT_SETTINGS_KEY, MSG_EXPORT_SECRETS_KEY, MSG_SETTINGS_EXPORTED_FORMAT_KEY,
    MSG_CONFIRM_IMPORT_SETTINGS_KEY, MSG_SETTINGS_IMPORTED_KEY, ERR_SETTINGS_FILE_KEY,
    SETTINGS_FILE_WILDCARD_KEY, SETTINGS_BACKUP_NAME, SPEECH_LEVELS, SPEECH_LEVEL_CUSTOM, FEEDBACK_RESULT,
    APP_TITLE_KEY, MSG_CONFIRM_LOGOUT_KEY, MSG_LANGUAGE_RESTART_KEY,
)


class FileMenuMixin:
    def on_open_downloads_menu(self, event):
        # Nothing has been downloaded yet on a fresh install.
        folder = self.downloads_folder()
        os.makedirs(folder, exist_ok=True)
        os.startfile(folder)

    def on_settings_menu(self, event):
        self.open_settings()

    def on_exit_menu(self, event):
        if self.on_quit is not None:
            self.on_quit()
        else:
            self.quit()

    def on_accounts_menu(self, event):
        """The accounts on this computer, the one in use marked, then a way to add one."""
        text = self.i18n.get_string
        current = self.settings.get(SETTING_CURRENT_ACCOUNT)
        accounts = self.settings.get(SETTING_ACCOUNTS)
        if current not in [account["id"] for account in accounts]:
            accounts = accounts + [{"id": current, "name": "", "phone": ""}]
        rows = []
        for account in accounts:
            row = text(ACCOUNT_ROW_FORMAT_KEY).format(**account) if account["name"] else text(ACCOUNT_UNNAMED_KEY)
            rows.append(text(ACCOUNT_CURRENT_FORMAT_KEY).format(row=row) if account["id"] == current else row)
        index = self.pick(text(MSG_CHOOSE_ACCOUNT_KEY), rows + [text(ACCOUNT_ADD_KEY)])
        if index is None or self.on_switch_account is None:
            return
        if index == len(accounts):
            self.on_switch_account(None)
        elif accounts[index]["id"] != current:
            self.on_switch_account(accounts[index]["id"])

    def ask_speech_level_once(self):
        """The first time the window opens: how much the app should say, so nobody has to find the setting."""
        if not self or self.settings.get(SPEECH_LEVEL_ASKED):
            return
        self.settings.set(SPEECH_LEVEL_ASKED, True)
        levels = [level for level in SPEECH_LEVELS if level != SPEECH_LEVEL_CUSTOM]
        index = self.pick(self.i18n.get_string(MSG_CHOOSE_SPEECH_LEVEL_KEY), [self.i18n.get_string(level) for level in levels])
        if index is not None:
            self.settings.apply_level(levels[index])
        self.settings.save()
        if index is not None:
            self.announce(self.i18n.get_string(MSG_SPEECH_LEVEL_SET_FORMAT_KEY).format(
                level=self.i18n.get_string(levels[index])
            ), FEEDBACK_RESULT)

    def on_export_settings_menu(self, event):
        with wx.FileDialog(
            self, self.i18n.get_string(MENU_EXPORT_SETTINGS_KEY), defaultFile=SETTINGS_BACKUP_NAME,
            wildcard=self.i18n.get_string(SETTINGS_FILE_WILDCARD_KEY), style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_OK:
                return
            path = file_dialog.GetPath()
        with_secrets = wx.MessageBox(
            self.i18n.get_string(MSG_EXPORT_SECRETS_KEY), self.i18n.get_string(APP_TITLE_KEY),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self
        ) == wx.YES
        try:
            self.settings.export_to(path, with_secrets)
        except OSError:
            self.show_error(ERR_SETTINGS_FILE_KEY)
            return
        self.announce(self.i18n.get_string(MSG_SETTINGS_EXPORTED_FORMAT_KEY).format(path=path), FEEDBACK_RESULT)

    def on_import_settings_menu(self, event):
        with wx.FileDialog(
            self, self.i18n.get_string(MENU_IMPORT_SETTINGS_KEY),
            wildcard=self.i18n.get_string(SETTINGS_FILE_WILDCARD_KEY), style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_OK:
                return
            path = file_dialog.GetPath()
        if not self.confirm(self.i18n.get_string(MSG_CONFIRM_IMPORT_SETTINGS_KEY)):
            return
        hotkey, language = self.show_window_shortcut(), self.settings.get(SETTING_LANGUAGE)
        if not self.settings.import_from(path):
            self.show_error(ERR_SETTINGS_FILE_KEY)
            return
        self.settings.save()
        # The same favourites set the Favourites view looks into, so it changes in place.
        self.favorites.clear()
        self.favorites.update(self.settings.get(SETTING_FAVORITES))
        self.render_dialogs()
        self.apply_simplicity()
        self.apply_text_size()
        self.apply_colours()
        self.apply_shortcuts()
        new_hotkey = self.show_window_shortcut()
        if new_hotkey != hotkey and self.on_hotkey_changed is not None:
            self.on_hotkey_changed(new_hotkey)
        self.announce(self.i18n.get_string(MSG_SETTINGS_IMPORTED_KEY), FEEDBACK_RESULT)
        if self.settings.get(SETTING_LANGUAGE) != language:
            self.offer_restart()

    def offer_restart(self):
        """A new language takes a fresh start: offer it now, Yes or No."""
        if not self:
            return
        answer = wx.MessageBox(
            self.i18n.get_string(MSG_LANGUAGE_RESTART_KEY), self.i18n.get_string(APP_TITLE_KEY),
            wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self
        )
        if answer != wx.YES:
            return
        restart.start_new_copy()
        self.on_exit_menu(None)

    def on_logout_menu(self, event):
        answer = wx.MessageBox(
            self.i18n.get_string(MSG_CONFIRM_LOGOUT_KEY), self.i18n.get_string(APP_TITLE_KEY),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self
        )
        if answer == wx.YES:
            self.on_logout()
