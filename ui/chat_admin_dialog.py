import wx
from ui.layout import prepare_window
from ui.text_dialog import TextDialog
from core.speech import speak
from core.constants import (
    APP_TITLE_KEY, MSG_LOADING_KEY, BTN_SAVE_KEY, BTN_CLOSE_KEY, ADMIN_SETTINGS_TITLE_FORMAT_KEY,
    ADMIN_SETTING_KEY_PREFIX, SETTING_USERNAME, ADMIN_SWITCHES, ADMIN_CHOICES, CHOICE_KEPT_FORMAT_KEY,
    MSG_ADMIN_SETTINGS_SAVED_KEY, MSG_NOTHING_CHANGED_KEY, BTN_CHAT_PHOTO_KEY, MSG_CHAT_PHOTO_SET_KEY,
    MSG_CHOOSE_PHOTO_KEY, PHOTO_FILES_KEY, PHOTO_FILE_PATTERNS, BTN_ADD_MEMBERS_KEY,
    MSG_CHOOSE_MEMBERS_TO_ADD_KEY, MSG_MEMBERS_ADDED_FORMAT_KEY, MSG_NO_CONTACTS_KEY, BTN_STATS_KEY,
    STATS_TITLE_KEY, STATS_ROW_FORMAT_KEY, STATS_PERCENT_FORMAT_KEY, STATS_LABEL_KEY_PREFIX,
    BTN_TRANSFER_KEY, MSG_CHOOSE_NEW_OWNER_KEY, MSG_NO_ADMINS_KEY, MSG_CONFIRM_TRANSFER_FORMAT_KEY,
    ERR_TRANSFER_NEEDS_PASSWORD_KEY, MSG_TRANSFERRED_FORMAT_KEY, MSG_TWO_STEP_CURRENT_KEY,
    BTN_DELETE_CHAT_KEY, MSG_CONFIRM_DELETE_CHAT_FOREVER_FORMAT_KEY, MSG_TYPE_CHAT_NAME_FORMAT_KEY,
    MSG_DELETE_CHAT_CANCELLED_KEY, MEMBER_ROLE_ADMIN, BTN_MANAGE_TOPICS_KEY, MSG_MANAGE_TOPICS_KEY,
    TOPIC_NEW_KEY, TOPIC_CLOSED_FORMAT_KEY, MSG_TOPIC_NAME_PROMPT_KEY, MSG_TOPIC_ACTION_FORMAT_KEY,
    TOPIC_RENAME_KEY, TOPIC_CLOSE_KEY, TOPIC_REOPEN_KEY, TOPIC_DELETE_KEY,
    MSG_CONFIRM_DELETE_TOPIC_FORMAT_KEY, MSG_TOPIC_SAVED_KEY, BTN_DISCUSSION_KEY,
    MSG_CHOOSE_DISCUSSION_KEY, DISCUSSION_NONE_KEY, MSG_DISCUSSION_SAVED_KEY, BTN_CHOOSE_REACTIONS_KEY,
    MSG_CHOOSE_REACTIONS_KEY, REACTION_EMOJIS, REACTION_NAME_KEY_PREFIX, REACTION_CHOICE_FORMAT_KEY,
    SETTING_FORUM, SETTING_SIGNATURES, GENERAL_TOPIC_ID, TOPIC_PIN_KEY, TOPIC_UNPIN_KEY, TOPIC_PINNED_FORMAT_KEY,
    BTN_GROUP_STICKERS_KEY, MSG_CHOOSE_GROUP_STICKERS_FORMAT_KEY, GROUP_STICKERS_NONE_KEY, MSG_GROUP_STICKERS_SAVED_KEY,
    MSG_NO_STICKER_SETS_KEY, BTN_GROUP_EMOJI_KEY, MSG_CHOOSE_GROUP_EMOJI_FORMAT_KEY, MSG_GROUP_EMOJI_SAVED_KEY,
    MSG_NO_EMOJI_SETS_KEY, BTN_BOOSTS_KEY, BOOSTS_TITLE_KEY, BOOSTS_LEVEL_FORMAT_KEY, BOOSTS_COUNT_FORMAT_KEY,
    BOOSTS_NEXT_FORMAT_KEY, BOOSTS_TOP_KEY, BOOSTS_LINK_FORMAT_KEY
)


class ChatAdminDialog(wx.Dialog):
    """What an admin sets for a whole group or channel, as opposed to for one member:
    how it is found and joined, what happens to its messages, and the chat itself."""

    def __init__(self, parent, i18n, telegram_manager, dialog_id, title):
        super().__init__(
            parent, title=i18n.get_string(ADMIN_SETTINGS_TITLE_FORMAT_KEY).format(title=title),
            size=(600, 640), style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER
        )
        prepare_window(self, i18n)
        self.i18n = i18n
        self.telegram_manager = telegram_manager
        self.dialog_id = dialog_id
        self.chat_title = title
        self.settings = None
        # name -> the control showing that setting; only for settings this chat has.
        self.controls = {}
        # name -> the values its drop-down offers, in order.
        self.choice_values = {}
        # Set once the chat has been deleted for everyone.
        self.deleted = False
        self.init_ui()
        self.load()

    def init_ui(self):
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.note = wx.StaticText(self, label=self.i18n.get_string(MSG_LOADING_KEY))
        self.sizer.Add(self.note, flag=wx.ALL, border=10)
        # Filled in once Telegram says which settings this chat has.
        self.settings_sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.settings_sizer, proportion=1, flag=wx.EXPAND)

        self.buttons = {}
        rows = (
            ((BTN_SAVE_KEY, self.on_save), (BTN_CHAT_PHOTO_KEY, self.on_photo), (BTN_ADD_MEMBERS_KEY, self.on_add_members)),
            ((BTN_CHOOSE_REACTIONS_KEY, self.on_reactions), (BTN_MANAGE_TOPICS_KEY, self.on_topics), (BTN_DISCUSSION_KEY, self.on_discussion)),
            ((BTN_STATS_KEY, self.on_stats), (BTN_TRANSFER_KEY, self.on_transfer), (BTN_DELETE_CHAT_KEY, self.on_delete)),
            ((BTN_GROUP_STICKERS_KEY, self.on_group_stickers), (BTN_GROUP_EMOJI_KEY, self.on_group_emoji),
             (BTN_BOOSTS_KEY, self.on_boosts)),
        )
        for row in rows:
            row_sizer = wx.BoxSizer(wx.HORIZONTAL)
            for label_key, handler in row:
                button = wx.Button(self, label=self.i18n.get_string(label_key))
                button.Bind(wx.EVT_BUTTON, handler)
                button.Disable()
                row_sizer.Add(button, flag=wx.RIGHT, border=10)
                self.buttons[label_key] = button
            self.sizer.Add(row_sizer, flag=wx.LEFT|wx.RIGHT|wx.TOP, border=10)
        self.sizer.Add(wx.Button(self, wx.ID_CANCEL, self.i18n.get_string(BTN_CLOSE_KEY)), flag=wx.ALL, border=10)
        self.SetSizer(self.sizer)
        self.CenterOnParent()

    def on_ui_thread(self, handler):
        def deliver(result, error_key):
            wx.CallAfter(self.handle_result, handler, result, error_key)
        return deliver

    def handle_result(self, handler, result, error_key):
        # The dialog may have been closed before Telegram answered.
        if not self:
            return
        if error_key:
            self.show_message(self.i18n.get_string(error_key), wx.ICON_ERROR)
        else:
            handler(result)

    def show_message(self, text, icon=wx.ICON_INFORMATION):
        wx.MessageBox(text, self.i18n.get_string(APP_TITLE_KEY), wx.OK | icon, self)

    def confirm(self, text):
        answer = wx.MessageBox(
            text, self.i18n.get_string(APP_TITLE_KEY), wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self
        )
        return answer == wx.YES

    def load(self):
        self.telegram_manager.load_admin_settings(self.dialog_id, self.on_ui_thread(self.show_settings))

    def show_settings(self, settings):
        self.settings = settings
        self.note.SetLabel("")
        self.settings_sizer.Clear(delete_windows=True)
        self.controls = {}
        values = settings["values"]
        text = self.i18n.get_string
        if SETTING_USERNAME in values:
            self.add_label(SETTING_USERNAME)
            username = wx.TextCtrl(self, value=values[SETTING_USERNAME])
            self.add_control(SETTING_USERNAME, username, wx.EXPAND)
        for name in ADMIN_SWITCHES:
            if name in values:
                checkbox = wx.CheckBox(self, label=text(ADMIN_SETTING_KEY_PREFIX + name))
                checkbox.SetValue(values[name])
                self.add_control(name, checkbox, 0)
        for name, options in ADMIN_CHOICES.items():
            if name not in values:
                continue
            self.add_label(name)
            offered = [value for value, label_key in options]
            labels = [text(label_key) for value, label_key in options]
            if values[name] not in offered:
                # Set elsewhere to something this list does not offer: shown, and kept unless changed.
                offered.append(values[name])
                labels.append(text(CHOICE_KEPT_FORMAT_KEY).format(
                    value=text(values[name]) if isinstance(values[name], str) else values[name]
                ))
            choice = wx.Choice(self, choices=labels)
            choice.SetSelection(offered.index(values[name]))
            self.choice_values[name] = offered
            self.add_control(name, choice, wx.EXPAND)
        for control in self.controls.values():
            control.Enable(settings["can_edit"])
        for label_key, usable in (
            (BTN_SAVE_KEY, settings["can_edit"]), (BTN_CHAT_PHOTO_KEY, settings["can_edit"]),
            (BTN_ADD_MEMBERS_KEY, settings["can_invite"]), (BTN_STATS_KEY, settings["can_view_stats"]),
            (BTN_TRANSFER_KEY, settings["is_owner"]), (BTN_DELETE_CHAT_KEY, settings["is_owner"]),
            (BTN_CHOOSE_REACTIONS_KEY, settings["can_edit"]),
            # Only a group already split into topics has any to manage.
            (BTN_MANAGE_TOPICS_KEY, bool(values.get(SETTING_FORUM)) and settings["can_manage_topics"]),
            # Comments belong to broadcast channels, which are the chats that sign their posts.
            (BTN_DISCUSSION_KEY, SETTING_SIGNATURES in values and settings["can_edit"]),
            (BTN_GROUP_STICKERS_KEY, settings["can_set_stickers"] and settings["can_edit"]),
            (BTN_GROUP_EMOJI_KEY, settings["is_large_group"] and settings["can_edit"]),
            (BTN_BOOSTS_KEY, settings["has_boosts"]),
        ):
            self.buttons[label_key].Enable(usable)
        self.Layout()

    def add_label(self, name):
        label = wx.StaticText(self, label=self.i18n.get_string(ADMIN_SETTING_KEY_PREFIX + name))
        self.settings_sizer.Add(label, flag=wx.LEFT|wx.RIGHT, border=10)

    def add_control(self, name, control, flag):
        self.settings_sizer.Add(control, flag=flag|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        self.controls[name] = control

    def changes(self):
        """Only the settings the admin actually changed, as {name: new value}."""
        changed = {}
        for name, control in self.controls.items():
            if name in self.choice_values:
                value = self.choice_values[name][control.GetSelection()]
            elif name == SETTING_USERNAME:
                value = control.GetValue().strip()
            else:
                value = control.GetValue()
            if value != self.settings["values"][name]:
                changed[name] = value
        return changed

    def on_save(self, event):
        changed = self.changes()
        if not changed:
            speak(self.i18n.get_string(MSG_NOTHING_CHANGED_KEY))
            return
        self.telegram_manager.save_admin_settings(self.dialog_id, changed, self.on_ui_thread(self.on_saved))

    def on_saved(self, result):
        speak(self.i18n.get_string(MSG_ADMIN_SETTINGS_SAVED_KEY))
        # Read back: Telegram may have turned something else on or off along with it.
        self.load()

    def on_group_stickers(self, event):
        self.telegram_manager.load_sticker_sets(self.on_ui_thread(self.choose_group_stickers))

    def choose_group_stickers(self, sticker_sets):
        self.choose_group_set(
            sticker_sets, self.settings["stickers"], MSG_NO_STICKER_SETS_KEY, MSG_CHOOSE_GROUP_STICKERS_FORMAT_KEY,
            self.telegram_manager.set_group_stickers, MSG_GROUP_STICKERS_SAVED_KEY
        )

    def on_group_emoji(self, event):
        self.telegram_manager.load_emoji_sets(self.on_ui_thread(self.choose_group_emoji))

    def choose_group_emoji(self, emoji_sets):
        self.choose_group_set(
            emoji_sets, self.settings["emoji"], MSG_NO_EMOJI_SETS_KEY, MSG_CHOOSE_GROUP_EMOJI_FORMAT_KEY,
            self.telegram_manager.set_group_emoji, MSG_GROUP_EMOJI_SAVED_KEY
        )

    def choose_group_set(self, sets, current, empty_key, prompt_key, save, saved_key):
        """Pick one of the account's sticker or emoji sets for the whole group, or none."""
        text = self.i18n.get_string
        if not sets:
            self.show_message(text(empty_key))
            return
        with wx.SingleChoiceDialog(
            self, text(prompt_key).format(current=current or text(GROUP_STICKERS_NONE_KEY)), text(APP_TITLE_KEY),
            [text(GROUP_STICKERS_NONE_KEY)] + [one_set["title"] for one_set in sets]
        ) as sets_dialog:
            if sets_dialog.ShowModal() != wx.ID_OK:
                return
            index = sets_dialog.GetSelection()
        set_id = None if index == 0 else sets[index - 1]["id"]
        save(self.dialog_id, set_id, self.on_ui_thread(lambda result: self.on_group_set_saved(saved_key)))

    def on_group_set_saved(self, saved_key):
        speak(self.i18n.get_string(saved_key))
        self.load()

    def on_boosts(self, event):
        self.telegram_manager.load_boosts(self.dialog_id, self.on_ui_thread(self.show_boosts))

    def show_boosts(self, boosts):
        text = self.i18n.get_string
        lines = [
            text(BOOSTS_LEVEL_FORMAT_KEY).format(level=boosts["level"]),
            text(BOOSTS_COUNT_FORMAT_KEY).format(count=boosts["boosts"]),
        ]
        if boosts["next"]:
            lines.append(text(BOOSTS_NEXT_FORMAT_KEY).format(needed=max(boosts["next"] - boosts["boosts"], 0)))
        else:
            lines.append(text(BOOSTS_TOP_KEY))
        if boosts["link"]:
            lines.append(text(BOOSTS_LINK_FORMAT_KEY).format(link=boosts["link"]))
        with TextDialog(self, self.i18n, text(BOOSTS_TITLE_KEY), "\n".join(lines)) as boosts_dialog:
            boosts_dialog.ShowModal()

    def on_photo(self, event):
        with wx.FileDialog(
            self, self.i18n.get_string(MSG_CHOOSE_PHOTO_KEY),
            wildcard="%s (%s)|%s" % (self.i18n.get_string(PHOTO_FILES_KEY), PHOTO_FILE_PATTERNS, PHOTO_FILE_PATTERNS),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as file_dialog:
            if file_dialog.ShowModal() != wx.ID_OK:
                return
            path = file_dialog.GetPath()
        self.set_photo(path)

    def set_photo(self, path):
        self.telegram_manager.set_chat_photo(
            self.dialog_id, path, self.on_ui_thread(lambda result: speak(self.i18n.get_string(MSG_CHAT_PHOTO_SET_KEY)))
        )

    def on_add_members(self, event):
        self.telegram_manager.load_contacts(self.on_ui_thread(self.choose_members))

    def choose_members(self, contacts):
        if not contacts:
            speak(self.i18n.get_string(MSG_NO_CONTACTS_KEY))
            return
        with wx.MultiChoiceDialog(
            self, self.i18n.get_string(MSG_CHOOSE_MEMBERS_TO_ADD_KEY), self.i18n.get_string(APP_TITLE_KEY),
            [contact["title"] for contact in contacts]
        ) as members_dialog:
            if members_dialog.ShowModal() != wx.ID_OK:
                return
            chosen = [contacts[index]["id"] for index in members_dialog.GetSelections()]
        if chosen:
            self.telegram_manager.add_members(self.dialog_id, chosen, self.on_ui_thread(
                lambda result: speak(self.i18n.get_string(MSG_MEMBERS_ADDED_FORMAT_KEY).format(count=len(chosen)))
            ))

    def choose(self, prompt, choices):
        """Index picked from a list; None if the user backs out."""
        with wx.SingleChoiceDialog(self, prompt, self.i18n.get_string(APP_TITLE_KEY), choices) as choice_dialog:
            if choice_dialog.ShowModal() != wx.ID_OK:
                return None
            return choice_dialog.GetSelection()

    def ask_line(self, prompt, value=""):
        with wx.TextEntryDialog(self, prompt, self.i18n.get_string(APP_TITLE_KEY), value=value) as line_dialog:
            if line_dialog.ShowModal() != wx.ID_OK:
                return None
            return line_dialog.GetValue().strip()

    def saved(self, message_key, reload=False):
        """A handler for "Telegram accepted it": say so, and read the settings back if they changed."""
        def handle(result):
            speak(self.i18n.get_string(message_key))
            if reload:
                self.load()
        return self.on_ui_thread(handle)

    def on_reactions(self, event):
        text = self.i18n.get_string
        with wx.MultiChoiceDialog(self, text(MSG_CHOOSE_REACTIONS_KEY), text(APP_TITLE_KEY), [
            text(REACTION_CHOICE_FORMAT_KEY).format(name=text(REACTION_NAME_KEY_PREFIX + str(index)), emoji=emoji)
            for index, emoji in enumerate(REACTION_EMOJIS)
        ]) as reactions_dialog:
            reactions_dialog.SetSelections([
                index for index, emoji in enumerate(REACTION_EMOJIS) if emoji in self.settings["reactions"]
            ])
            if reactions_dialog.ShowModal() != wx.ID_OK:
                return
            chosen = [REACTION_EMOJIS[index] for index in reactions_dialog.GetSelections()]
        # None chosen is "no reactions", which the drop-down above already offers.
        if chosen:
            self.telegram_manager.set_reactions(self.dialog_id, chosen, self.saved(MSG_ADMIN_SETTINGS_SAVED_KEY, reload=True))

    def on_topics(self, event):
        self.telegram_manager.load_topics(self.dialog_id, self.on_ui_thread(self.manage_topics))

    def manage_topics(self, topics):
        text = self.i18n.get_string
        def described(topic):
            title = topic["title"]
            if topic["pinned"]:
                title = text(TOPIC_PINNED_FORMAT_KEY).format(title=title)
            return text(TOPIC_CLOSED_FORMAT_KEY).format(title=title) if topic["closed"] else title

        index = self.choose(text(MSG_MANAGE_TOPICS_KEY), [text(TOPIC_NEW_KEY)] + [described(topic) for topic in topics])
        if index is None:
            return
        done = self.saved(MSG_TOPIC_SAVED_KEY)
        if index == 0:
            title = self.ask_line(text(MSG_TOPIC_NAME_PROMPT_KEY))
            if title:
                self.telegram_manager.create_topic(self.dialog_id, title, done)
            return
        topic = topics[index - 1]
        actions = [
            TOPIC_RENAME_KEY, TOPIC_REOPEN_KEY if topic["closed"] else TOPIC_CLOSE_KEY,
            TOPIC_UNPIN_KEY if topic["pinned"] else TOPIC_PIN_KEY,
        ]
        # The first topic of every forum group can be closed or renamed, but never removed.
        if topic["id"] != GENERAL_TOPIC_ID:
            actions.append(TOPIC_DELETE_KEY)
        chosen = self.choose(
            text(MSG_TOPIC_ACTION_FORMAT_KEY).format(title=topic["title"]), [text(action) for action in actions]
        )
        if chosen is None:
            return
        action = actions[chosen]
        if action == TOPIC_RENAME_KEY:
            title = self.ask_line(text(MSG_TOPIC_NAME_PROMPT_KEY), topic["title"])
            if title and title != topic["title"]:
                self.telegram_manager.edit_topic(self.dialog_id, topic["id"], done, title=title)
        elif action in (TOPIC_PIN_KEY, TOPIC_UNPIN_KEY):
            self.telegram_manager.pin_topic(self.dialog_id, topic["id"], action == TOPIC_PIN_KEY, done)
        elif action == TOPIC_DELETE_KEY:
            if self.confirm(text(MSG_CONFIRM_DELETE_TOPIC_FORMAT_KEY).format(title=topic["title"])):
                self.telegram_manager.delete_topic(self.dialog_id, topic["id"], done)
        else:
            self.telegram_manager.edit_topic(self.dialog_id, topic["id"], done, closed=action == TOPIC_CLOSE_KEY)

    def on_discussion(self, event):
        self.telegram_manager.load_discussion_groups(self.on_ui_thread(self.choose_discussion))

    def choose_discussion(self, groups):
        index = self.choose(
            self.i18n.get_string(MSG_CHOOSE_DISCUSSION_KEY),
            [self.i18n.get_string(DISCUSSION_NONE_KEY)] + [group["title"] for group in groups]
        )
        if index is not None:
            self.telegram_manager.set_discussion_group(
                self.dialog_id, groups[index - 1]["id"] if index else None, self.saved(MSG_DISCUSSION_SAVED_KEY)
            )

    def on_stats(self, event):
        self.telegram_manager.load_stats(self.dialog_id, self.on_ui_thread(self.show_stats))

    def stats_text(self, rows):
        lines = []
        for name, current, previous in rows:
            label = self.i18n.get_string(STATS_LABEL_KEY_PREFIX + name)
            if previous is None:
                lines.append(self.i18n.get_string(STATS_PERCENT_FORMAT_KEY).format(label=label, percent=current))
            else:
                lines.append(self.i18n.get_string(STATS_ROW_FORMAT_KEY).format(
                    label=label, current=round(current), previous=round(previous)
                ))
        return "\n".join(lines)

    def show_stats(self, rows):
        with TextDialog(self, self.i18n, self.i18n.get_string(STATS_TITLE_KEY), self.stats_text(rows)) as stats_dialog:
            stats_dialog.ShowModal()

    def on_transfer(self, event):
        self.telegram_manager.load_two_step_state(self.on_ui_thread(self.load_admins))

    def load_admins(self, has_password):
        if not has_password:
            self.show_message(self.i18n.get_string(ERR_TRANSFER_NEEDS_PASSWORD_KEY), wx.ICON_ERROR)
            return
        self.telegram_manager.load_members(self.dialog_id, "", self.on_ui_thread(self.choose_new_owner))

    def choose_new_owner(self, members):
        admins = [member for member in members if member["role"] == MEMBER_ROLE_ADMIN and not member["is_self"]]
        if not admins:
            self.show_message(self.i18n.get_string(MSG_NO_ADMINS_KEY))
            return
        with wx.SingleChoiceDialog(
            self, self.i18n.get_string(MSG_CHOOSE_NEW_OWNER_KEY), self.i18n.get_string(APP_TITLE_KEY),
            [admin["name"] for admin in admins]
        ) as owner_dialog:
            if owner_dialog.ShowModal() != wx.ID_OK:
                return
            admin = admins[owner_dialog.GetSelection()]
        if not self.confirm(self.i18n.get_string(MSG_CONFIRM_TRANSFER_FORMAT_KEY).format(
            chat=self.chat_title, name=admin["name"]
        )):
            return
        with wx.PasswordEntryDialog(
            self, self.i18n.get_string(MSG_TWO_STEP_CURRENT_KEY), self.i18n.get_string(APP_TITLE_KEY)
        ) as password_dialog:
            if password_dialog.ShowModal() != wx.ID_OK or not password_dialog.GetValue():
                return
            password = password_dialog.GetValue()
        self.telegram_manager.transfer_ownership(
            self.dialog_id, admin["id"], password, self.on_ui_thread(lambda result: self.on_transferred(admin))
        )

    def on_transferred(self, admin):
        self.show_message(self.i18n.get_string(MSG_TRANSFERRED_FORMAT_KEY).format(name=admin["name"]))
        # This account is an ordinary admin now: show what it may still do.
        self.load()

    def on_delete(self, event):
        # A question, then the chat's own name typed out: this cannot be undone for anyone.
        confirmed = self.confirm(
            self.i18n.get_string(MSG_CONFIRM_DELETE_CHAT_FOREVER_FORMAT_KEY).format(chat=self.chat_title)
        )
        typed = None
        if confirmed:
            with wx.TextEntryDialog(
                self, self.i18n.get_string(MSG_TYPE_CHAT_NAME_FORMAT_KEY).format(chat=self.chat_title),
                self.i18n.get_string(APP_TITLE_KEY)
            ) as name_dialog:
                if name_dialog.ShowModal() == wx.ID_OK:
                    typed = name_dialog.GetValue().strip()
        if typed != self.chat_title:
            speak(self.i18n.get_string(MSG_DELETE_CHAT_CANCELLED_KEY))
            return
        self.telegram_manager.delete_chat(self.dialog_id, self.on_ui_thread(self.on_deleted))

    def on_deleted(self, result):
        self.deleted = True
        if self.IsModal():
            self.EndModal(wx.ID_CANCEL)
