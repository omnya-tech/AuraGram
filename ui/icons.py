"""Small pictures beside the words on buttons and tabs, for the eyes.

They are drawn from the icon font Windows itself ships (Segoe Fluent Icons on Windows 11, Segoe MDL2
Assets on Windows 10), so they need no image files, are sharp at any screen scaling, and take the
colours of the theme in use. On a system with neither font the buttons simply keep their words alone.

The words stay on every button: they are what a screen reader says, and what tells a sighted user who
does not know the picture what it does. The picture only makes the button quicker to find.
"""
import wx

from ui.themes import THEME_COLOURS, current_theme

ICON_FONTS = ("Segoe Fluent Icons", "Segoe MDL2 Assets")
# Icon name -> its character in those fonts (both number them the same).
GLYPHS = {
    "send": 0xE724, "attach": 0xE723, "microphone": 0xE720, "stop": 0xE71A, "cancel": 0xE711,
    "search": 0xE721, "back": 0xE72B, "add": 0xE710, "globe": 0xE774, "download": 0xE896, "info": 0xE946,
    "settings": 0xE713, "more": 0xE712, "reply": 0xE97A, "forward": 0xE72D, "react": 0xE76E, "play": 0xE768,
    "open": 0xE8E5, "comments": 0xE90A, "stats": 0xE9D2, "remind": 0xEA8F, "delete": 0xE74D,
    "chats": 0xE8F2, "unread": 0xE715, "archive": 0xF12B, "channel": 0xE789, "group": 0xE902,
    "favorite": 0xE734, "contact": 0xE77B, "folder": 0xE8B7,
    "audio": 0xE8D6, "photo": 0xE722, "video": 0xE714, "video_note": 0xE8AA, "gif": 0xF4A9, "file": 0xE7C3,
    "sticker": 0xE76E, "location": 0xE707, "contact_card": 0xE779, "poll": 0xE9D5,
}
# The picture at the start of a message's row in the list, by what it carries (a MEDIA_* key).
MEDIA_ICONS = {
    "MEDIA_VOICE": "microphone", "MEDIA_AUDIO": "audio", "MEDIA_PHOTO": "photo", "MEDIA_VIDEO": "video",
    "MEDIA_VIDEO_NOTE": "video_note", "MEDIA_GIF": "gif", "MEDIA_FILE": "file", "MEDIA_STICKER": "sticker",
    "MEDIA_LOCATION": "location", "MEDIA_CONTACT": "contact_card", "MEDIA_POLL": "poll",
}
# Pictures that point a way: in a right-to-left window they point the other way, as the reading does
# ("back" to the right, "send" to the left), the way Windows and Telegram's own apps turn them.
DIRECTIONAL = {"send", "back", "reply", "forward"}
# How big a picture is beside a button's words, before the screen's scaling.
ICON_SIZE = 16

_font_name = None
_looked_for_font = False
# (name, size in pixels, colour) -> bitmap: the same picture is drawn once.
_drawn = {}


def font_name():
    """The icon font this computer has; None if it has neither."""
    global _font_name, _looked_for_font
    if not _looked_for_font:
        _looked_for_font = True
        _font_name = next((name for name in ICON_FONTS if wx.FontEnumerator.IsValidFacename(name)), None)
    return _font_name


def available():
    return font_name() is not None


def icon_colour():
    """The colour pictures are drawn in: the theme's text, or Windows' own button text."""
    colours = THEME_COLOURS[current_theme()]
    if colours is None:
        return wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNTEXT)
    return wx.Colour(colours["text"])


def draw(name, size, colour, mirrored=False):
    """The picture `name` as a bitmap `size` pixels square, in `colour` on a see-through background,
    turned left to right if `mirrored`; None if there is no icon font."""
    face = font_name()
    if face is None:
        return None
    key = (name, size, colour.GetRGB(), mirrored)
    if key in _drawn:
        return _drawn[key]
    # Black on white first: how dark each pixel came out is how solid it is to be.
    canvas = wx.Bitmap(size, size, 24)
    dc = wx.MemoryDC(canvas)
    dc.SetBackground(wx.WHITE_BRUSH)
    dc.Clear()
    dc.SetFont(wx.Font(wx.FontInfo(wx.Size(0, size)).FaceName(face)))
    dc.SetTextForeground(wx.BLACK)
    glyph = chr(GLYPHS[name])
    width, height = dc.GetTextExtent(glyph)
    dc.DrawText(glyph, (size - width) // 2, (size - height) // 2)
    dc.SelectObject(wx.NullBitmap)
    shade = canvas.ConvertToImage().GetData()
    image = wx.Image(size, size)
    image.SetData(bytes((colour.Red(), colour.Green(), colour.Blue())) * (size * size))
    image.SetAlpha(bytes(255 - shade[index] for index in range(0, len(shade), 3)))
    bitmap = wx.Bitmap(image.Mirror() if mirrored else image)
    _drawn[key] = bitmap
    return bitmap


BUTTON_TYPE_MASK = 0x0F
BUTTON_OWNER_DRAWN = 0x0B
WINDOW_STYLE = -16


def is_drawn_by_wx(button):
    """Whether wx draws the button itself (its colours set by a theme), rather than Windows: then nothing
    of it is turned round for a right-to-left window, its picture included."""
    try:
        import ctypes
        style = ctypes.windll.user32.GetWindowLongW(button.GetHandle(), WINDOW_STYLE)
    except Exception:
        return False
    return style & BUTTON_TYPE_MASK == BUTTON_OWNER_DRAWN


def put_on(button, name, colour=None):
    """Give a button (or toggle button) its picture beside its words, in the current theme's colours or
    in `colour`. Called again after the theme changes, it repaints the picture; None leaves it without one."""
    button.icon_name = name
    if name is None:
        return
    # In a right-to-left window the arrows are to point the other way, and nothing else is. Windows itself
    # turns round every picture of its own buttons there, so on those it is the rest that is turned here,
    # to come out as drawn; a button wx draws itself (once a theme gives it colours) shows its picture as it
    # is, so there only the arrows are.
    right_to_left = button.GetLayoutDirection() == wx.Layout_RightToLeft
    mirrored = right_to_left and ((name in DIRECTIONAL) == is_drawn_by_wx(button))
    bitmap = draw(name, button.FromDIP(ICON_SIZE), colour or icon_colour(), mirrored)
    if bitmap is None:
        return
    button.SetBitmap(bitmap, wx.LEFT)
    button.SetBitmapMargins(button.FromDIP(wx.Size(4, 0)))
    # Room for the picture: the button grows to hold it and its words.
    button.InvalidateBestSize()


def list_text_colour():
    """The colour of the words in lists, which a list's pictures take too."""
    colours = THEME_COLOURS[current_theme()]
    if colours is None:
        return wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
    return wx.Colour(colours["field_text"])


class MediaPictures:
    """The pictures of what messages carry, for a list's rows: one image list holding one of each.

    `mirrored`: the list is laid out right to left, where Windows draws its pictures back to front
    (a "GIF" would read "FIG"); each is turned beforehand so that it comes out the right way.
    """

    def __init__(self, size, colour, mirrored=False):
        self.size = size
        self.image_list = wx.ImageList(size, size, mask=False)
        self.indexes = {}
        for media, name in MEDIA_ICONS.items():
            bitmap = draw(name, size, colour, mirrored)
            if bitmap is not None:
                self.indexes[media] = self.image_list.Add(bitmap)

    def index_for(self, media):
        """The picture of a MEDIA_* kind; -1 for a message with none, or one without a picture."""
        return self.indexes.get(media, -1)


def repaint(window):
    """Draw again, in the theme's colours now, the picture of every button inside a window."""
    for child in window.GetChildren():
        if getattr(child, "icon_name", None):
            put_on(child, child.icon_name)
        if not isinstance(child, wx.TopLevelWindow):
            repaint(child)
