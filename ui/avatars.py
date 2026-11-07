"""The round picture at the start of each row of the chat list.

A chat with a photo on Telegram shows it, once it has come down; until then, and for a chat with none,
its initials on a colour of its own, as Telegram's own apps do, so every row has something to tell it
by at a glance. Photos are kept in a folder on this computer and fetched only once per photo.
"""
import os

import wx

from core.constants import CHAT_PHOTO_NAME_FORMAT

# The colours Telegram gives chats without a photo, picked by the chat's number so each keeps its own.
PLACEHOLDER_COLOURS = ("#E17076", "#FAA774", "#A695E7", "#7BC862", "#6EC9CB", "#65AADD", "#EE7AAE")


def photo_path(folder, chat_id, photo_id):
    return os.path.join(folder, CHAT_PHOTO_NAME_FORMAT.format(chat_id=chat_id, photo_id=photo_id))


def initials(title):
    """One or two letters for a chat: the first of its first two words."""
    letters = [word[0] for word in title.split() if word and word[0].isalnum()][:2]
    return "".join(letters).upper() or "#"


def circle_alpha(size):
    """How solid each pixel of a round picture is: inside, outside, and smoothed along the edge."""
    centre = (size - 1) / 2
    radius = size / 2
    alpha = bytearray(size * size)
    for y in range(size):
        for x in range(size):
            distance = ((x - centre) ** 2 + (y - centre) ** 2) ** 0.5
            alpha[y * size + x] = max(0, min(255, int((radius - distance + 0.5) * 255)))
    return bytes(alpha)


def placeholder(title, chat_id, size, mirrored=False):
    """A round bitmap with the chat's initials in white on its colour."""
    image = wx.Image(size, size)
    image.InitAlpha()
    image.SetAlpha(bytes(size * size))
    context = wx.GraphicsContext.Create(image)
    context.SetAntialiasMode(wx.ANTIALIAS_DEFAULT)
    context.SetBrush(wx.Brush(wx.Colour(PLACEHOLDER_COLOURS[abs(chat_id) % len(PLACEHOLDER_COLOURS)])))
    context.SetPen(wx.TRANSPARENT_PEN)
    context.DrawEllipse(0, 0, size, size)
    font = wx.Font(wx.FontInfo(wx.Size(0, size * 2 // 5)).Bold())
    context.SetFont(font, wx.WHITE)
    text = initials(title)
    width, height = context.GetTextExtent(text)
    context.DrawText(text, (size - width) / 2, (size - height) / 2)
    del context
    return wx.Bitmap(image.Mirror() if mirrored else image)


def round_photo(path, size, mirrored=False):
    """A photo file cut to a circle `size` pixels across; None if the file cannot be read."""
    image = wx.Image()
    if not os.path.exists(path) or not image.LoadFile(path, wx.BITMAP_TYPE_ANY) or not image.IsOk():
        return None
    # The middle of the photo, square, then made small.
    side = min(image.GetWidth(), image.GetHeight())
    image = image.GetSubImage(wx.Rect((image.GetWidth() - side) // 2, (image.GetHeight() - side) // 2, side, side))
    image = image.Scale(size, size, wx.IMAGE_QUALITY_HIGH)
    image.SetAlpha(circle_alpha(size))
    return wx.Bitmap(image.Mirror() if mirrored else image)


class ChatPictures:
    """The pictures of one list's rows, in an image list the list shows them from.

    `mirrored`: the list is laid out right to left, where Windows draws every picture back to front;
    each is turned round beforehand so that it comes out the right way.
    """

    def __init__(self, folder, size, mirrored=False):
        self.folder = folder
        self.size = size
        self.mirrored = mirrored
        self.image_list = wx.ImageList(size, size, mask=False)
        # chat id -> (its photo's id or None, index of its picture in the image list).
        self.indexes = {}
        # (chat id, photo id) of the photos to be fetched: wanted, and not on this computer yet.
        self.missing = set()

    def index_for(self, chat):
        """The image list index of a chat's picture, made the first time it is asked for."""
        chat_id, photo_id = chat["id"], chat.get("photo")
        known = self.indexes.get(chat_id)
        if known is not None and known[0] == photo_id:
            return known[1]
        bitmap = None
        if photo_id is not None:
            bitmap = round_photo(photo_path(self.folder, chat_id, photo_id), self.size, self.mirrored)
            if bitmap is None:
                self.missing.add((chat_id, photo_id))
        if bitmap is None:
            bitmap = placeholder(chat["title"], chat_id, self.size, self.mirrored)
        if known is not None:
            # The chat changed its photo: the same place in the list of pictures takes the new one.
            self.image_list.Replace(known[1], bitmap)
            index = known[1]
        else:
            index = self.image_list.Add(bitmap)
        self.indexes[chat_id] = (photo_id, index)
        return index

    def take_missing(self):
        """The photos to fetch now, each handed out once."""
        missing, self.missing = sorted(self.missing), set()
        return missing

    def photo_arrived(self, chat_id, photo_id, path):
        """A photo has come down: True if it took the place of what its chat showed until now."""
        known = self.indexes.get(chat_id)
        if known is None or known[0] != photo_id:
            return False
        bitmap = round_photo(path, self.size, self.mirrored)
        if bitmap is None:
            return False
        self.image_list.Replace(known[1], bitmap)
        return True
