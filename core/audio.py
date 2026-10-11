"""Voice message playback and recording.

Needs the optional packages av, numpy and sounddevice; `AVAILABLE` says
whether they could be loaded.
"""
import threading

try:
    import av
    import numpy
    import sounddevice
    AVAILABLE = True
except Exception:
    AVAILABLE = False

# What Telegram voice notes use: Opus, mono, 48 kHz.
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


def decode(path, speed=1.0):
    """Read any audio file into a mono int16 array at SAMPLE_RATE.

    `speed` shortens or stretches it without changing how high the voice sounds.
    """
    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    chunks = []
    with av.open(path) as container:
        stream = container.streams.audio[0]
        if speed == 1.0:
            frames = container.decode(stream)
        else:
            frames = _at_speed(container.decode(stream), stream, speed)
        for frame in frames:
            chunks.extend(out.to_ndarray()[0] for out in resampler.resample(frame))
        chunks.extend(out.to_ndarray()[0] for out in resampler.resample(None))
    if not chunks:
        return numpy.zeros(0, dtype=SAMPLE_FORMAT)
    return numpy.concatenate(chunks)


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
    """
    peak = int(numpy.abs(samples.astype("int32")).max()) if len(samples) else 0
    if peak == 0:
        return samples
    most = LOUDEST / peak
    if factor is None:
        factor = min(most * AUTO_LEVEL_PEAK, AUTO_LEVEL_MAX_GAIN)
    factor = min(factor, most)
    return (samples.astype("float32") * factor).astype(SAMPLE_FORMAT)


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


class Player:
    """Plays one file at a time on a background thread."""

    def __init__(self):
        self.thread = None
        self.stopped = False

    def is_playing(self):
        return self.thread is not None and self.thread.is_alive()

    def play(self, path, on_finished, speed=1.0):
        """on_finished(completed, error) is called from the playback thread."""
        self.stop()
        self.stopped = False
        self.thread = threading.Thread(target=self._run, args=(path, on_finished, speed), daemon=True)
        self.thread.start()

    def _run(self, path, on_finished, speed):
        try:
            samples = decode(path, speed)
            if not self.stopped:
                sounddevice.play(samples, SAMPLE_RATE)
                sounddevice.wait()
        except Exception as error:
            on_finished(False, error)
        else:
            on_finished(not self.stopped, None)

    def stop(self):
        if self.is_playing():
            self.stopped = True
            sounddevice.stop()
            self.thread.join()


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
