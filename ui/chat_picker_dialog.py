import wx
from core.speech import speak, say
from ui.layout import prepare_window
from ui.type_ahead import TypeAhead
from core.constants import (
    FEEDBACK_COUNT,
    APP_TITLE_KEY, CHAT_PICKER_SEARCH_LABEL_KEY, CHAT_PICKER_LIST_LABEL_KEY, MSG_CHAT_PICKER_COUNT_FORMAT_KEY,
    MSG_CHAT_PICKER_NONE_KEY, CHAT_PICKER_SPEAK_DELAY_MS, CHAT_PICKER_HINT_KEY
)

class ChatPickerDialog(wx.Dialog):
    """Pick one chat or several from a long list: a search field narrows the list as it is
    typed in, and what was ticked stays ticked whatever the list shows at the moment."""

    def __init__(self, parent, i18n, prompt, titles):
        super().__init__(
            parent, title=i18n.get_string(APP_TITLE_KEY), size=(480, 520),
            style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER
        )
        prepare_window(self, i18n)
        self.i18n = i18n
        self.titles = list(titles)
        # Positions in `titles`: the ones ticked, and the ones the list shows now, in its order.
        self.ticked = set()
        self.shown = []
        self.count_timer = None
        sizer = wx.BoxSizer(wx.VERTICAL)
        # What is being asked, then how this window is worked: the same whoever asks.
        note = wx.StaticText(self, label=prompt + "\n" + i18n.get_string(CHAT_PICKER_HINT_KEY))
        note.Wrap(440)
        sizer.Add(note, flag=wx.ALL, border=10)
        sizer.Add(wx.StaticText(self, label=i18n.get_string(CHAT_PICKER_SEARCH_LABEL_KEY)), flag=wx.LEFT|wx.RIGHT, border=10)
        self.search_input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_input.Bind(wx.EVT_TEXT, self.on_search)
        # Enter in the search goes on to what was found, rather than closing the window with nothing ticked.
        self.search_input.Bind(wx.EVT_TEXT_ENTER, lambda event: self.chats_list.SetFocus())
        self.search_input.Bind(wx.EVT_KEY_DOWN, self.on_search_key)
        sizer.Add(self.search_input, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        sizer.Add(wx.StaticText(self, label=i18n.get_string(CHAT_PICKER_LIST_LABEL_KEY)), flag=wx.LEFT|wx.RIGHT, border=10)
        self.chats_list = wx.CheckListBox(self)
        self.type_ahead = TypeAhead(self.chats_list)
        self.chats_list.Bind(wx.EVT_CHECKLISTBOX, self.on_tick)
        sizer.Add(self.chats_list, proportion=1, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=10)
        sizer.Add(self.CreateButtonSizer(wx.OK|wx.CANCEL), flag=wx.EXPAND|wx.ALL, border=10)
        self.SetSizer(sizer)
        self.CenterOnParent()
        self.show_matches()
        self.search_input.SetFocus()

    def show_matches(self):
        """Fill the list with the chats whose name holds what is typed in the search; all of them when it is empty."""
        needle = self.search_input.GetValue().strip().casefold()
        self.shown = [index for index, title in enumerate(self.titles) if needle in title.casefold()]
        self.chats_list.Set([self.titles[index] for index in self.shown])
        for row, index in enumerate(self.shown):
            if index in self.ticked:
                self.chats_list.Check(row)
        if self.shown:
            self.chats_list.SetSelection(0)

    def on_search(self, event):
        self.show_matches()
        # The list changes without a sound: say how many are left, once the typing pauses.
        if self.count_timer is not None:
            self.count_timer.Stop()
        self.count_timer = wx.CallLater(CHAT_PICKER_SPEAK_DELAY_MS, self.say_count)

    def on_search_key(self, event):
        # The down arrow leads on to the list too, as the eye would expect of a list under a field.
        if event.GetKeyCode() == wx.WXK_DOWN and not event.HasAnyModifiers():
            self.chats_list.SetFocus()
        else:
            event.Skip()

    def say_count(self):
        if self:
            say(
                self.i18n.get_string(MSG_CHAT_PICKER_COUNT_FORMAT_KEY).format(count=len(self.shown)) if self.shown
                else self.i18n.get_string(MSG_CHAT_PICKER_NONE_KEY)
            , FEEDBACK_COUNT)

    def on_tick(self, event):
        index = self.shown[event.GetInt()]
        if self.chats_list.IsChecked(event.GetInt()):
            self.ticked.add(index)
        else:
            self.ticked.discard(index)

    def chosen(self):
        """Positions of the picked chats, in the order they were given. With nothing ticked,
        the chat the list stands on is the one meant."""
        if not self.ticked and self.shown and self.chats_list.GetSelection() != wx.NOT_FOUND:
            return [self.shown[self.chats_list.GetSelection()]]
        return sorted(self.ticked)

    def Destroy(self):
        if self.count_timer is not None:
            self.count_timer.Stop()
        return super().Destroy()
