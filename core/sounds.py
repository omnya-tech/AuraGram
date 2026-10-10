import os
import wx.adv
from core.constants import SOUNDS_DIR

_loaded = {}

def play(name):
    """Play one of the SOUND_* tones without waiting for it; silent if the file is missing."""
    sound = _loaded.get(name)
    if sound is None:
        path = os.path.join(SOUNDS_DIR, name + ".wav")
        if not os.path.exists(path):
            return
        # Kept loaded: reading the file again for every message would add a delay.
        sound = _loaded[name] = wx.adv.Sound(path)
    if sound.IsOk():
        sound.Play(wx.adv.SOUND_ASYNC)
