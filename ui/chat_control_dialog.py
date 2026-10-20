import wx
from ui.layout import prepare_window
from ui.member_row import member_row
from core.speech import speak, say
from ui.admin_log_dialog import AdminLogDialog
from ui.invite_links_dialog import InviteLinksDialog
from ui.chat_admin_dialog import ChatAdminDialog
from core.constants import (
    FEEDBACK_CONFIRM, FEEDBACK_COUNT, FEEDBACK_RESULT, FEEDBACK_UNAVAILABLE,
    APP_TITLE_KEY, MSG_LOADING_KEY, CHAT_KIND_USER, CHAT_KIND_GROUP,
    MEMBER_ROLE_OWNER, MEMBER_ROLE_ADMIN, MEMBER_ACTION_KICK, MEMBER_ACTION_BAN,
    MEMBER_ACTION_PROMOTE, MEMBER_ACTION_DEMOTE, MEMBER_ACTION_TEXTS,
    INFO_MEMBERS_HINT_KEY, MSG_NO_MEMBER_ACTIONS_KEY, MEMBER_ACTION_UNBAN, MEMBER_ROLE_BANNED,
    ADMIN_RIGHTS, CHANNEL_ONLY_RIGHTS, ADMIN_RIGHT_KEY_PREFIX, MEMBER_EDIT_RIGHTS_KEY,
    MSG_CHOOSE_RIGHTS_FORMAT_KEY, MSG_NO_RIGHTS_CHOSEN_KEY, INFO_MEMBER_LIST_LABEL_KEY,
    MEMBERS_CURRENT, MEMBERS_BANNED, MEMBERS_REQUESTS, MEMBER_LISTS, MEMBER_ROLE_PENDING,
    MEMBER_ROLE_RESTRICTED, MEMBER_ACTION_MUTE, MEMBER_ACTION_UNMUTE, MEMBER_ACTION_APPROVE,
    MEMBER_ACTION_DECLINE, CHAT_KIND_SUPERGROUP, BTN_ADMIN_LOG_KEY, MEMBER_PERMISSIONS,
    MEMBER_PERMISSION_KEY_PREFIX, BTN_MEMBER_PERMISSIONS_KEY, MSG_CHOOSE_PERMISSIONS_FORMAT_KEY,
    MSG_PERMISSIONS_SAVED_KEY,
    BTN_INVITE_LINKS_KEY, CHAT_KIND_CHANNEL,
    INFO_TITLE_FORMAT_KEY, INFO_SUMMARY_LABEL_KEY, INFO_KIND_FORMAT_KEY,
    INFO_USERNAME_FORMAT_KEY, INFO_MEMBERS_COUNT_FORMAT_KEY, INFO_ROLE_MANAGER_KEY,
    INFO_ROLE_VIEWER_KEY, INFO_NAME_LABEL_KEY, INFO_ABOUT_LABEL_KEY,
    INFO_MEMBER_SEARCH_LABEL_KEY, INFO_MEMBERS_LABEL_KEY,
    INFO_MEMBERS_FOUND_FORMAT_KEY, BTN_SEARCH_MEMBERS_KEY, BTN_SAVE_KEY, BTN_CLOSE_KEY,
    ERR_TITLE_REQUIRED_KEY, CONTROL_TITLE_FORMAT_KEY, GROUP_ONLY_RIGHTS, RIGHTS_OFF_BY_DEFAULT, MEMBER_ACTION_RESTRICT,
    MEMBER_ACTION_TITLE, MEMBER_ACTION_DELETE_MESSAGES, MSG_RESTRICT_PROMPT_FORMAT_KEY,
    MSG_RESTRICT_DURATION_KEY, RESTRICT_DURATIONS, MSG_ADMIN_TITLE_PROMPT_FORMAT_KEY, BTN_ADMIN_SETTINGS_KEY,
    INFO_PHONE_FORMAT_KEY, INFO_COMMON_CHATS_FORMAT_KEY, BTN_APPROVE_ALL_KEY, BTN_DECLINE_ALL_KEY,
    MSG_CONFIRM_APPROVE_ALL_FORMAT_KEY, MSG_CONFIRM_DECLINE_ALL_FORMAT_KEY, MSG_ALL_APPROVED_KEY, MSG_ALL_DECLINED_KEY
)

class ChatControlDialog(wx.Dialog):
    """The management window for a group or channel: edit its name and description, act on its
    members, open its invite links, member permissions, admin log, and admin settings. Opened
    from the chat's menu by its owner or an admin. Read-only, defensively, for anyone who is not."""

    def __init__(self, parent, i18n, telegram_manager, dialog):
        super().__init__(
            parent, title=i18n.get_string(CONTROL_TITLE_FORMAT_KEY).format(title=dialog["title"]),
            size=(560, 620), style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER
        )
        prepare_window(self, i18n)
        self.i18n = i18n
        self.telegram_manager = telegram_manager
        self.dialog_id = dialog["id"]
        self.info = None
        self.members = []
        self.list_modes = [MEMBERS_CURRENT]
        # Set once a new name has been saved, for the caller to show in its chat list.
        self.saved_title = None
        # Set if the chat was deleted for everyone from the admin settings.
        self.deleted = False
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

        self.list_label = self.add_label(sizer, INFO_MEMBER_LIST_LABEL_KEY)
        self.list_choice = wx.Choice(self)
        self.list_choice.Bind(wx.EVT_CHOICE, self.on_search_members)
        sizer.Add(self.list_choice, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)

        self.members_label = self.add_label(sizer, INFO_MEMBERS_LABEL_KEY)
        self.members_controls.append(self.members_label)
        self.members_list = wx.ListBox(self, style=wx.LB_SINGLE)
        self.members_list.Bind(wx.EVT_CONTEXT_MENU, self.on_member_context_menu)
        sizer.Add(self.members_list, proportion=1, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        self.members_controls += [self.search_input, self.search_btn, self.members_list]

        # Six buttons are more than the window is wide: they go on to a second row rather than
        # squeeze the last of them, Close, out of sight.
        buttons = wx.WrapSizer(wx.HORIZONTAL, wx.REMOVE_LEADING_SPACES)
        self.save_btn = wx.Button(self, label=self.i18n.get_string(BTN_SAVE_KEY))
        self.save_btn.Bind(wx.EVT_BUTTON, self.on_save)
        buttons.Add(self.save_btn, flag=wx.RIGHT|wx.BOTTOM, border=10)
        self.invite_btn = wx.Button(self, label=self.i18n.get_string(BTN_INVITE_LINKS_KEY))
        self.invite_btn.Bind(wx.EVT_BUTTON, self.on_invite_links)
        buttons.Add(self.invite_btn, flag=wx.RIGHT|wx.BOTTOM, border=10)
        self.permissions_btn = wx.Button(self, label=self.i18n.get_string(BTN_MEMBER_PERMISSIONS_KEY))
        self.permissions_btn.Bind(wx.EVT_BUTTON, self.on_member_permissions)
        buttons.Add(self.permissions_btn, flag=wx.RIGHT|wx.BOTTOM, border=10)
        self.log_btn = wx.Button(self, label=self.i18n.get_string(BTN_ADMIN_LOG_KEY))
        self.log_btn.Bind(wx.EVT_BUTTON, self.on_admin_log)
        buttons.Add(self.log_btn, flag=wx.RIGHT|wx.BOTTOM, border=10)
        self.admin_btn = wx.Button(self, label=self.i18n.get_string(BTN_ADMIN_SETTINGS_KEY))
        self.admin_btn.Bind(wx.EVT_BUTTON, self.on_admin_settings)
        buttons.Add(self.admin_btn, flag=wx.RIGHT|wx.BOTTOM, border=10)
        # Shown only while the list is of join requests, and there are some.
        self.approve_all_btn = wx.Button(self, label=self.i18n.get_string(BTN_APPROVE_ALL_KEY))
        self.approve_all_btn.Bind(wx.EVT_BUTTON, lambda event: self.decide_all(True))
        self.decline_all_btn = wx.Button(self, label=self.i18n.get_string(BTN_DECLINE_ALL_KEY))
        self.decline_all_btn.Bind(wx.EVT_BUTTON, lambda event: self.decide_all(False))
        for button in (self.approve_all_btn, self.decline_all_btn):
            button.Hide()
            buttons.Add(button, flag=wx.RIGHT|wx.BOTTOM, border=10)
        buttons.Add(wx.Button(self, wx.ID_CANCEL, self.i18n.get_string(BTN_CLOSE_KEY)), flag=wx.BOTTOM, border=10)
        sizer.Add(buttons, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, border=10)

        # Nothing can be edited or searched until the chat's details arrive.
        for control in (
            self.title_input, self.about_input, self.save_btn, self.invite_btn, self.log_btn,
            self.permissions_btn, self.admin_btn,
            self.list_label, self.list_choice, *self.members_controls
        ):
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
        if info["phone"]:
            lines.append(text(INFO_PHONE_FORMAT_KEY).format(phone=info["phone"]))
        if info["common_chats"]:
            lines.append(text(INFO_COMMON_CHATS_FORMAT_KEY).format(titles="، ".join(info["common_chats"])))
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
        if info["can_ban"] or info["can_promote"]:
            # Tell managers the list is more than a list; viewers get the plain label.
            self.members_label.SetLabel(self.i18n.get_string(INFO_MEMBERS_HINT_KEY))
        # Offer only the lists this account may see here. Small basic groups keep no ban list.
        self.list_modes = [MEMBERS_CURRENT]
        if info["can_ban"] and info["kind"] != CHAT_KIND_GROUP:
            self.list_modes.append(MEMBERS_BANNED)
        if info["can_invite"]:
            self.list_modes.append(MEMBERS_REQUESTS)
        self.list_choice.Set([self.i18n.get_string(dict(MEMBER_LISTS)[mode]) for mode in self.list_modes])
        self.list_choice.SetSelection(0)
        has_choice = len(self.list_modes) > 1
        # Telegram keeps an admin log only for channels and large groups, and shows it to admins.
        is_admin = info["can_edit"] or info["can_ban"] or info["can_promote"] or info["can_invite"]
        has_log = is_admin and info["kind"] in (CHAT_KIND_CHANNEL, CHAT_KIND_SUPERGROUP)
        # A broadcast channel has no ordinary members who write, so nothing to permit.
        has_permissions = info["can_ban"] and info["kind"] in (CHAT_KIND_GROUP, CHAT_KIND_SUPERGROUP)
        for control, usable in (
            (self.list_label, has_choice), (self.list_choice, has_choice),
            (self.invite_btn, info["can_invite"]), (self.log_btn, has_log),
            (self.permissions_btn, has_permissions), (self.admin_btn, is_admin and not is_user)
        ):
            control.Show(usable)
            control.Enable(usable)
        self.Layout()
        if not is_user:
            self.load_members()

    def on_search_members(self, event):
        self.load_members()

    def load_members(self):
        self.members_list.Set([self.i18n.get_string(MSG_LOADING_KEY)])
        self.members = []
        self.telegram_manager.load_members(
            self.dialog_id, self.search_input.GetValue().strip(),
            # E.g. a channel where only admins may see the subscribers.
            self.on_ui_thread(self.show_members, on_error=self.members_list.Clear),
            which=self.list_modes[max(self.list_choice.GetSelection(), 0)]
        )

    def on_member_permissions(self, event):
        self.telegram_manager.load_member_permissions(
            self.dialog_id, self.on_ui_thread(self.choose_member_permissions)
        )

    def choose_member_permissions(self, allowed):
        with wx.MultiChoiceDialog(
            self,
            self.i18n.get_string(MSG_CHOOSE_PERMISSIONS_FORMAT_KEY).format(chat=self.info["title"]),
            self.i18n.get_string(APP_TITLE_KEY),
            [self.i18n.get_string(MEMBER_PERMISSION_KEY_PREFIX + name) for name in MEMBER_PERMISSIONS]
        ) as permissions_dialog:
            permissions_dialog.SetSelections(
                [index for index, name in enumerate(MEMBER_PERMISSIONS) if name in allowed]
            )
            if permissions_dialog.ShowModal() != wx.ID_OK:
                return
            chosen = {MEMBER_PERMISSIONS[index] for index in permissions_dialog.GetSelections()}
        if chosen == allowed:
            return
        self.telegram_manager.save_member_permissions(
            self.dialog_id, chosen,
            self.on_ui_thread(lambda result: say(self.i18n.get_string(MSG_PERMISSIONS_SAVED_KEY), FEEDBACK_CONFIRM))
        )

    def on_admin_log(self, event):
        with AdminLogDialog(
            self, self.i18n, self.telegram_manager, self.dialog_id, self.info["title"]
        ) as log_dialog:
            log_dialog.ShowModal()

    def on_admin_settings(self, event):
        with ChatAdminDialog(
            self, self.i18n, self.telegram_manager, self.dialog_id, self.info["title"]
        ) as admin_dialog:
            admin_dialog.ShowModal()
            deleted = admin_dialog.deleted
        if deleted:
            # Nothing is left to show information about.
            self.deleted = True
            self.EndModal(wx.ID_CANCEL)
        else:
            # Members may have been added, or the owner may be someone else now.
            self.load_members()

    def on_invite_links(self, event):
        with InviteLinksDialog(
            self, self.i18n, self.telegram_manager, self.dialog_id, self.info["title"]
        ) as links_dialog:
            links_dialog.ShowModal()

    def showing_requests(self):
        return self.list_modes[max(self.list_choice.GetSelection(), 0)] == MEMBERS_REQUESTS

    def decide_all(self, approved):
        question_key = MSG_CONFIRM_APPROVE_ALL_FORMAT_KEY if approved else MSG_CONFIRM_DECLINE_ALL_FORMAT_KEY
        answer = wx.MessageBox(
            self.i18n.get_string(question_key).format(chat=self.info["title"]), self.i18n.get_string(APP_TITLE_KEY),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self
        )
        if answer != wx.YES:
            return
        done_key = MSG_ALL_APPROVED_KEY if approved else MSG_ALL_DECLINED_KEY
        self.telegram_manager.decide_all_requests(
            self.dialog_id, approved, self.on_ui_thread(lambda result: self.on_all_decided(done_key))
        )

    def on_all_decided(self, done_key):
        say(self.i18n.get_string(done_key), FEEDBACK_RESULT)
        self.load_members()

    def show_members(self, members):
        self.members = members
        self.members_list.Set([self.format_member(member) for member in members])
        has_requests = self.showing_requests() and bool(members)
        for button in (self.approve_all_btn, self.decline_all_btn):
            button.Show(has_requests)
        self.Layout()
        if members:
            self.members_list.SetSelection(0)
        say(self.i18n.get_string(INFO_MEMBERS_FOUND_FORMAT_KEY).format(count=len(members)), FEEDBACK_COUNT)

    def member_actions(self, member):
        """What this account may do to a member; never anything to itself or to the owner."""
        if member["is_self"] or member["role"] == MEMBER_ROLE_OWNER:
            return []
        if member["role"] == MEMBER_ROLE_BANNED:
            return [MEMBER_ACTION_UNBAN] if self.info["can_ban"] else []
        if member["role"] == MEMBER_ROLE_PENDING:
            return [MEMBER_ACTION_APPROVE, MEMBER_ACTION_DECLINE] if self.info["can_invite"] else []
        actions = []
        if self.info["can_ban"]:
            # Only large groups can take away the right to write while keeping the member.
            if self.info["kind"] == CHAT_KIND_SUPERGROUP and member["role"] != MEMBER_ROLE_ADMIN:
                is_restricted = member["role"] == MEMBER_ROLE_RESTRICTED
                actions.append(MEMBER_ACTION_UNMUTE if is_restricted else MEMBER_ACTION_MUTE)
                actions.append(MEMBER_ACTION_RESTRICT)
                actions.append(MEMBER_ACTION_DELETE_MESSAGES)
            actions.append(MEMBER_ACTION_KICK)
            # Small basic groups have no ban list, only removal.
            if self.info["kind"] != CHAT_KIND_GROUP:
                actions.append(MEMBER_ACTION_BAN)
        if self.info["can_promote"]:
            # On someone who is already an admin, "promote" means changing their rights.
            actions.append(MEMBER_ACTION_PROMOTE)
            if member["role"] == MEMBER_ROLE_ADMIN:
                # Small basic groups have one kind of admin, with no title of their own.
                if self.info["kind"] != CHAT_KIND_GROUP:
                    actions.append(MEMBER_ACTION_TITLE)
                actions.append(MEMBER_ACTION_DEMOTE)
        return actions

    def action_label(self, member, action):
        if action == MEMBER_ACTION_PROMOTE and member["role"] == MEMBER_ROLE_ADMIN:
            return self.i18n.get_string(MEMBER_EDIT_RIGHTS_KEY)
        return self.i18n.get_string(MEMBER_ACTION_TEXTS[action][0])

    def choose_rights(self, member):
        """Ask which admin rights the member should hold; None if cancelled or nothing chosen."""
        is_channel = self.info["kind"] == CHAT_KIND_CHANNEL
        names = [
            name for name in ADMIN_RIGHTS
            if name not in (GROUP_ONLY_RIGHTS if is_channel else CHANNEL_ONLY_RIGHTS)
        ]
        if member["role"] == MEMBER_ROLE_ADMIN:
            chosen = member["rights"]
        else:
            # A sensible start for a new admin: everything but appointing more admins or hiding behind the group.
            chosen = set(names) - RIGHTS_OFF_BY_DEFAULT
        with wx.MultiChoiceDialog(
            self,
            self.i18n.get_string(MSG_CHOOSE_RIGHTS_FORMAT_KEY).format(name=member["name"], chat=self.info["title"]),
            self.i18n.get_string(APP_TITLE_KEY),
            [self.i18n.get_string(ADMIN_RIGHT_KEY_PREFIX + name) for name in names]
        ) as rights_dialog:
            rights_dialog.SetSelections([index for index, name in enumerate(names) if name in chosen])
            if rights_dialog.ShowModal() != wx.ID_OK:
                return None
            rights = {names[index] for index in rights_dialog.GetSelections()}
        if not rights:
            self.show_error(MSG_NO_RIGHTS_CHOSEN_KEY)
            return None
        return rights

    def on_member_context_menu(self, event):
        position = event.GetPosition()
        # A right click does not select by itself; keyboard menu keys report no position.
        if position != wx.DefaultPosition:
            clicked = self.members_list.HitTest(self.members_list.ScreenToClient(position))
            if clicked != wx.NOT_FOUND:
                self.members_list.SetSelection(clicked)
        index = self.members_list.GetSelection()
        if not 0 <= index < len(self.members):
            return
        member = self.members[index]
        actions = self.member_actions(member)
        if not actions:
            say(self.i18n.get_string(MSG_NO_MEMBER_ACTIONS_KEY), FEEDBACK_UNAVAILABLE)
            return
        menu = wx.Menu()
        for action in actions:
            item = menu.Append(wx.ID_ANY, self.action_label(member, action))
            menu.Bind(wx.EVT_MENU, lambda event, action=action: self.manage_member(member, action), item)
        self.PopupMenu(menu)
        menu.Destroy()

    def manage_member(self, member, action):
        _, confirm_key, done_key = MEMBER_ACTION_TEXTS[action]
        rights = title = seconds = None
        if action == MEMBER_ACTION_PROMOTE and self.info["kind"] != CHAT_KIND_GROUP:
            # Picking the rights and pressing OK is the confirmation here.
            rights = self.choose_rights(member)
            if rights is None:
                return
        elif action == MEMBER_ACTION_RESTRICT:
            chosen = self.choose_restriction(member)
            if chosen is None:
                return
            rights, seconds = chosen
        elif action == MEMBER_ACTION_TITLE:
            with wx.TextEntryDialog(
                self, self.i18n.get_string(MSG_ADMIN_TITLE_PROMPT_FORMAT_KEY).format(name=member["name"]),
                self.i18n.get_string(APP_TITLE_KEY), value=member["title"]
            ) as title_dialog:
                if title_dialog.ShowModal() != wx.ID_OK:
                    return
                title = title_dialog.GetValue().strip()
        else:
            answer = wx.MessageBox(
                self.i18n.get_string(confirm_key).format(name=member["name"], chat=self.info["title"]),
                self.i18n.get_string(APP_TITLE_KEY),
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self
            )
            if answer != wx.YES:
                return
        self.telegram_manager.manage_member(
            self.dialog_id, member["id"], action,
            self.on_ui_thread(lambda result: self.on_member_managed(member, done_key)),
            rights=rights, title=title, seconds=seconds
        )

    def choose_restriction(self, member):
        """Ask what a member may still do and for how long; None if cancelled. Returns (allowed, seconds)."""
        title = self.i18n.get_string(APP_TITLE_KEY)
        with wx.MultiChoiceDialog(
            self, self.i18n.get_string(MSG_RESTRICT_PROMPT_FORMAT_KEY).format(name=member["name"]), title,
            [self.i18n.get_string(MEMBER_PERMISSION_KEY_PREFIX + name) for name in MEMBER_PERMISSIONS]
        ) as permissions_dialog:
            # Starts from nothing taken away: the admin unticks what the member loses.
            permissions_dialog.SetSelections(list(range(len(MEMBER_PERMISSIONS))))
            if permissions_dialog.ShowModal() != wx.ID_OK:
                return None
            allowed = {MEMBER_PERMISSIONS[index] for index in permissions_dialog.GetSelections()}
        with wx.SingleChoiceDialog(
            self, self.i18n.get_string(MSG_RESTRICT_DURATION_KEY), title,
            [self.i18n.get_string(label_key) for seconds, label_key in RESTRICT_DURATIONS]
        ) as duration_dialog:
            if duration_dialog.ShowModal() != wx.ID_OK:
                return None
            return allowed, RESTRICT_DURATIONS[duration_dialog.GetSelection()][0]

    def on_member_managed(self, member, done_key):
        say(self.i18n.get_string(done_key).format(name=member["name"]), FEEDBACK_CONFIRM)
        # Reload so the list shows the member's new role, or that they are gone.
        self.load_members()

    def format_member(self, member):
        return member_row(self, self.i18n, member)

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
