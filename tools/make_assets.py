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
from core.constants import (
    BASE_DIR, SOUND_MESSAGE, SOUND_MESSAGE_IN_CHAT, SOUND_SENT, SOUND_START, SOUND_START_WINDOWS, SOUND_RECORD_START,
    SOUND_RECORD_STOP
)

SAMPLE_RATE = 44100
ASSETS = os.path.join(BASE_DIR, "assets")

# Note frequencies in Hz.
C5, E5, G5, A5, C6, E6 = 523.25, 659.25, 783.99, 880.00, 1046.50, 1318.51
D4, D5, D6, F6_SHARP = 293.66, 587.33, 1174.66, 1479.98
A4, F5_SHARP = 440.00, 739.99


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
    # Own message sent: three quick notes going up, like a small "done". Loud enough
    # to be heard over the screen reader, which starts talking right after a send.
    save(SOUND_SENT, mix(
        0.6, (0.00, note(G5, 0.3, 11.0)), (0.07, note(C6, 0.35, 10.0)), (0.14, note(E6, 0.46, 8.0))
    ), volume=0.50)
    make_recording_sounds()
    # The app opening: its signature. An open chord climbing two octaves over a low note
    # that keeps ringing underneath, so it sounds like a glow spreading rather than a bell.
    save(SOUND_START, mix(
        1.9, (0.00, note(D4, 1.8, 2.2) * 0.6), (0.00, note(D5, 1.5, 3.0)), (0.13, note(A5, 1.5, 3.0)),
        (0.26, note(D6, 1.5, 2.8)), (0.39, note(F6_SHARP, 1.45, 2.6) * 0.8)
    ), volume=0.50)
    make_windows_start_sound()


def make_windows_start_sound():
    # Started with Windows, out of sight, and ready: the opening tone's notes, but fewer, lower and
    # softer, so it says "AuraGram is here" without sounding like a window opening.
    save(SOUND_START_WINDOWS, mix(
        1.3, (0.00, note(D4, 1.2, 3.0) * 0.5), (0.00, note(A4, 1.0, 3.5)), (0.18, note(D5, 1.0, 3.5)),
        (0.36, note(F5_SHARP, 0.9, 3.8) * 0.8)
    ), volume=0.35)


def make_recording_sounds():
    # Recording starts: two quick notes going up, "go on". Short and quiet, since the
    # microphone is already open and hears it too.
    save(SOUND_RECORD_START, mix(0.2, (0.00, note(D5, 0.12, 22.0)), (0.07, note(A5, 0.13, 20.0))), volume=0.30)
    # Recording ends: the same two coming back down.
    save(SOUND_RECORD_STOP, mix(0.22, (0.00, note(A5, 0.12, 22.0)), (0.07, note(D5, 0.15, 18.0))), volume=0.30)


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
