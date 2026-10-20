import wx
from ui.layout import prepare_window
from ui.text_dialog import TextDialog
from core.speech import speak, say
from core.constants import (
    FILE_LABEL_SEPARATOR_KEY,
    FEEDBACK_CONFIRM, FEEDBACK_UNAVAILABLE,
    APP_TITLE_KEY, MSG_LOADING_KEY, BTN_CLOSE_KEY, MSG_INVITE_COPIED_KEY,
    INVITE_LINKS_TITLE_FORMAT_KEY, INVITE_LINKS_LABEL_KEY, INVITE_LINK_FORMAT_KEY,
    INVITE_LINK_MAIN_KEY, INVITE_LINK_UNNAMED_KEY, INVITE_LINK_APPROVAL_SUFFIX_KEY,
    INVITE_LINKS_EMPTY_KEY, BTN_COPY_LINK_KEY, BTN_NEW_LINK_KEY, BTN_REVOKE_LINK_KEY,
    MSG_NEW_LINK_NAME_PROMPT_KEY, MSG_NEW_LINK_APPROVAL_KEY, MSG_LINK_CREATED_KEY,
    MSG_CONFIRM_REVOKE_LINK_KEY, MSG_LINK_REVOKED_KEY, MSG_NEW_LINK_EXPIRY_KEY, LINK_EXPIRY_CHOICES,
    MSG_NEW_LINK_LIMIT_KEY, ERR_LINK_LIMIT_KEY, INVITE_LINK_EXPIRES_FORMAT_KEY, INVITE_LINK_LIMIT_FORMAT_KEY,
    DATE_TIME_FORMAT, BTN_DELETE_REVOKED_KEY, MSG_CONFIRM_DELETE_REVOKED_FORMAT_KEY, MSG_NO_REVOKED_KEY,
    MSG_REVOKED_DELETED_KEY, BTN_LINK_JOINERS_KEY, LINK_JOINERS_TITLE_FORMAT_KEY, LINK_JOINED_FORMAT_KEY,
    LINK_WAITING_FORMAT_KEY, LINK_NOBODY_KEY
)

class InviteLinksDialog(wx.Dialog):
    """The invite links this account made for a chat: copy one, make another, or revoke one."""

    def __init__(self, parent, i18n, telegram_manager, dialog_id, title):
        super().__init__(
            parent, title=i18n.get_string(INVITE_LINKS_TITLE_FORMAT_KEY).format(title=title),
            size=(600, 420), style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER
        )
        prepare_window(self, i18n)
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
            (BTN_COPY_LINK_KEY, self.on_copy), (BTN_LINK_JOINERS_KEY, self.on_joiners), (BTN_NEW_LINK_KEY, self.on_new),
            (BTN_REVOKE_LINK_KEY, self.on_revoke), (BTN_DELETE_REVOKED_KEY, self.on_delete_revoked),
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
        # The limits of a link read right after its name, with the other things that set it apart.
        if link["expires"]:
            approval += self.i18n.get_string(INVITE_LINK_EXPIRES_FORMAT_KEY).format(
                date=link["expires"].astimezone().strftime(DATE_TIME_FORMAT)
            )
        if link["limit"]:
            approval += self.i18n.get_string(INVITE_LINK_LIMIT_FORMAT_KEY).format(limit=link["limit"])
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
        say(self.i18n.get_string(MSG_INVITE_COPIED_KEY), FEEDBACK_CONFIRM)

    def on_joiners(self, event):
        link = self.selected_link()
        if link is not None:
            self.telegram_manager.load_link_joiners(
                self.dialog_id, link["link"], self.on_ui_thread(lambda joiners: self.show_joiners(link, joiners))
            )

    def show_joiners(self, link, joiners):
        text = self.i18n.get_string
        lines = [
            text(key).format(count=len(joiners[name]), names=text(FILE_LABEL_SEPARATOR_KEY).join(joiners[name]))
            for name, key in (("joined", LINK_JOINED_FORMAT_KEY), ("waiting", LINK_WAITING_FORMAT_KEY))
            if joiners[name]
        ] or [text(LINK_NOBODY_KEY)]
        name = text(INVITE_LINK_MAIN_KEY) if link["permanent"] else link["title"] or text(INVITE_LINK_UNNAMED_KEY)
        with TextDialog(self, self.i18n, text(LINK_JOINERS_TITLE_FORMAT_KEY).format(name=name), "\n".join(lines)) as joiners_dialog:
            joiners_dialog.ShowModal()

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
        with wx.SingleChoiceDialog(
            self, self.i18n.get_string(MSG_NEW_LINK_EXPIRY_KEY), title,
            [self.i18n.get_string(label_key) for seconds, label_key in LINK_EXPIRY_CHOICES]
        ) as expiry_dialog:
            if expiry_dialog.ShowModal() != wx.ID_OK:
                return
            expire_seconds = LINK_EXPIRY_CHOICES[expiry_dialog.GetSelection()][0]
        usage_limit = None
        # Telegram does not count joiners on a link whose joiners wait for approval.
        if answer != wx.YES:
            with wx.TextEntryDialog(self, self.i18n.get_string(MSG_NEW_LINK_LIMIT_KEY), title) as limit_dialog:
                if limit_dialog.ShowModal() != wx.ID_OK:
                    return
                typed = limit_dialog.GetValue().strip()
            if typed:
                if not typed.isdigit() or int(typed) < 1:
                    wx.MessageBox(self.i18n.get_string(ERR_LINK_LIMIT_KEY), title, wx.OK | wx.ICON_ERROR, self)
                    return
                usage_limit = int(typed)
        self.telegram_manager.create_invite_link(
            self.dialog_id, name, answer == wx.YES,
            self.on_ui_thread(lambda result: self.on_changed(MSG_LINK_CREATED_KEY)),
            expire_seconds=expire_seconds, usage_limit=usage_limit
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

    def on_delete_revoked(self, event):
        """Clear away the links already revoked, once the user knows how many there are."""
        self.telegram_manager.count_revoked_links(self.dialog_id, self.on_ui_thread(self.confirm_delete_revoked))

    def confirm_delete_revoked(self, count):
        if not count:
            say(self.i18n.get_string(MSG_NO_REVOKED_KEY), FEEDBACK_UNAVAILABLE)
            return
        answer = wx.MessageBox(
            self.i18n.get_string(MSG_CONFIRM_DELETE_REVOKED_FORMAT_KEY).format(count=count),
            self.i18n.get_string(APP_TITLE_KEY), wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self
        )
        if answer == wx.YES:
            self.telegram_manager.delete_revoked_links(
                self.dialog_id, self.on_ui_thread(lambda result: self.on_changed(MSG_REVOKED_DELETED_KEY))
            )

    def on_changed(self, message_key):
        say(self.i18n.get_string(message_key), FEEDBACK_CONFIRM)
        self.load_links()
