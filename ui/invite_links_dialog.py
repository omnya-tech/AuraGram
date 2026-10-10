import wx
from core.speech import speak
from core.constants import (
    APP_TITLE_KEY, MSG_LOADING_KEY, BTN_CLOSE_KEY, MSG_INVITE_COPIED_KEY,
    INVITE_LINKS_TITLE_FORMAT_KEY, INVITE_LINKS_LABEL_KEY, INVITE_LINK_FORMAT_KEY,
    INVITE_LINK_MAIN_KEY, INVITE_LINK_UNNAMED_KEY, INVITE_LINK_APPROVAL_SUFFIX_KEY,
    INVITE_LINKS_EMPTY_KEY, BTN_COPY_LINK_KEY, BTN_NEW_LINK_KEY, BTN_REVOKE_LINK_KEY,
    MSG_NEW_LINK_NAME_PROMPT_KEY, MSG_NEW_LINK_APPROVAL_KEY, MSG_LINK_CREATED_KEY,
    MSG_CONFIRM_REVOKE_LINK_KEY, MSG_LINK_REVOKED_KEY
)

class InviteLinksDialog(wx.Dialog):
    """The invite links this account made for a chat: copy one, make another, or revoke one."""

    def __init__(self, parent, i18n, telegram_manager, dialog_id, title):
        super().__init__(
            parent, title=i18n.get_string(INVITE_LINKS_TITLE_FORMAT_KEY).format(title=title),
            size=(600, 420), style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER
        )
        self.i18n = i18n
        self.telegram_manager = telegram_manager
        self.dialog_id = dialog_id
        self.links = []

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label=i18n.get_string(INVITE_LINKS_LABEL_KEY)), flag=wx.ALL, border=10)
        self.links_list = wx.ListBox(self, style=wx.LB_SINGLE)
        sizer.Add(self.links_list, proportion=1, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        for label_key, handler in (
            (BTN_COPY_LINK_KEY, self.on_copy), (BTN_NEW_LINK_KEY, self.on_new), (BTN_REVOKE_LINK_KEY, self.on_revoke),
        ):
            button = wx.Button(self, label=i18n.get_string(label_key))
            button.Bind(wx.EVT_BUTTON, handler)
            buttons.Add(button, flag=wx.RIGHT, border=10)
        buttons.Add(wx.Button(self, wx.ID_CANCEL, i18n.get_string(BTN_CLOSE_KEY)))
        sizer.Add(buttons, flag=wx.ALL, border=10)
        self.SetSizer(sizer)
        self.CenterOnParent()
        self.load_links()

    def on_ui_thread(self, handler):
        def deliver(result, error_key):
            wx.CallAfter(self.handle_result, handler, result, error_key)
        return deliver

    def handle_result(self, handler, result, error_key):
        # The dialog may have been closed before Telegram answered.
        if not self:
            return
        if error_key:
            wx.MessageBox(
                self.i18n.get_string(error_key), self.i18n.get_string(APP_TITLE_KEY),
                wx.OK | wx.ICON_ERROR, self
            )
        else:
            handler(result)

    def load_links(self):
        self.links = []
        self.links_list.Set([self.i18n.get_string(MSG_LOADING_KEY)])
        self.telegram_manager.load_invite_links(self.dialog_id, self.on_ui_thread(self.show_links))

    def show_links(self, links):
        self.links = links
        if not links:
            self.links_list.Set([self.i18n.get_string(INVITE_LINKS_EMPTY_KEY)])
            return
        self.links_list.Set([self.format_link(link) for link in links])
        self.links_list.SetSelection(0)

    def format_link(self, link):
        if link["permanent"]:
            name = self.i18n.get_string(INVITE_LINK_MAIN_KEY)
        else:
            name = link["title"] or self.i18n.get_string(INVITE_LINK_UNNAMED_KEY)
        approval = self.i18n.get_string(INVITE_LINK_APPROVAL_SUFFIX_KEY) if link["needs_approval"] else ""
        return self.i18n.get_string(INVITE_LINK_FORMAT_KEY).format(
            name=name, approval=approval, uses=link["uses"], link=link["link"]
        )

    def selected_link(self):
        index = self.links_list.GetSelection()
        if 0 <= index < len(self.links):
            return self.links[index]
        return None

    def on_copy(self, event):
        link = self.selected_link()
        if link is None or not wx.TheClipboard.Open():
            return
        wx.TheClipboard.SetData(wx.TextDataObject(link["link"]))
        wx.TheClipboard.Close()
        speak(self.i18n.get_string(MSG_INVITE_COPIED_KEY))

    def on_new(self, event):
        title = self.i18n.get_string(APP_TITLE_KEY)
        with wx.TextEntryDialog(self, self.i18n.get_string(MSG_NEW_LINK_NAME_PROMPT_KEY), title) as name_dialog:
            if name_dialog.ShowModal() != wx.ID_OK:
                return
            name = name_dialog.GetValue().strip()
        answer = wx.MessageBox(
            self.i18n.get_string(MSG_NEW_LINK_APPROVAL_KEY), title,
            wx.YES_NO | wx.CANCEL | wx.NO_DEFAULT | wx.ICON_QUESTION, self
        )
        if answer == wx.CANCEL:
            return
        self.telegram_manager.create_invite_link(
            self.dialog_id, name, answer == wx.YES, self.on_ui_thread(lambda result: self.on_changed(MSG_LINK_CREATED_KEY))
        )

    def on_revoke(self, event):
        link = self.selected_link()
        if link is None:
            return
        answer = wx.MessageBox(
            self.i18n.get_string(MSG_CONFIRM_REVOKE_LINK_KEY).format(link=self.format_link(link)),
            self.i18n.get_string(APP_TITLE_KEY),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self
        )
        if answer != wx.YES:
            return
        self.telegram_manager.revoke_invite_link(
            self.dialog_id, link["link"], self.on_ui_thread(lambda result: self.on_changed(MSG_LINK_REVOKED_KEY))
        )

    def on_changed(self, message_key):
        speak(self.i18n.get_string(message_key))
        self.load_links()
