import wx
from core.speech import speak
from core.constants import (
    APP_TITLE_KEY, MSG_LOADING_KEY, CHAT_KIND_USER,
    INFO_TITLE_FORMAT_KEY, INFO_SUMMARY_LABEL_KEY, INFO_KIND_FORMAT_KEY,
    INFO_USERNAME_FORMAT_KEY, INFO_MEMBERS_COUNT_FORMAT_KEY, INFO_ROLE_MANAGER_KEY,
    INFO_ROLE_VIEWER_KEY, INFO_NAME_LABEL_KEY, INFO_ABOUT_LABEL_KEY,
    INFO_MEMBER_SEARCH_LABEL_KEY, INFO_MEMBERS_LABEL_KEY, INFO_MEMBER_ROLE_FORMAT_KEY,
    INFO_MEMBERS_FOUND_FORMAT_KEY, BTN_SEARCH_MEMBERS_KEY, BTN_SAVE_KEY, BTN_CLOSE_KEY,
    ERR_TITLE_REQUIRED_KEY
)

class ChatInfoDialog(wx.Dialog):
    """Shows a chat's details and members; its name and description can be
    edited when the account is allowed to."""

    def __init__(self, parent, i18n, telegram_manager, dialog):
        super().__init__(
            parent, title=i18n.get_string(INFO_TITLE_FORMAT_KEY).format(title=dialog["title"]),
            size=(560, 620), style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER
        )
        self.i18n = i18n
        self.telegram_manager = telegram_manager
        self.dialog_id = dialog["id"]
        self.info = None
        # Set once a new name has been saved, for the caller to show in its chat list.
        self.saved_title = None
        self.init_ui()
        self.telegram_manager.load_chat_info(self.dialog_id, self.on_ui_thread(self.show_info))

    def init_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.add_label(sizer, INFO_SUMMARY_LABEL_KEY)
        # A read-only text field, so a screen reader can go through it line by line.
        self.summary = wx.TextCtrl(
            self, value=self.i18n.get_string(MSG_LOADING_KEY),
            style=wx.TE_MULTILINE|wx.TE_READONLY, size=(-1, 90)
        )
        sizer.Add(self.summary, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)

        self.add_label(sizer, INFO_NAME_LABEL_KEY)
        self.title_input = wx.TextCtrl(self)
        sizer.Add(self.title_input, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)

        self.add_label(sizer, INFO_ABOUT_LABEL_KEY)
        self.about_input = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=(-1, 70))
        sizer.Add(self.about_input, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)

        self.members_controls = [self.add_label(sizer, INFO_MEMBER_SEARCH_LABEL_KEY)]
        search_box = wx.BoxSizer(wx.HORIZONTAL)
        self.search_input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_input.Bind(wx.EVT_TEXT_ENTER, self.on_search_members)
        search_box.Add(self.search_input, proportion=1, flag=wx.RIGHT, border=10)
        self.search_btn = wx.Button(self, label=self.i18n.get_string(BTN_SEARCH_MEMBERS_KEY))
        self.search_btn.Bind(wx.EVT_BUTTON, self.on_search_members)
        search_box.Add(self.search_btn)
        sizer.Add(search_box, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)

        self.members_controls.append(self.add_label(sizer, INFO_MEMBERS_LABEL_KEY))
        self.members_list = wx.ListBox(self, style=wx.LB_SINGLE)
        sizer.Add(self.members_list, proportion=1, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        self.members_controls += [self.search_input, self.search_btn, self.members_list]

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.save_btn = wx.Button(self, label=self.i18n.get_string(BTN_SAVE_KEY))
        self.save_btn.Bind(wx.EVT_BUTTON, self.on_save)
        buttons.Add(self.save_btn, flag=wx.RIGHT, border=10)
        buttons.Add(wx.Button(self, wx.ID_CANCEL, self.i18n.get_string(BTN_CLOSE_KEY)))
        sizer.Add(buttons, flag=wx.ALL, border=10)

        # Nothing can be edited or searched until the chat's details arrive.
        for control in (self.title_input, self.about_input, self.save_btn, *self.members_controls):
            control.Disable()
        self.SetSizer(sizer)
        self.CenterOnParent()

    def add_label(self, sizer, label_key):
        label = wx.StaticText(self, label=self.i18n.get_string(label_key))
        sizer.Add(label, flag=wx.LEFT|wx.RIGHT|wx.TOP, border=10)
        return label

    def on_ui_thread(self, handler, on_error=None):
        def deliver(result, error_key):
            wx.CallAfter(self.handle_result, handler, on_error, result, error_key)
        return deliver

    def handle_result(self, handler, on_error, result, error_key):
        # The dialog may have been closed before Telegram answered.
        if not self:
            return
        if error_key:
            if on_error is not None:
                on_error()
            self.show_error(error_key)
        else:
            handler(result)

    def show_error(self, error_key):
        wx.MessageBox(
            self.i18n.get_string(error_key), self.i18n.get_string(APP_TITLE_KEY),
            wx.OK | wx.ICON_ERROR, self
        )

    def show_info(self, info):
        self.info = info
        text = self.i18n.get_string
        lines = [text(INFO_KIND_FORMAT_KEY).format(kind=text(info["kind"]))]
        if info["username"]:
            lines.append(text(INFO_USERNAME_FORMAT_KEY).format(username=info["username"]))
        if info["members_count"] is not None:
            lines.append(text(INFO_MEMBERS_COUNT_FORMAT_KEY).format(count=info["members_count"]))
        is_user = info["kind"] == CHAT_KIND_USER
        if not is_user:
            lines.append(text(INFO_ROLE_MANAGER_KEY if info["can_edit"] else INFO_ROLE_VIEWER_KEY))
        self.summary.SetValue("\n".join(lines))

        self.title_input.SetValue(info["title"])
        self.about_input.SetValue(info["about"])
        for control in (self.title_input, self.about_input):
            control.Enable()
            # Viewers can still read and copy the text, just not change it.
            control.SetEditable(info["can_edit"])
        self.save_btn.Enable(info["can_edit"])
        self.save_btn.Show(info["can_edit"])

        for control in self.members_controls:
            control.Show(not is_user)
            control.Enable(not is_user)
        self.Layout()
        if not is_user:
            self.load_members()

    def on_search_members(self, event):
        self.load_members()

    def load_members(self):
        self.members_list.Set([self.i18n.get_string(MSG_LOADING_KEY)])
        self.telegram_manager.load_members(
            self.dialog_id, self.search_input.GetValue().strip(),
            # E.g. a channel where only admins may see the subscribers.
            self.on_ui_thread(self.show_members, on_error=self.members_list.Clear)
        )

    def show_members(self, members):
        self.members_list.Set([self.format_member(member) for member in members])
        if members:
            self.members_list.SetSelection(0)
        speak(self.i18n.get_string(INFO_MEMBERS_FOUND_FORMAT_KEY).format(count=len(members)))

    def format_member(self, member):
        if not member["role"]:
            return member["name"]
        return self.i18n.get_string(INFO_MEMBER_ROLE_FORMAT_KEY).format(
            name=member["name"], role=self.i18n.get_string(member["role"])
        )

    def on_save(self, event):
        title = self.title_input.GetValue().strip()
        about = self.about_input.GetValue().strip()
        if not title:
            self.show_error(ERR_TITLE_REQUIRED_KEY)
            return
        # Send only what changed, so an untouched field is never rewritten.
        new_title = title if title != self.info["title"] else None
        new_about = about if about != self.info["about"] else None
        if new_title is None and new_about is None:
            self.EndModal(wx.ID_CANCEL)
            return
        self.save_btn.Disable()
        self.telegram_manager.save_chat_info(
            self.dialog_id, new_title, new_about,
            self.on_ui_thread(lambda result: self.on_saved(new_title), on_error=self.save_btn.Enable)
        )

    def on_saved(self, new_title):
        self.saved_title = new_title
        self.EndModal(wx.ID_OK)
