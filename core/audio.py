"""Voice message playback and recording.

Needs the optional packages av, numpy and sounddevice; `AVAILABLE` says
whether they could be loaded.
"""
import io
import logging
import threading

try:
    import av
    import numpy
    import sounddevice
    AVAILABLE = True
except Exception:
    AVAILABLE = False

# What Telegram voice notes use: Opus, mono, 48 kHz.
logger = logging.getLogger(__name__)

SAMPLE_RATE = 48000
SAMPLE_FORMAT = "int16"
LOUDEST = 32767
# Noise reduction works on short overlapping stretches of sound, a fiftieth of a second each.
NOISE_FRAME = 1024
NOISE_HOP = 256
# Rumble and mains hum live below this; a voice does not.
LOW_CUT_HZ = 80
# The share of the loudest possible that "as loud as it goes" aims for, and the most a quiet recording is raised.
AUTO_LEVEL_PEAK = 0.9
AUTO_LEVEL_MAX_GAIN = 8.0
# How much of a recording may be louder than what its level is measured by: a tap or a cough
# that stands far above the voice is not allowed to hold the whole recording down.
LEVEL_PEAK_PERCENTILE = 99.9
# How little of a sound is read to know what it is before playing starts: Telegram's voice notes
# (Ogg/Opus) and songs (MP3) say what they are in their first bytes.
STREAM_PROBE_OPTIONS = {"probesize": "32768", "analyzeduration": "0"}
# How far back a sound being played can be taken: what was heard is kept this long, in memory only.
REWIND_SECONDS = 120
# Samples handed to the sound card at a time: short, so a jump is heard at once.
PLAY_BLOCK = 2048
# The longest stopping a sound may hold up the program.
STOP_WAIT_SECONDS = 2
# Above this share of the loudest a sample can be, what is left is bent smoothly under it rather than cut.
LIMIT_KNEE = 0.9


def decode_pieces(source, speed=1.0, halted=None):
    """Read any audio, a file's path or its bytes held in memory, as mono int16 pieces at SAMPLE_RATE,
    one after another as they are decoded, so a long sound is never held whole. `speed` shortens or
    stretches it without changing how high the voice sounds; `halted()` true stops the reading."""
    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    with av.open(io.BytesIO(source) if isinstance(source, bytes) else source) as container:
        stream = container.streams.audio[0]
        if speed == 1.0:
            frames = container.decode(stream)
        else:
            frames = _at_speed(container.decode(stream), stream, speed)
        for frame in frames:
            if halted is not None and halted():
                return
            for out in resampler.resample(frame):
                yield out.to_ndarray()[0]
        for out in resampler.resample(None):
            yield out.to_ndarray()[0]


def decode(source, speed=1.0, seconds=None):
    """A sound as one mono int16 array at SAMPLE_RATE: for short sounds, like the tones. With `seconds`,
    only its start: reading stops there, so a long song chosen as a tone is not decoded whole."""
    wanted = None if seconds is None else int(seconds * SAMPLE_RATE)
    chunks = []
    got = 0
    for chunk in decode_pieces(source, speed):
        chunks.append(chunk)
        got += len(chunk)
        if wanted is not None and got >= wanted:
            break
    if not chunks:
        return numpy.zeros(0, dtype=SAMPLE_FORMAT)
    return numpy.concatenate(chunks)[:wanted]


def _at_speed(frames, stream, speed):
    """Pass decoded frames through FFmpeg's tempo filter, yielding them as they come out."""
    graph = av.filter.Graph()
    source = graph.add_abuffer(template=stream)
    tempo = graph.add("atempo", str(speed))
    sink = graph.add("abuffersink")
    source.link_to(tempo)
    tempo.link_to(sink)
    graph.configure()

    def ready():
        while True:
            try:
                yield graph.pull()
            except (av.error.BlockingIOError, av.error.EOFError):
                # Nothing more until the filter is fed again, or at all.
                return

    for frame in frames:
        graph.push(frame)
        yield from ready()
    graph.push(None)
    yield from ready()


def _smooth(values, width, axis):
    kernel = numpy.ones(width, dtype="float32") / width
    return numpy.apply_along_axis(lambda row: numpy.convolve(row, kernel, mode="same"), axis, values)


def reduce_noise(samples, reduction_db):
    """Turn down the steady noise behind a voice by about `reduction_db` decibels, leaving the voice as it is.

    The noise is turned down, never cut out: cutting it out is what makes cleaned
    recordings warble. Each frequency is judged against how loud it is when
    nobody speaks: at that level it is noise, well above it voice, and in
    between some of each, so nothing switches on and off abruptly.
    """
    if reduction_db <= 0 or len(samples) < NOISE_FRAME * 8:
        return samples
    window = numpy.hanning(NOISE_FRAME + 1)[:-1].astype("float32")
    padded = numpy.pad(samples.astype("float32"), (NOISE_FRAME, NOISE_FRAME))
    count = 1 + (len(padded) - NOISE_FRAME) // NOISE_HOP
    index = numpy.arange(NOISE_FRAME)[None, :] + NOISE_HOP * numpy.arange(count)[:, None]
    spectrum = numpy.fft.rfft(padded[index] * window, axis=1)
    magnitude = numpy.abs(spectrum)
    # The quiet moments of each frequency are the noise alone; scaled from "quietest" to "typical".
    noise = numpy.percentile(magnitude, 15, axis=0) * 2.2
    ratio = _smooth(magnitude ** 2, 5, 0) / (noise ** 2 + 1e-9)
    voice_share = numpy.clip((ratio - 1.5) / (6.0 - 1.5), 0, 1)
    voice_share = _smooth(_smooth(voice_share, 3, 0), 3, 1)
    floor = 10 ** (-reduction_db / 20)
    gain = floor + (1 - floor) * voice_share
    frequencies = numpy.fft.rfftfreq(NOISE_FRAME, 1 / SAMPLE_RATE)
    gain *= numpy.clip(frequencies / LOW_CUT_HZ, 0, 1) ** 2
    frames = numpy.fft.irfft(spectrum * gain, n=NOISE_FRAME, axis=1) * window
    cleaned = numpy.zeros(len(padded), dtype="float32")
    weight = numpy.zeros(len(padded), dtype="float32")
    numpy.add.at(cleaned, index, frames)
    numpy.add.at(weight, index, numpy.broadcast_to(window ** 2, frames.shape))
    cleaned = cleaned / numpy.maximum(weight, 1e-6)
    return numpy.clip(cleaned[NOISE_FRAME:-NOISE_FRAME], -LOUDEST, LOUDEST).astype(SAMPLE_FORMAT)


def set_level(samples, factor):
    """Make a recording louder or quieter by `factor`, never past the point where it would clip.

    `factor` None raises it as far as it goes, within reason for a recording that is nearly silent.
    The room there is is measured on the voice, not on its single loudest moment, and the few
    moments louder still are bent under the limit rather than cut off.
    """
    magnitude = numpy.abs(samples.astype("float32"))
    peak = float(numpy.percentile(magnitude, LEVEL_PEAK_PERCENTILE)) if len(samples) else 0.0
    if peak == 0:
        return samples
    most = LOUDEST / peak
    if factor is None:
        factor = min(most * AUTO_LEVEL_PEAK, AUTO_LEVEL_MAX_GAIN)
    factor = min(factor, most)
    return limit(samples.astype("float32") * factor).astype(SAMPLE_FORMAT)


def limit(samples):
    """Keep every sample within what 16 bits hold: those past the knee are bent under the limit, smoothly."""
    knee = LOUDEST * LIMIT_KNEE
    room = LOUDEST - knee
    over = numpy.abs(samples) > knee
    if not over.any():
        return samples
    bent = samples.copy()
    excess = numpy.abs(samples[over]) - knee
    bent[over] = numpy.sign(samples[over]) * (knee + room * numpy.tanh(excess / room))
    return bent


def prepare_voice(samples, level, reduction_db):
    """What is done to a recording before it is sent: cleaned first, so the noise is not made louder with the voice."""
    return set_level(reduce_noise(samples, reduction_db), level)


def input_devices():
    """Names of the microphones Windows offers, each once."""
    try:
        api = sounddevice.default.hostapi
        return [
            device["name"] for device in sounddevice.query_devices()
            if device["max_input_channels"] > 0 and device["hostapi"] == api
        ]
    except Exception:
        return []


def find_input(name):
    """The microphone of that name as sounddevice wants it named; None (the default one) if it is gone or unset."""
    try:
        api = sounddevice.default.hostapi
        for index, device in enumerate(sounddevice.query_devices()):
            if device["name"] == name and device["max_input_channels"] > 0 and device["hostapi"] == api:
                return index
    except Exception:
        pass
    return None


def play_samples(samples):
    """Play a recording held in memory without waiting for it to end."""
    sounddevice.play(samples, SAMPLE_RATE)


def encode_voice(samples, path):
    """Write a mono int16 array at SAMPLE_RATE as an Ogg/Opus file, the voice note format."""
    with av.open(path, "w", format="ogg") as container:
        stream = container.add_stream("libopus", rate=SAMPLE_RATE, layout="mono")
        frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = SAMPLE_RATE
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)


class StreamBuffer:
    """The bytes of a sound as they arrive from Telegram, read by the player as they come.

    Read like a file that cannot seek: read() waits for more until the last piece is in. Nothing of
    it is kept: what was read is let go, and nothing is written to the disk."""

    def __init__(self):
        self.data = bytearray()
        self.condition = threading.Condition()
        self.done = False
        self.error = None
        # Set when the listening stopped: the reader gets nothing more, and the sender can stop sending.
        self.abandoned = False

    def feed(self, data):
        with self.condition:
            self.data.extend(data)
            self.condition.notify_all()

    def finish(self, error=None):
        """No more is coming: all of it is in, or `error` stopped it."""
        with self.condition:
            self.done = True
            self.error = error
            self.condition.notify_all()

    def abandon(self):
        with self.condition:
            self.abandoned = True
            self.condition.notify_all()

    def read(self, size=-1):
        with self.condition:
            while not self.data and not self.done and not self.abandoned:
                self.condition.wait()
            if self.abandoned:
                return b""
            if not self.data:
                if self.error is not None:
                    raise IOError(str(self.error))
                return b""
            count = len(self.data) if size is None or size < 0 else min(size, len(self.data))
            piece = bytes(self.data[:count])
            del self.data[:count]
            return piece


class Player:
    """Plays one sound at a time on a background thread, and goes back or forward in it on request."""

    def __init__(self):
        self.thread = None
        # Set to stop the sound playing now; each sound gets a new one.
        self.halt = threading.Event()
        # While a sound plays as it arrives: where it comes from, and the sound card's stream.
        self.buffer = None
        self.output = None
        self.lock = threading.Lock()
        # Seconds of the sound heard so far, and how far back it can be taken from here.
        self.position = 0.0
        self.earliest = 0.0
        # How long the whole sound is, when the caller knows; 0 when not.
        self.duration = 0.0
        # Seconds to go forward (or back, below zero), asked for and not yet done.
        self.jump = 0.0
        self.speed = 1.0

    def is_playing(self):
        return self.thread is not None and self.thread.is_alive()

    def seek(self, seconds):
        """Go `seconds` forward, or back below zero, in the sound playing. Returns where that lands, in
        seconds of the sound; None if nothing is playing."""
        if not self.is_playing():
            return None
        with self.lock:
            self.jump += seconds
            target = max(self.earliest, self.position + self.jump)
            return min(target, self.duration) if self.duration else target

    def _play_through(self, pieces, output, halt):
        """Play pieces of sound (int16 arrays) as they are decoded, going back or forward when seek()
        asks. What was heard is kept for REWIND_SECONDS behind the place being played, and no longer."""
        kept = bytearray()
        kept_start = 0
        decoded_end = 0
        play_at = 0
        window = int(REWIND_SECONDS * SAMPLE_RATE)

        def play_what_is_there():
            nonlocal kept_start, play_at
            while not halt.is_set():
                with self.lock:
                    jump, self.jump = self.jump, 0.0
                if jump:
                    play_at = max(kept_start, play_at + int(jump * SAMPLE_RATE / self.speed))
                # What is further back than can be returned to is let go, a batch at a time.
                drop = min(play_at - window, decoded_end) - kept_start
                if drop > window // 2:
                    del kept[:drop * 2]
                    kept_start += drop
                with self.lock:
                    self.position = play_at * self.speed / SAMPLE_RATE
                    self.earliest = kept_start * self.speed / SAMPLE_RATE
                if play_at >= decoded_end:
                    return
                count = min(PLAY_BLOCK, decoded_end - play_at)
                start = (play_at - kept_start) * 2
                block = numpy.frombuffer(bytes(kept[start:start + count * 2]), dtype=SAMPLE_FORMAT)
                output.write(block.reshape(-1, 1))
                play_at += count

        for piece in pieces:
            if halt.is_set():
                break
            kept.extend(numpy.ascontiguousarray(piece, dtype=SAMPLE_FORMAT).reshape(-1).tobytes())
            decoded_end += len(piece.reshape(-1))
            play_what_is_there()
        play_what_is_there()

    def _start(self, speed):
        """A fresh stop signal for the sound about to play."""
        self.halt = threading.Event()
        with self.lock:
            self.position = self.earliest = self.jump = 0.0
            self.speed = speed

    def play(self, path, on_finished, speed=1.0):
        """on_finished(completed, error) is called from the playback thread."""
        self.stop()
        self._start(speed)
        self.thread = threading.Thread(target=self._run, args=(path, on_finished, speed, self.halt), daemon=True)
        self.thread.start()

    def _run(self, path, on_finished, speed, halt):
        output = None
        try:
            # Played as it is decoded, a piece at a time: a song of an hour never sits whole in memory.
            pieces = decode_pieces(path, speed, halt.is_set)
            with sounddevice.OutputStream(samplerate=SAMPLE_RATE, channels=1, dtype=SAMPLE_FORMAT) as output:
                self.output = output
                self._play_through(pieces, output, halt)
        except Exception as error:
            on_finished(False, None if halt.is_set() else error)
        else:
            on_finished(not halt.is_set(), None)
        finally:
            self._let_go(output)

    def play_stream(self, buffer, on_finished, speed=1.0):
        """Play a sound as its bytes arrive in `buffer`, starting with the first of them.
        on_finished(completed, error, started) is called from the playback thread; `started` says
        whether any of it was heard, so a sound that cannot be read this way can be fetched whole."""
        self.stop()
        self._start(speed)
        self.buffer = buffer
        self.thread = threading.Thread(
            target=self._run_stream, args=(buffer, on_finished, speed, self.halt), daemon=True
        )
        self.thread.start()

    def _run_stream(self, buffer, on_finished, speed, halt):
        started = False
        output = None
        try:
            resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
            # Started as soon as the kind of sound is known, not after reading far into it to be sure.
            with av.open(buffer, mode="r", options=STREAM_PROBE_OPTIONS) as container:
                stream = container.streams.audio[0]
                frames = container.decode(stream)
                if speed != 1.0:
                    frames = _at_speed(frames, stream, speed)
                def pieces():
                    nonlocal started
                    for frame in frames:
                        if halt.is_set():
                            return
                        for out in resampler.resample(frame):
                            started = True
                            yield out.to_ndarray()
                    for out in resampler.resample(None):
                        yield out.to_ndarray()

                with sounddevice.OutputStream(samplerate=SAMPLE_RATE, channels=1, dtype=SAMPLE_FORMAT) as output:
                    self.output = output
                    self._play_through(pieces(), output, halt)
        except Exception as error:
            on_finished(False, None if halt.is_set() else error, started)
        else:
            on_finished(not halt.is_set(), None, started)
        finally:
            self._let_go(output)

    def _let_go(self, output):
        # Only its own: a sound let go of while stuck must not take the next one's sound card stream with it.
        if output is not None and self.output is output:
            self.output = None

    def stop(self):
        """Stop the sound playing. Waits STOP_WAIT_SECONDS at most: a sound card or a decoder that does
        not let go is left to finish on its own, and the program goes on."""
        if self.is_playing():
            self.halt.set()
            if self.buffer is not None:
                # A read waiting for the next piece gives up at once.
                self.buffer.abandon()
            output = self.output
            if output is not None:
                try:
                    output.abort()
                except Exception:
                    pass
            sounddevice.stop()
            self.thread.join(STOP_WAIT_SECONDS)
            if self.thread.is_alive():
                logger.warning("A sound did not stop within %s seconds; it is left to end on its own", STOP_WAIT_SECONDS)
                self.thread = None
                self.output = None
        self.buffer = None


class Recorder:
    """Captures a microphone until stopped."""

    def __init__(self):
        self.stream = None
        self.chunks = []
        # Which microphone (None: the default one), and what is done to what it hears.
        self.device = None
        self.level = 1.0
        self.reduction_db = 0

    def is_recording(self):
        return self.stream is not None

    def start(self):
        self.chunks = []
        self.stream = sounddevice.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype=SAMPLE_FORMAT, callback=self._on_audio, device=self.device
        )
        self.stream.start()

    def _on_audio(self, data, frames, time, status):
        self.chunks.append(data[:, 0].copy())

    def cancel(self):
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.chunks = []

    def take(self):
        """Stop, and return what was recorded with the level and cleaning asked for applied."""
        chunks = self.chunks
        self.cancel()
        samples = numpy.concatenate(chunks) if chunks else numpy.zeros(0, dtype=SAMPLE_FORMAT)
        return prepare_voice(samples, self.level, self.reduction_db)

    def finish(self, path):
        """Stop and save the recording to `path`; returns its length in seconds."""
        samples = self.take()
        if len(samples):
            encode_voice(samples, path)
        return len(samples) / SAMPLE_RATE
