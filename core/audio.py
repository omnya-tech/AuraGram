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
    """Captures the default microphone until stopped."""

    def __init__(self):
        self.stream = None
        self.chunks = []

    def is_recording(self):
        return self.stream is not None

    def start(self):
        self.chunks = []
        self.stream = sounddevice.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype=SAMPLE_FORMAT, callback=self._on_audio
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

    def finish(self, path):
        """Stop and save the recording to `path`; returns its length in seconds."""
        chunks = self.chunks
        self.cancel()
        samples = numpy.concatenate(chunks) if chunks else numpy.zeros(0, dtype=SAMPLE_FORMAT)
        if len(samples):
            encode_voice(samples, path)
        return len(samples) / SAMPLE_RATE
