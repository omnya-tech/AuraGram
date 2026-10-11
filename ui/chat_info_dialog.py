import wx
from ui.layout import prepare_window
from core.speech import speak
from ui.chat_control_dialog import ChatControlDialog
from core.constants import (
    APP_TITLE_KEY, MSG_LOADING_KEY, STATUS_READY_KEY, CHAT_KIND_USER, CHAT_KIND_GROUP, CHAT_KIND_SUPERGROUP,
    CHAT_KIND_CHANNEL, INFO_TITLE_FORMAT_KEY, INFO_SUMMARY_LABEL_KEY, INFO_KIND_FORMAT_KEY,
    INFO_USERNAME_FORMAT_KEY, INFO_MEMBERS_COUNT_FORMAT_KEY, INFO_ROLE_MANAGER_KEY, INFO_ROLE_VIEWER_KEY,
    INFO_PHONE_FORMAT_KEY, INFO_COMMON_CHATS_FORMAT_KEY, INFO_MEMBERS_LABEL_KEY, INFO_MEMBER_SEARCH_LABEL_KEY,
    INFO_MEMBER_ROLE_FORMAT_KEY, INFO_MEMBERS_FOUND_FORMAT_KEY, BTN_SEARCH_MEMBERS_KEY, BTN_CLOSE_KEY,
    INFO_INVITE_LABEL_KEY, CONTEXT_COPY_INVITE_KEY, MSG_INVITE_COPIED_KEY, BTN_MANAGE_KEY, MEMBERS_CURRENT
)

class ChatInfoDialog(wx.Dialog):
    """A chat's details, for reading only: a summary, its invite link, and its members to look through.
    Nothing here changes anything. An admin gets a "Manage" button that opens the control window."""

    def __init__(self, parent, i18n, telegram_manager, dialog):
        super().__init__(
            parent, title=i18n.get_string(INFO_TITLE_FORMAT_KEY).format(title=dialog["title"]),
            size=(560, 560), style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER
        )
        prepare_window(self, i18n)
        self.i18n = i18n
        self.telegram_manager = telegram_manager
        self.dialog = dialog
        self.dialog_id = dialog["id"]
        self.info = None
        self.members = []
        self.invite_link = None
        # Passed up to the caller when management, opened from here, renames or deletes the chat.
        self.saved_title = None
        self.deleted = False
        self.init_ui()
        self.load_info()

    def init_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.add_label(sizer, INFO_SUMMARY_LABEL_KEY)
        # Read-only text, so a screen reader goes through it line by line and nothing can be changed.
        self.summary = wx.TextCtrl(
            self, value=self.i18n.get_string(MSG_LOADING_KEY),
            style=wx.TE_MULTILINE|wx.TE_READONLY, size=(-1, 110)
        )
        sizer.Add(self.summary, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)

        self.invite_label = self.add_label(sizer, INFO_INVITE_LABEL_KEY)
        invite_box = wx.BoxSizer(wx.HORIZONTAL)
        self.invite_field = wx.TextCtrl(self, style=wx.TE_READONLY)
        invite_box.Add(self.invite_field, proportion=1, flag=wx.RIGHT, border=10)
        self.copy_invite_btn = wx.Button(self, label=self.i18n.get_string(CONTEXT_COPY_INVITE_KEY))
        self.copy_invite_btn.Bind(wx.EVT_BUTTON, self.on_copy_invite)
        invite_box.Add(self.copy_invite_btn)
        sizer.Add(invite_box, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        self.invite_controls = [self.invite_label, self.invite_field, self.copy_invite_btn]

        self.search_label = self.add_label(sizer, INFO_MEMBER_SEARCH_LABEL_KEY)
        search_box = wx.BoxSizer(wx.HORIZONTAL)
        self.search_input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_input.Bind(wx.EVT_TEXT_ENTER, lambda event: self.load_members())
        search_box.Add(self.search_input, proportion=1, flag=wx.RIGHT, border=10)
        self.search_btn = wx.Button(self, label=self.i18n.get_string(BTN_SEARCH_MEMBERS_KEY))
        self.search_btn.Bind(wx.EVT_BUTTON, lambda event: self.load_members())
        search_box.Add(self.search_btn)
        sizer.Add(search_box, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)

        self.members_label = self.add_label(sizer, INFO_MEMBERS_LABEL_KEY)
        self.members_list = wx.ListBox(self, style=wx.LB_SINGLE)
        sizer.Add(self.members_list, proportion=1, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        self.members_controls = [self.search_label, self.search_input, self.search_btn,
                                 self.members_label, self.members_list]

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.manage_btn = wx.Button(self, label=self.i18n.get_string(BTN_MANAGE_KEY))
        self.manage_btn.Bind(wx.EVT_BUTTON, self.on_manage)
        buttons.Add(self.manage_btn, flag=wx.RIGHT, border=10)
        buttons.Add(wx.Button(self, wx.ID_CANCEL, self.i18n.get_string(BTN_CLOSE_KEY)))
        sizer.Add(buttons, flag=wx.ALL, border=10)

        # Hidden until the details arrive and say what this chat has.
        for control in self.invite_controls + self.members_controls + [self.manage_btn]:
            control.Hide()
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
        if not self:
            return
        if error_key:
            if on_error is not None:
                on_error()
            return
        handler(result)

    def load_info(self):
        self.telegram_manager.load_chat_info(self.dialog_id, self.on_ui_thread(self.show_info))

    def show_info(self, info):
        self.info = info
        text = self.i18n.get_string
        lines = [text(INFO_KIND_FORMAT_KEY).format(kind=text(info["kind"]))]
        if info["username"]:
            lines.append(text(INFO_USERNAME_FORMAT_KEY).format(username=info["username"]))
        if info["phone"]:
            lines.append(text(INFO_PHONE_FORMAT_KEY).format(phone=info["phone"]))
        if info["about"]:
            lines.append(info["about"])
        if info["common_chats"]:
            lines.append(text(INFO_COMMON_CHATS_FORMAT_KEY).format(titles="، ".join(info["common_chats"])))
        if info["members_count"] is not None:
            lines.append(text(INFO_MEMBERS_COUNT_FORMAT_KEY).format(count=info["members_count"]))
        is_user = info["kind"] == CHAT_KIND_USER
        if not is_user:
            lines.append(text(INFO_ROLE_MANAGER_KEY if info["can_edit"] else INFO_ROLE_VIEWER_KEY))
        self.summary.SetValue("\n".join(lines))

        for control in self.members_controls:
            control.Show(not is_user)
        is_admin = info["can_edit"] or info["can_ban"] or info["can_promote"] or info["can_invite"]
        self.manage_btn.Show(is_admin and not is_user)
        self.Layout()
        if not is_user:
            self.load_members()
            # Groups and channels have a link to share; a private chat does not.
            self.telegram_manager.load_invite_link(self.dialog_id, self.on_ui_thread(self.show_invite_link))

    def show_invite_link(self, link):
        self.invite_link = link
        self.invite_field.SetValue(link)
        for control in self.invite_controls:
            control.Show()
        self.Layout()

    def on_copy_invite(self, event):
        if self.invite_link and wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self.invite_link))
            wx.TheClipboard.Close()
            speak(self.i18n.get_string(MSG_INVITE_COPIED_KEY))

    def load_members(self):
        self.members_list.Set([self.i18n.get_string(MSG_LOADING_KEY)])
        self.members = []
        self.telegram_manager.load_members(
            self.dialog_id, self.search_input.GetValue().strip(),
            self.on_ui_thread(self.show_members, on_error=self.members_list.Clear), which=MEMBERS_CURRENT
        )

    def show_members(self, members):
        self.members = members
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

    def on_manage(self, event):
        with ChatControlDialog(self, self.i18n, self.telegram_manager, self.dialog) as control:
            control.ShowModal()
            self.saved_title, self.deleted = control.saved_title, control.deleted
        if self.deleted:
            # Nothing is left to show.
            self.EndModal(wx.ID_CANCEL)
            return
        if self.saved_title:
            # Renamed from the control window: carry the new name up, and show it here.
            self.dialog = dict(self.dialog, title=self.saved_title)
            self.SetTitle(self.i18n.get_string(INFO_TITLE_FORMAT_KEY).format(title=self.saved_title))
        self.load_info()
