"""A list of rows with a picture and a colour each: the chats (their photos, colours by kind) and the
messages (what each carries, the colour of who wrote it).

A plain list box can show neither, so this is Windows' own list view (what Explorer lists files in),
which every screen reader knows: it reads each row's words as it read the list box's. It answers to the
same calls as wx.ListBox (Set, GetSelection, SetString, Insert...) and sends the same events, so the
rest of the program uses it as it used the list box.

How each row looks is asked of `row_look(index)` whenever a row is written: (colour or None, bold,
picture index or -1). The pictures come from whatever is given to set_pictures: anything with an
`image_list`.
"""
import wx

NO_LOOK = (None, False, -1)


class ChatRows(wx.ListCtrl):
    def __init__(self, parent, row_look=None):
        super().__init__(parent, style=wx.LC_REPORT | wx.LC_NO_HEADER | wx.LC_SINGLE_SEL)
        self.row_look = row_look or (lambda index: NO_LOOK)
        self.InsertColumn(0, "")
        self.pictures = None
        # True while the program itself moves the selection: a list box says nothing of that.
        self.moving = False
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_selected)
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_activated)

    # ----------------------------------------------------------------- what a list box answers to

    def GetCount(self):
        return self.GetItemCount()

    def IsEmpty(self):
        return self.GetItemCount() == 0

    def GetString(self, index):
        return self.GetItemText(index)

    def GetItems(self):
        return [self.GetItemText(index) for index in range(self.GetItemCount())]

    GetStrings = GetItems

    def GetSelection(self):
        return self.GetFirstSelected()

    def SetSelection(self, index):
        """Select a row, or none with wx.NOT_FOUND, without the event a user's choice would send."""
        self.moving = True
        try:
            selected = self.GetFirstSelected()
            if selected != wx.NOT_FOUND and selected != index:
                self.Select(selected, False)
            if 0 <= index < self.GetItemCount():
                self.Select(index)
                # Where the keyboard is, too, which is what a screen reader follows.
                self.Focus(index)
        finally:
            self.moving = False

    def Set(self, items):
        self.Freeze()
        try:
            self.DeleteAllItems()
            for index, text in enumerate(items):
                self.InsertItem(index, text)
                self.paint_row(index)
        finally:
            self.Thaw()

    def SetString(self, index, text):
        self.SetItemText(index, text)
        self.paint_row(index)

    def Insert(self, text, index):
        self.InsertItem(index, text)
        self.paint_row(index)
        return index

    def Append(self, text):
        return self.Insert(text, self.GetItemCount())

    def Delete(self, index):
        self.DeleteItem(index)

    def Clear(self):
        self.DeleteAllItems()

    def HitTest(self, point):
        """The row at a point, or wx.NOT_FOUND, as a list box tells it."""
        index, flags = super().HitTest(point)
        return index

    # ----------------------------------------------------------------- how the rows look

    def set_pictures(self, pictures):
        """Show each row's picture from `pictures` (avatars.ChatPictures, icons.MediaPictures), or none with None."""
        self.pictures = pictures
        # The list does not own the image list it shows: `pictures` keeps it alive.
        self.SetImageList(pictures.image_list if pictures is not None else None, wx.IMAGE_LIST_SMALL)

    def paint_row(self, index):
        colour, bold, picture = self.row_look(index)
        self.SetItemTextColour(index, colour if colour is not None else self.GetTextColour())
        font = self.GetFont()
        if bold:
            font = font.Bold()
        self.SetItemFont(index, font)
        self.SetItemImage(index, picture if self.pictures is not None else -1)

    def paint_rows(self):
        """Look again at every row: the theme, the text size or the settings changed."""
        for index in range(self.GetItemCount()):
            self.paint_row(index)
        self.fit_column()
        self.Refresh()

    def fit_column(self):
        # One column, as wide as the list, so a row's words run to its edge and no further.
        self.SetColumnWidth(0, max(self.GetClientSize().width, 1))

    # ----------------------------------------------------------------- events, as a list box sends them

    def on_size(self, event):
        event.Skip()
        wx.CallAfter(self.fit_column_if_alive)

    def fit_column_if_alive(self):
        if self:
            self.fit_column()

    def on_selected(self, event):
        event.Skip()
        if self.moving:
            return
        self.send(wx.wxEVT_LISTBOX, event.GetIndex())

    def on_activated(self, event):
        # A double click; Enter is taken by the window before it gets here.
        self.send(wx.wxEVT_LISTBOX_DCLICK, event.GetIndex())

    def send(self, event_type, index):
        command = wx.CommandEvent(event_type, self.GetId())
        command.SetEventObject(self)
        command.SetInt(index)
        self.ProcessWindowEvent(command)
