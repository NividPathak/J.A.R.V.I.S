"""Wake word — "Hey Jarvis".

openWakeWord with its pretrained `hey_jarvis` model: free, open source, runs on
CPU, no account and no per-call cost. Nothing leaves the machine.

A wake word is only worth having if it stays quiet. A detector that fires at the
television is worse than pressing a key, because you stop trusting it and then
stop using it — so the threshold here is deliberately conservative, and
`measure()` exists to re-check it against real audio rather than assume.
"""
import logging
import queue
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger("jarvis.wake")

MODEL = "hey_jarvis"
PHRASE = "Hey Jarvis"
SAMPLE_RATE = 16000
#: openWakeWord expects 80ms frames of int16 at 16kHz.
FRAME = 1280

#: Synthesised "hey jarvis" scores 0.83-0.93; unrelated speech scores 0.000.
#: 0.5 sits in the middle of a very wide gap. Raise it if the room is noisy.
THRESHOLD = 0.5
#: Ignore further detections while a request is being handled, so the assistant
#: never wakes itself on its own reply.
COOLDOWN = 3.0

ACK_SOUND = Path("/System/Library/Sounds/Tink.aiff")


@dataclass
class Detection:
    score: float
    waited: float


class WakeWord:
    """Holds the loaded model — construction is the expensive part, so build
    once and reuse."""

    def __init__(self, threshold: float = THRESHOLD, model: str = MODEL):
        from openwakeword.model import Model

        self.threshold = threshold
        # onnx rather than tflite: tflite wheels are inconsistent on Apple
        # Silicon, and this model is small enough that it makes no odds.
        self._model = Model(wakeword_models=[model], inference_framework="onnx")
        self._key = model

    def wait(self, timeout: float | None = None, on_start=None) -> Detection | None:
        """Block until the phrase is heard. None if `timeout` elapses first."""
        import sounddevice as sd

        frames: queue.Queue = queue.Queue()
        self._model.reset()
        started = time.monotonic()

        def on_audio(indata, _n, _t, status):
            if status:
                log.debug("audio status: %s", status)
            frames.put(indata.copy())

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                            blocksize=FRAME, callback=on_audio):
            if on_start:
                on_start()
            while True:
                if timeout and time.monotonic() - started > timeout:
                    return None
                try:
                    block = frames.get(timeout=0.5)
                except queue.Empty:
                    continue
                score = float(self._model.predict(block.flatten())[self._key])
                if score >= self.threshold:
                    # Clear state so the tail of this utterance can't re-trigger.
                    self._model.reset()
                    return Detection(score=score, waited=time.monotonic() - started)

    def measure(self, audio: np.ndarray) -> float:
        """Peak score over a clip — for checking the threshold against real
        recordings rather than trusting the default."""
        self._model.reset()
        peak = 0.0
        for i in range(0, max(len(audio) - FRAME, 0), FRAME):
            peak = max(peak, float(self._model.predict(audio[i:i + FRAME])[self._key]))
        return peak


def acknowledge() -> None:
    """Tell the user they were heard, and wait for the tone to finish.

    Without the tone you talk into a void and can't tell whether it woke.
    Without the *wait*, capture starts while the tone is still sounding, the
    detector counts it as speech, and the recording runs on well past the point
    you stopped talking.
    """
    if ACK_SOUND.exists():
        subprocess.run(["afplay", str(ACK_SOUND)], check=False, timeout=5)


def available() -> tuple[bool, str]:
    try:
        import openwakeword  # noqa: F401
        from openwakeword.model import Model

        Model(wakeword_models=[MODEL], inference_framework="onnx")
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
