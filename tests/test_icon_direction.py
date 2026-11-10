"""In a right-to-left window the arrows on the buttons point the other way, and nothing else is turned:
Windows turns every picture of its own buttons round there, and none of a button wx draws itself."""
import unittest
from unittest import mock

import wx

from tests.harness import get_app
from ui import icons


class IconDirectionTest(unittest.TestCase):
    def drawn_turned(self, name, owner_drawn, right_to_left=True):
        get_app()
        frame = wx.Frame(None)
        self.addCleanup(frame.Destroy)
        if right_to_left:
            frame.SetLayoutDirection(wx.Layout_RightToLeft)
        button = wx.Button(frame, label="x")
        asked = []
        with mock.patch.object(icons, "is_drawn_by_wx", return_value=owner_drawn), \
                mock.patch.object(icons, "draw", lambda name, size, colour, mirrored=False: asked.append(mirrored)):
            icons.put_on(button, name)
        return asked[0]

    def test_on_windows_own_buttons_the_rest_is_turned_to_cancel_windows_turning_it(self):
        self.assertFalse(self.drawn_turned("back", owner_drawn=False))
        self.assertTrue(self.drawn_turned("play", owner_drawn=False))

    def test_on_buttons_wx_draws_only_the_arrows_are_turned(self):
        self.assertTrue(self.drawn_turned("back", owner_drawn=True))
        self.assertFalse(self.drawn_turned("play", owner_drawn=True))

    def test_left_to_right_nothing_is_turned(self):
        for name in ("back", "play"):
            for owner_drawn in (False, True):
                self.assertFalse(self.drawn_turned(name, owner_drawn, right_to_left=False))

    def test_a_coloured_button_is_known_as_drawn_by_wx(self):
        get_app()
        frame = wx.Frame(None)
        self.addCleanup(frame.Destroy)
        button = wx.Button(frame, label="x")
        self.assertFalse(icons.is_drawn_by_wx(button))
        # A theme's colours make wx draw it itself.
        button.SetBackgroundColour(wx.Colour(30, 30, 30))
        button.SetForegroundColour(wx.Colour(230, 230, 230))
        self.assertTrue(icons.is_drawn_by_wx(button))
