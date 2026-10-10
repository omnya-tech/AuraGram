"""Generates the app's notification sounds and icon into assets/.

Run it again after changing a tone or the icon; the results are committed, so
the app and the build never need this script.

    python tools/make_assets.py
"""
import os
import sys
import wave

import numpy
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.constants import BASE_DIR, SOUND_MESSAGE, SOUND_MESSAGE_IN_CHAT, SOUND_SENT

SAMPLE_RATE = 44100
ASSETS = os.path.join(BASE_DIR, "assets")

# Note frequencies in Hz.
C5, E5, G5, A5, C6, E6 = 523.25, 659.25, 783.99, 880.00, 1046.50, 1318.51


def note(frequency, seconds, decay):
    """One soft bell-like note: a pure tone with two quiet overtones, fading out."""
    t = numpy.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    tone = (
        numpy.sin(2 * numpy.pi * frequency * t)
        + 0.30 * numpy.sin(2 * numpy.pi * frequency * 2 * t) * numpy.exp(-t * decay * 1.5)
        + 0.10 * numpy.sin(2 * numpy.pi * frequency * 3 * t) * numpy.exp(-t * decay * 2.5)
    )
    # A few milliseconds of fade-in removes the click a sudden start would make.
    attack = numpy.minimum(t / 0.004, 1.0)
    return tone * attack * numpy.exp(-t * decay)


def mix(seconds, *notes):
    """Layer notes, each given as (start time, samples), into one clip."""
    clip = numpy.zeros(int(SAMPLE_RATE * seconds))
    for start, samples in notes:
        begin = int(SAMPLE_RATE * start)
        end = min(begin + len(samples), len(clip))
        clip[begin:end] += samples[:end - begin]
    return clip


def save(name, clip, volume):
    clip = clip / numpy.abs(clip).max() * volume
    # Fade the very end to silence so the clip never stops mid-wave.
    tail = int(SAMPLE_RATE * 0.02)
    clip[-tail:] *= numpy.linspace(1.0, 0.0, tail)
    path = os.path.join(ASSETS, "sounds", name + ".wav")
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes((clip * 32767).astype("<i2").tobytes())
    print("wrote", os.path.relpath(path, BASE_DIR), "%.2fs" % (len(clip) / SAMPLE_RATE))


def make_sounds():
    os.makedirs(os.path.join(ASSETS, "sounds"), exist_ok=True)
    # A message somewhere else: three rising notes of a major chord, ringing together.
    save(SOUND_MESSAGE, mix(
        1.1, (0.00, note(E5, 0.9, 5.0)), (0.11, note(A5, 0.9, 5.0)), (0.22, note(E6, 0.85, 4.5))
    ), volume=0.55)
    # A message in the chat being read: one short, quiet, high note, easy to ignore.
    save(SOUND_MESSAGE_IN_CHAT, mix(0.45, (0.00, note(C6, 0.45, 9.0))), volume=0.30)
    # Own message sent: two quick notes going up, like a small "done".
    save(SOUND_SENT, mix(0.45, (0.00, note(G5, 0.3, 12.0)), (0.07, note(C6, 0.38, 10.0))), volume=0.32)


def make_icon():
    """A speech bubble on a blue disc, at every size Windows asks for."""
    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, size - 8, size - 8), fill=(36, 129, 204, 255))
    draw.rounded_rectangle((62, 72, 194, 160), radius=28, fill=(255, 255, 255, 255))
    draw.polygon([(92, 150), (84, 196), (128, 158)], fill=(255, 255, 255, 255))
    for x in (98, 128, 158):
        draw.ellipse((x - 9, 107, x + 9, 125), fill=(36, 129, 204, 255))
    path = os.path.join(ASSETS, "auragram.ico")
    image.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", os.path.relpath(path, BASE_DIR))


if __name__ == "__main__":
    make_sounds()
    make_icon()
