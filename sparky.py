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

def play_audio(audio: np.ndarray, sample_rate: int = 22050):
    sd.play(audio, samplerate=sample_rate)
    sd.wait()


class SparkyVoice:
    """
    Character voice for Sparky.
    Backend priority: ElevenLabs → Kokoro → Piper
    All output passes through the robot audio effect.
    """

    SAMPLE_RATE = 22050
    ELEVENLABS_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"  # Aria

    def __init__(self):
        self.startup_chime = _generate_startup_chime(self.SAMPLE_RATE)
        self.thinking_beep = _generate_thinking_beep(self.SAMPLE_RATE)
        self._thinking_active = False
        self._thinking_thread = None

        self.elevenlabs_available = False
        try:
            from elevenlabs.client import ElevenLabs
            self._el_client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
            self._el_client.voices.get_all()
            self.elevenlabs_available = True
            print("[Sparky] ElevenLabs voice ready ✓")
        except Exception as e:
            print(f"[Sparky] ElevenLabs unavailable ({e}), trying Kokoro...")

        self.kokoro_available = False
        if not self.elevenlabs_available:
            try:
                from kokoro_onnx import Kokoro
                self._kokoro = Kokoro("kokoro-v0_19.onnx", "voices.bin")
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
        self.say("Hello! I'm Sparky. I'm ready to help!")

    def start_thinking(self):
        """Begin pulsing thinking beeps. Call when Gemini starts processing."""
        self._thinking_active = True
        def _pulse():
            while self._thinking_active:
                play_audio(self.thinking_beep, self.SAMPLE_RATE)
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
            if self.elevenlabs_available:
                self._say_elevenlabs(text)
            elif self.kokoro_available:
                self._say_kokoro(text)
            else:
                self._say_piper(text)
        except Exception as e:
            print(f"[Sparky] TTS error: {e} — trying Piper fallback")
            try:
                self._say_piper(text)
            except Exception:
                pass

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

    def _say_elevenlabs(self, text: str):
        from elevenlabs import VoiceSettings
        audio_bytes = self._el_client.text_to_speech.convert(
            voice_id=self.ELEVENLABS_VOICE_ID,
            text=text,
            model_id="eleven_turbo_v2_5",
            voice_settings=VoiceSettings(
                stability=0.45,
                similarity_boost=0.80,
                style=0.25,
                use_speaker_boost=True,
            ),
            output_format="pcm_22050",
        )
        audio = np.frombuffer(b"".join(audio_bytes), dtype=np.int16).astype(np.float32) / 32768.0
        audio = apply_robot_effect(audio, self.SAMPLE_RATE)
        play_audio(audio, self.SAMPLE_RATE)

    def _say_kokoro(self, text: str):
        samples, sr = self._kokoro.create(text, voice="af_sky", speed=0.95, lang="en-us")
        audio = np.array(samples, dtype=np.float32)
        if sr != self.SAMPLE_RATE:
            from scipy.signal import resample_poly
            from math import gcd
            g = gcd(self.SAMPLE_RATE, sr)
            audio = resample_poly(audio, self.SAMPLE_RATE // g, sr // g)
        audio = apply_robot_effect(audio, self.SAMPLE_RATE)
        play_audio(audio, self.SAMPLE_RATE)

    def _say_piper(self, text: str):
        import subprocess, tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
        subprocess.run([
            "piper", "--model", "en_US-amy-medium",
            "--length-scale", "1.15",
            "--output_file", tmp_path,
        ], input=text.encode(), capture_output=True)
        audio, sr = sf.read(tmp_path)
        audio = apply_robot_effect(audio.astype(np.float32), sr)
        play_audio(audio, sr)
        os.unlink(tmp_path)
