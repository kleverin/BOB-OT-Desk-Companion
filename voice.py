import json
import sys
import termios
import threading
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from pynput import keyboard as pynkb
import ollama

RECORD_RATE = 48000   # native ALSA rate
WHISPER_RATE = 16000  # faster-whisper expects 16kHz
CHANNELS = 2          # hw:1,4 is stereo
MIC_DEVICE = 6        # amd-soundwire hw:1,4 — only device with live signal

_INTENT_SYSTEM = """You are an intent classifier for a robot assistant called Sparky.
Given a voice command, classify it into one of these modes:

- identify: "what do you see", "what's on my desk", "what is this", "look at this"
- tutor: "help me", "explain this", "how do I solve", "teach me", "show me how", "what is"
- track: "follow me", "watch me", "track me"
- clean: "clean up", "tidy this", "clean my desk", "pick this up"
- idle: "stop", "rest", "never mind", "that's enough"

Respond with ONLY valid JSON, no explanation or markdown:
{"mode": "<mode>", "target": "<full question text, or empty string>"}

If unclear, use "idle"."""


class VoiceModule:
    """faster-whisper STT + Ollama llama3.2:3b intent routing."""

    def __init__(self, model_size: str = "base"):
        print("[Voice] Loading faster-whisper...")
        self._model = WhisperModel(model_size, device="cpu", compute_type="int8")
        print("[Voice] Whisper ready ✓")

    def listen_once(self) -> dict:
        """Block until spacebar held, record, transcribe, classify intent.

        Returns dict with keys "mode" and "target".
        """
        print("[Voice] Hold SPACE to speak...")
        fd, old_settings = self._disable_echo()
        try:
            self._wait_for_press()
            print("[Voice] Listening... (release SPACE when done)", flush=True)
            audio = self._record_while_held()
            print("[Voice] Processing...", flush=True)
        finally:
            self._restore_echo(fd, old_settings)
            print()  # newline after held spaces
        if audio is None or len(audio) < RECORD_RATE * 0.3:
            return {"mode": "idle", "target": ""}
        transcript = self._transcribe(audio)
        print(f"[Voice] Heard: \"{transcript}\"")
        if not transcript.strip():
            return {"mode": "idle", "target": ""}
        return self._classify_intent(transcript)

    def _disable_echo(self):
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        new = termios.tcgetattr(fd)
        new[3] &= ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSANOW, new)
        return fd, old

    def _restore_echo(self, fd, old_settings):
        termios.tcsetattr(fd, termios.TCSANOW, old_settings)

    def _wait_for_press(self):
        event = threading.Event()
        def on_press(key):
            if key == pynkb.Key.space:
                event.set()
                return False
        with pynkb.Listener(on_press=on_press):
            event.wait()

    def _record_while_held(self) -> np.ndarray | None:
        chunks = []
        released = threading.Event()

        def on_release(key):
            if key == pynkb.Key.space:
                released.set()
                return False

        listener = pynkb.Listener(on_release=on_release)
        listener.start()

        with sd.InputStream(device=MIC_DEVICE, samplerate=RECORD_RATE, channels=CHANNELS, dtype="float32") as stream:
            while not released.is_set():
                data, _ = stream.read(1024)
                chunks.append(data.copy())
                rms = float(np.sqrt(np.mean(data ** 2)))
                level = int(rms * 40)
                bar = "█" * min(level, 20)
                print(f"\r  mic: {bar:<20} ({rms:.3f})", end="", flush=True)

        listener.stop()
        if not chunks:
            return None
        audio = np.concatenate(chunks, axis=0)
        return audio.mean(axis=1) if audio.ndim > 1 else audio.flatten()

    def _transcribe(self, audio: np.ndarray) -> str:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(WHISPER_RATE, RECORD_RATE)
        audio = resample_poly(audio, WHISPER_RATE // g, RECORD_RATE // g).astype(np.float32)
        segments, _ = self._model.transcribe(audio, language="en", beam_size=1)
        return " ".join(s.text.strip() for s in segments).strip()

    def _classify_intent(self, transcript: str) -> dict:
        try:
            response = ollama.chat(
                model="llama3.2:3b",
                messages=[
                    {"role": "system", "content": _INTENT_SYSTEM},
                    {"role": "user", "content": transcript},
                ],
                options={"temperature": 0.0},
            )
            raw = response["message"]["content"].strip()
            if "```" in raw:
                raw = raw.split("```")[1].lstrip("json").strip()
            intent = json.loads(raw)
            intent.setdefault("target", "")
            if intent.get("mode") not in ("identify", "tutor", "track", "clean", "idle"):
                intent["mode"] = "idle"
            return intent
        except Exception as e:
            print(f"[Voice] Intent classification error: {e}")
            return {"mode": "idle", "target": ""}
