import logging
import os
import shutil
import wave
import wx.adv
from core import audio
from core.constants import SOUNDS_DIR, USER_SOUNDS_DIR, CUSTOM_SOUND_MAX_SECONDS

logger = logging.getLogger(__name__)
_loaded = {}
# Held so a tone being tried out is not dropped while it plays.
_preview = None

def custom_path(name):
    return os.path.join(USER_SOUNDS_DIR, name + ".wav")

def has_custom(name):
    return os.path.exists(custom_path(name))

def path_of(name):
    """The user's own file for this tone if they chose one, otherwise the bundled one."""
    return custom_path(name) if has_custom(name) else os.path.join(SOUNDS_DIR, name + ".wav")

def play(name):
    """Play one of the SOUND_* tones without waiting for it; silent if the file is missing."""
    sound = _loaded.get(name)
    if sound is None:
        path = path_of(name)
        if not os.path.exists(path):
            return
        # Kept loaded: reading the file again for every message would add a delay.
        sound = _loaded[name] = wx.adv.Sound(path)
    if sound.IsOk():
        sound.Play(wx.adv.SOUND_ASYNC)

def play_file(path):
    """Play a file that is not (yet) one of the app's tones, to hear it before choosing it."""
    global _preview
    _preview = wx.adv.Sound(path)
    if _preview.IsOk():
        _preview.Play(wx.adv.SOUND_ASYNC)

def convert(source, target):
    """Write the audio file `source` to `target` as a WAV the app can play; False if it cannot be used."""
    try:
        if audio.AVAILABLE:
            samples = audio.decode(source)[:audio.SAMPLE_RATE * CUSTOM_SOUND_MAX_SECONDS]
            if not len(samples):
                return False
            with wave.open(target, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(audio.SAMPLE_RATE)
                wav.writeframes(samples.astype("<i2").tobytes())
        else:
            # Nothing to convert with: only a file Windows plays as it is will pass the check below.
            shutil.copyfile(source, target)
    except Exception:
        logger.info("Could not read %s as a tone", source, exc_info=True)
        return False
    return wx.adv.Sound(target).IsOk()

def set_custom(name, path):
    """Use the WAV at `path` (made by convert) for this tone from now on."""
    os.makedirs(USER_SOUNDS_DIR, exist_ok=True)
    _forget(name)
    shutil.copyfile(path, custom_path(name))

def clear_custom(name):
    """Go back to the bundled tone."""
    _forget(name)
    if has_custom(name):
        os.remove(custom_path(name))

def _forget(name):
    # Windows may still hold the file of a tone that is playing.
    wx.adv.Sound.Stop()
    _loaded.pop(name, None)
