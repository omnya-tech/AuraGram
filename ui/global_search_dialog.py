import wx
from core import global_search
from core.speech import speak
from ui.layout import prepare_window
from ui.type_ahead import TypeAhead
from core.constants import (
    GLOBAL_SEARCH_TITLE_KEY, GLOBAL_SEARCH_LABEL_KEY, GLOBAL_SEARCH_RESULTS_LABEL_KEY, BTN_SEARCH_KEY,
    BTN_OPEN_KEY, BTN_JOIN_KEY, BTN_MORE_RESULTS_KEY, MSG_GLOBAL_SEARCH_EMPTY_KEY, MSG_GLOBAL_SEARCH_COUNT_FORMAT_KEY,
    MSG_GLOBAL_SEARCH_MORE_FORMAT_KEY, MSG_GLOBAL_SEARCH_NO_MORE_KEY, MSG_SEARCHING_KEY, SEARCH_ROW_MEMBERS_FORMAT_KEY,
    SEARCH_ROW_JOINED_KEY, SEARCH_KIND_PERSON_KEY, SEARCH_KIND_BOT_KEY, CHAT_KIND_CHANNEL, CHAT_KIND_GROUP,
    MSG_JOINED_FORMAT_KEY, MSG_ALREADY_JOINED_KEY, MSG_CANNOT_JOIN_PERSON_KEY, FILE_LABEL_SEPARATOR_KEY,
    CATEGORY_BROADCASTS, CATEGORY_GROUPS, CATEGORY_BOTS
)

class GlobalSearchDialog(wx.Dialog):
    """Searching all of Telegram in a window of its own: what is found never mixes with the user's
    chats, and is gone when the window closes. A result can be opened (`chosen`, with OK) or joined
    from here; "show more" searches again, more loosely, and adds what it finds."""

    def __init__(self, parent, i18n, telegram_manager, on_joined):
        super().__init__(
            parent, title=i18n.get_string(GLOBAL_SEARCH_TITLE_KEY), size=(600, 560),
            style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER
        )
        prepare_window(self, i18n)
        self.i18n = i18n
        self.telegram_manager = telegram_manager
        # Told of a chat joined from here, so the chat list has it.
        self.on_joined = on_joined
        self.chosen = None
        self.text = ""
        self.round = 0
        # Chat id -> chat, everything found for the words being searched; and the same, nearest first.
        self.found = {}
        self.results = []
        self.busy = False

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label=i18n.get_string(GLOBAL_SEARCH_LABEL_KEY)), flag=wx.LEFT|wx.RIGHT|wx.TOP, border=10)
        search_row = wx.BoxSizer(wx.HORIZONTAL)
        self.search_input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_input.SetName(i18n.get_string(GLOBAL_SEARCH_LABEL_KEY))
        self.search_input.Bind(wx.EVT_TEXT_ENTER, lambda event: self.search())
        search_row.Add(self.search_input, proportion=1, flag=wx.RIGHT, border=10)
        search_button = wx.Button(self, label=i18n.get_string(BTN_SEARCH_KEY))
        search_button.Bind(wx.EVT_BUTTON, lambda event: self.search())
        search_row.Add(search_button)
        sizer.Add(search_row, flag=wx.EXPAND|wx.ALL, border=10)

        sizer.Add(wx.StaticText(self, label=i18n.get_string(GLOBAL_SEARCH_RESULTS_LABEL_KEY)), flag=wx.LEFT|wx.RIGHT, border=10)
        self.results_list = wx.ListBox(self, style=wx.LB_SINGLE)
        self.results_list.SetName(i18n.get_string(GLOBAL_SEARCH_RESULTS_LABEL_KEY))
        self.results_list.Bind(wx.EVT_LISTBOX_DCLICK, lambda event: self.open_result())
        self.type_ahead = TypeAhead(self.results_list, lambda index: self.results[index]["title"])
        sizer.Add(self.results_list, proportion=1, flag=wx.EXPAND|wx.ALL, border=10)
        self.count_label = wx.StaticText(self)
        sizer.Add(self.count_label, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.open_button = wx.Button(self, label=i18n.get_string(BTN_OPEN_KEY))
        self.open_button.Bind(wx.EVT_BUTTON, lambda event: self.open_result())
        self.join_button = wx.Button(self, label=i18n.get_string(BTN_JOIN_KEY))
        self.join_button.Bind(wx.EVT_BUTTON, lambda event: self.join_result())
        self.more_button = wx.Button(self, label=i18n.get_string(BTN_MORE_RESULTS_KEY))
        self.more_button.Bind(wx.EVT_BUTTON, lambda event: self.search_more())
        close_button = wx.Button(self, wx.ID_CANCEL)
        for button in (self.open_button, self.join_button, self.more_button, close_button):
            buttons.Add(button, flag=wx.RIGHT, border=10)
        sizer.Add(buttons, flag=wx.ALL, border=10)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.SetSizer(sizer)
        self.CenterOnParent()
        self.update_buttons()
        self.search_input.SetFocus()

    def on_char_hook(self, event):
        # Enter on a result opens it, rather than pressing some button of the window.
        if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and wx.Window.FindFocus() is self.results_list:
            self.open_result()
        else:
            event.Skip()

    def search(self):
        text = self.search_input.GetValue().strip()
        if not text or self.busy:
            return
        self.text, self.round, self.found, self.results = text, 0, {}, []
        self.results_list.Clear()
        self.run_round()

    def search_more(self):
        if self.text and not self.busy:
            self.run_round()

    def run_round(self):
        """Ask Telegram for the next round's words; a round with nothing new to ask is passed over."""
        while self.round < global_search.ROUNDS:
            queries = global_search.queries(self.text, self.round)
            self.round += 1
            if queries:
                self.busy = True
                self.update_buttons()
                speak(self.i18n.get_string(MSG_SEARCHING_KEY))
                self.telegram_manager.search_public(
                    queries, lambda chats, error_key: wx.CallAfter(self.on_found, chats, error_key)
                )
                return
        self.update_buttons()
        speak(self.i18n.get_string(MSG_GLOBAL_SEARCH_NO_MORE_KEY))

    def on_found(self, chats, error_key):
        if not self:
            return
        self.busy = False
        if error_key:
            self.update_buttons()
            speak(self.i18n.get_string(error_key))
            return
        before = len(self.found)
        for chat in chats or []:
            self.found.setdefault(chat["id"], chat)
        added = len(self.found) - before
        if not self.found and self.round < global_search.ROUNDS:
            # Nothing at all yet: look more loosely by itself, rather than leave the user with an empty list.
            self.run_round()
            return
        selected = self.selected()
        self.results = global_search.ranked(list(self.found.values()), self.text)
        self.results_list.Set([self.row(chat) for chat in self.results])
        if self.results:
            # Stay on the result being looked at, if there was one.
            self.results_list.SetSelection(self.results.index(selected) if selected in self.results else 0)
        self.update_buttons()
        if not self.results:
            text = self.i18n.get_string(MSG_GLOBAL_SEARCH_EMPTY_KEY)
        elif before:
            text = self.i18n.get_string(MSG_GLOBAL_SEARCH_MORE_FORMAT_KEY).format(added=added, count=len(self.results))
        else:
            text = self.i18n.get_string(MSG_GLOBAL_SEARCH_COUNT_FORMAT_KEY).format(count=len(self.results))
        self.count_label.SetLabel(text)
        speak(text)
        if self.results and before == 0:
            self.results_list.SetFocus()

    def row(self, chat):
        """A result as one line: its name, what it is, its username and size, and whether it is joined."""
        text = self.i18n.get_string
        if chat["category"] == CATEGORY_BROADCASTS:
            kind = text(CHAT_KIND_CHANNEL)
        elif chat["category"] == CATEGORY_GROUPS:
            kind = text(CHAT_KIND_GROUP)
        elif chat["category"] == CATEGORY_BOTS:
            kind = text(SEARCH_KIND_BOT_KEY)
        else:
            kind = text(SEARCH_KIND_PERSON_KEY)
        parts = [chat["title"], kind]
        if chat.get("username"):
            parts.append("@" + chat["username"])
        if chat.get("members"):
            parts.append(text(SEARCH_ROW_MEMBERS_FORMAT_KEY).format(count=chat["members"]))
        if chat["joined"] and chat["category"] in (CATEGORY_BROADCASTS, CATEGORY_GROUPS):
            parts.append(text(SEARCH_ROW_JOINED_KEY))
        return text(FILE_LABEL_SEPARATOR_KEY).join(parts)

    def selected(self):
        index = self.results_list.GetSelection()
        return self.results[index] if 0 <= index < len(self.results) else None

    def update_buttons(self):
        has_result = self.selected() is not None
        self.open_button.Enable(has_result and not self.busy)
        self.join_button.Enable(has_result and not self.busy)
        self.more_button.Enable(bool(self.text) and not self.busy and self.round < global_search.ROUNDS)

    def open_result(self):
        chat = self.selected()
        if chat is None:
            return
        self.chosen = chat
        self.EndModal(wx.ID_OK)

    def join_result(self):
        chat = self.selected()
        if chat is None or self.busy:
            return
        if chat["category"] not in (CATEGORY_BROADCASTS, CATEGORY_GROUPS):
            speak(self.i18n.get_string(MSG_CANNOT_JOIN_PERSON_KEY))
            return
        if chat["joined"]:
            speak(self.i18n.get_string(MSG_ALREADY_JOINED_KEY))
            return
        self.busy = True
        self.update_buttons()
        self.telegram_manager.join_chat(
            chat["id"], lambda result, error_key: wx.CallAfter(self.on_joined_here, chat, result, error_key)
        )

    def on_joined_here(self, chat, result, error_key):
        if not self:
            return
        self.busy = False
        self.update_buttons()
        if error_key:
            speak(self.i18n.get_string(error_key))
            return
        chat.update(joined=True, can_send=result["can_send"])
        chat.pop("preview", None)
        index = self.results.index(chat)
        self.results_list.SetString(index, self.row(chat))
        self.on_joined(chat)
        speak(self.i18n.get_string(MSG_JOINED_FORMAT_KEY).format(title=chat["title"]))
