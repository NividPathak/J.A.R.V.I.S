"""Speech in and out.

Whisper via MLX (Apple Silicon GPU) for transcription, macOS `say` for output.
Both local and free, so a voice turn costs nothing and works offline.

Capture stops on silence rather than a fixed duration: a fixed window either
truncates a long request or leaves you waiting after a short one, and both feel
broken. Energy-based VAD is crude but the alternative — a neural VAD — is a
dependency and a model load to solve a problem that a threshold handles for
someone speaking deliberately at a laptop.
"""
import logging
import queue
import subprocess
import sys
import time
from dataclasses import dataclass

import numpy as np

log = logging.getLogger("jarvis.speech")

SAMPLE_RATE = 16000  # what Whisper expects; resampling here avoids doing it later
BLOCK = 1600  # 100ms
#: RMS below this counts as silence. Tuned for a laptop mic in a quiet room;
#: `calibrate()` adapts it to the actual room.
DEFAULT_SILENCE = 0.012
SILENCE_TO_STOP = 1.2  # seconds of quiet that end a phrase
MAX_SECONDS = 20.0
MIN_SPEECH = 0.35  # ignore a cough or a key press

MODEL = "mlx-community/whisper-base-mlx"


@dataclass
class Heard:
    text: str
    seconds: float
    transcribe_ms: float

    def __bool__(self) -> bool:
        return bool(self.text.strip())


def calibrate(seconds: float = 1.0) -> float:
    """Measure room noise and set the silence threshold above it.

    A fixed threshold either clips speech in a noisy room or never stops in a
    quiet one; measuring once at startup costs a second and avoids both.
    """
    import sounddevice as sd

    audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()
    noise = float(np.sqrt(np.mean(audio**2)))
    return max(DEFAULT_SILENCE, noise * 3.0)


def record(threshold: float = DEFAULT_SILENCE, max_seconds: float = MAX_SECONDS) -> np.ndarray:
    """Capture until the speaker stops. Returns mono float32 at 16kHz."""
    import sounddevice as sd

    blocks: list[np.ndarray] = []
    q: queue.Queue = queue.Queue()

    def on_audio(indata, _frames, _t, status):
        if status:
            log.debug("audio status: %s", status)
        q.put(indata.copy())

    started = time.monotonic()
    speech_started = False
    quiet_since: float | None = None

    with sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="float32",
        blocksize=BLOCK, callback=on_audio,
    ):
        while True:
            try:
                block = q.get(timeout=0.5)
            except queue.Empty:
                continue
            blocks.append(block)
            level = float(np.sqrt(np.mean(block**2)))
            now = time.monotonic()

            if level > threshold:
                speech_started, quiet_since = True, None
            elif speech_started:
                quiet_since = quiet_since or now
                if now - quiet_since >= SILENCE_TO_STOP:
                    break

            if now - started >= max_seconds:
                log.info("hit max recording length")
                break

    return np.concatenate(blocks).flatten() if blocks else np.zeros(0, dtype="float32")


def transcribe(audio: np.ndarray, model: str = MODEL) -> Heard:
    """Whisper on the GPU. Returns empty text for anything too short to be speech."""
    import mlx_whisper

    seconds = len(audio) / SAMPLE_RATE
    if seconds < MIN_SPEECH:
        return Heard(text="", seconds=seconds, transcribe_ms=0.0)

    started = time.perf_counter()
    result = mlx_whisper.transcribe(audio, path_or_hf_repo=model, fp16=True)
    return Heard(
        text=(result.get("text") or "").strip(),
        seconds=seconds,
        transcribe_ms=(time.perf_counter() - started) * 1000,
    )


def warm(model: str = MODEL) -> None:
    """Load Whisper now rather than on the first thing the user says.

    The model load is ~4s and happens inside the first `transcribe`, which is
    exactly the moment someone is waiting for an answer. Doing it at startup —
    while the banner is still printing — makes the first turn as fast as the
    rest. Failure here is not fatal: the load simply happens later.
    """
    import numpy as np_

    try:
        transcribe(np_.zeros(int(SAMPLE_RATE * 0.5), dtype="float32"), model=model)
    except Exception as e:
        log.debug("whisper warm-up skipped: %s", e)


def listen(threshold: float = DEFAULT_SILENCE) -> Heard:
    return transcribe(record(threshold))


def speak(text: str, voice: str = "Daniel", rate: int = 190, wait: bool = True) -> None:
    """Read aloud via macOS `say`.

    Blocks by default: overlapping replies are unintelligible, and in a voice
    loop the next capture would otherwise record JARVIS talking to itself.
    """
    if not text.strip():
        return
    args = ["say", "-v", voice, "-r", str(rate), text]
    if wait:
        subprocess.run(args, check=False)
    else:
        subprocess.Popen(args)


def available() -> tuple[bool, str]:
    """Whether voice can run here, and why not if it can't."""
    try:
        import sounddevice as sd

        if sd.query_devices(kind="input") is None:
            return False, "no audio input device"
    except Exception as e:
        return False, f"audio unavailable: {e}"
    if sys.platform != "darwin":
        return False, "TTS uses macOS `say`"
    return True, ""
