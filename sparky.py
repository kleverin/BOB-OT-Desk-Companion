import os, io, time, threading
import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy import signal


def apply_robot_effect(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Subtle chorus + mild metallic shimmer. Adds texture without killing warmth."""
    delay_samples = int(sample_rate * 0.012)
    delayed = np.zeros_like(audio)
    delayed[delay_samples:] = audio[:-delay_samples] * 0.18
    chorused = audio + delayed

    b, a = signal.butter(2, [1400 / (sample_rate / 2), 2200 / (sample_rate / 2)], btype='band')
    resonance = signal.lfilter(b, a, chorused) * 0.12
    result = chorused + resonance

    peak = np.max(np.abs(result))
    if peak > 0:
        result = result / peak * 0.92
    return result.astype(np.float32)


def _generate_startup_chime(sr: int = 22050) -> np.ndarray:
    """Two rising tones — robot powering on."""
    duration = 0.18
    t = np.linspace(0, duration, int(sr * duration))
    tone1 = np.sin(2 * np.pi * 880 * t) * np.exp(-t * 8) * 0.4
    tone2 = np.sin(2 * np.pi * 1320 * t) * np.exp(-t * 8) * 0.3
    gap = np.zeros(int(sr * 0.08))
    return np.concatenate([tone1, gap, tone2]).astype(np.float32)

def _generate_thinking_beep(sr: int = 22050) -> np.ndarray:
    """Soft pulsing beep — Sparky is thinking."""
    t = np.linspace(0, 0.12, int(sr * 0.12))
    return (np.sin(2 * np.pi * 660 * t) * np.exp(-t * 15) * 0.25).astype(np.float32)

SPEAKER_DEVICE = 7  # amd-soundwire hw:3,2 — laptop speaker

def play_audio(audio: np.ndarray, sample_rate: int = 22050):
    audio = audio.squeeze()  # remove batch dim if present
    if audio.ndim == 1:
        audio = np.stack([audio, audio], axis=1)  # mono → stereo for hw:3,0
    sd.play(audio, samplerate=sample_rate, device=SPEAKER_DEVICE)
    sd.wait()


class SparkyVoice:
    """
    Character voice for Sparky.
    Backend priority: ElevenLabs → Kokoro → Piper
    All output passes through the robot audio effect.
    """

    SAMPLE_RATE = 48000

    def __init__(self):
        self.startup_chime = _generate_startup_chime(self.SAMPLE_RATE)
        self.thinking_beep = _generate_thinking_beep(self.SAMPLE_RATE)
        self._thinking_active = False
        self._thinking_thread = None

        self.elevenlabs_available = False

        self.kokoro_available = False
        try:
            from kokoro_onnx import Kokoro
            import os as _os
            _model_dir = _os.path.dirname(_os.path.abspath(__file__))
            self._kokoro = Kokoro(
                _os.path.join(_model_dir, "kokoro.onnx"),
                _os.path.join(_model_dir, "voices", "voices-v1.0.bin"),
            )
            self.kokoro_available = True
            print("[Sparky] Kokoro TTS ready ✓")
        except Exception as e:
            print(f"[Sparky] Kokoro unavailable ({e}), falling back to Piper.")

        if not self.elevenlabs_available and not self.kokoro_available:
            print("[Sparky] Using Piper TTS (last resort).")

    def startup(self):
        """Play startup chime then introduce Sparky. Call once at boot."""
        play_audio(self.startup_chime, self.SAMPLE_RATE)
        time.sleep(0.1)
        self.say("Hey guys, how is it going?")

    def start_thinking(self):
        """Begin pulsing thinking beeps. Call when Gemini starts processing."""
        self._thinking_active = True
        def _pulse():
            while self._thinking_active:
                try:
                    play_audio(self.thinking_beep, self.SAMPLE_RATE)
                except Exception:
                    pass
                time.sleep(0.55)
        self._thinking_thread = threading.Thread(target=_pulse, daemon=True)
        self._thinking_thread.start()

    def stop_thinking(self):
        """Stop thinking beeps. Call just before speaking the first sentence."""
        self._thinking_active = False
        if self._thinking_thread:
            self._thinking_thread.join(timeout=0.6)

    def say(self, text: str):
        """Speak text as Sparky. Blocks until speech is complete."""
        if not text.strip():
            return
        try:
            if self.kokoro_available:
                self._say_kokoro(text)
            else:
                self._say_piper(text)
        except Exception as e:
            print(f"[Sparky] TTS failed: {e}")

    def say_streamed(self, sentence_generator):
        """
        Speak sentences from a generator as they arrive (for Gemini streaming).
        Automatically stops thinking beeps before the first sentence.
        """
        first = True
        for sentence in sentence_generator:
            if first:
                self.stop_thinking()
                first = False
            self.say(sentence)

    def _say_kokoro(self, text: str):
        samples, sr = self._kokoro.create(text, voice="af_sky", speed=0.95, lang="en-us")
        audio = np.array(samples, dtype=np.float32).squeeze()
        if sr != self.SAMPLE_RATE:
            from scipy.signal import resample_poly
            from math import gcd
            g = gcd(self.SAMPLE_RATE, sr)
            audio = resample_poly(audio, self.SAMPLE_RATE // g, sr // g)
        audio = apply_robot_effect(audio, self.SAMPLE_RATE)
        play_audio(audio, self.SAMPLE_RATE)

    def _say_piper(self, text: str):
        import subprocess
        subprocess.run(
            ["espeak-ng", "-s", "145", "-p", "60", "-a", "200", text],
            check=True,
        )
