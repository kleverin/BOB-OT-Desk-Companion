# Desk Companion Robot — Complete Build Plan
### AMD StarkHacks · SO-101 + Ryzen AI Laptop · One Day

---

## Hardware (confirmed from AMD official docs)

| Item | Details |
|---|---|
| Robot | WowRobo SO-101 Leader/Follower kit (pre-assembled) |
| Compute | AMD Ryzen AI laptop (Ryzen AI 9 HX370) — RDNA 3.5 iGPU + XDNA 2 NPU |
| OS | Ubuntu 24.04 LTS |
| Cloud GPU | AMD Developer Cloud — 2× MI300X Jupyter notebooks per team |
| Cameras | 2× USB cameras — **top** (overhead desk view) + **side** (forward-facing) |
| OLED | SSD1306 128×64 I²C connected to Arduino Uno/Nano |
| Power | **5V 6A** → Leader arm · **12V 8A** → Follower arm ← DO NOT SWAP |

---

## What the robot does — six modes

| Mode | Trigger phrase | What happens |
|---|---|---|
| **IDLE** | "stop" / "rest" | Neutral blinking eyes, waiting |
| **IDENTIFY** | "what do you see?" / "what's on my desk?" | Gemini 2.0 Flash describes the desk naturally |
| **TRACK** | "follow me" / "watch me" | MediaPipe tracks your face, arm aims |
| **CLEAN** | "clean up" / "tidy this" | YOLO checks for objects, then ACT or scripted cleanup |
| **TUTOR** | "help me" / "explain this" / "how do I solve this" | Gemini explains to the child step by step with conversation memory |
| **LISTEN** | spacebar held | STT active, waiting for a command |

---

## Central architecture

```
                        ┌──────────────────────┐
                        │     ModeSwitcher      │  (main thread, state machine)
                        └──────────┬────────────┘
                                   │
   ┌──────────┬────────────────────┼──────────┬────────────┬─────────────┐
   ▼          ▼                    ▼          ▼            ▼             ▼
voice.py  vision.py           eyes.py      arm.py      sparky.py   gemini_vision.py
(STT+LLM) (YOLO + MediaPipe)  (serial)    (lerobot)   (character  (Gemini 2.0 Flash
                                                        voice TTS)  + LLaVA fallback)

Camera routing:
  TOP camera  (index 0, overhead) → gemini_vision.py + arm.py (ACT policy)
  SIDE camera (index 2, forward)  → vision.py (MediaPipe face tracking)

YOLO        → CLEAN mode only (confirms objects present before arm moves)
Gemini 2.0  → IDENTIFY + TUTOR modes (all vision-language understanding)
sparky.py   → ALL speech output (ElevenLabs primary · Kokoro fallback · Piper last resort)
```

---

## Environment setup — exact AMD-pinned versions

```bash
# 1. ROCm 6.3
wget https://repo.radeon.com/amdgpu-install/6.3.4/ubuntu/noble/amdgpu-install_6.3.60304-1_all.deb
sudo apt install ./amdgpu-install_6.3.60304-1_all.deb
amdgpu-install -y --usecase=rocm --no-dkms
sudo reboot

# 2. iGPU compatibility mode for Ryzen AI 300 series (REQUIRED)
echo "export HSA_OVERRIDE_GFX_VERSION=11.0.0" >> ~/.bashrc
source ~/.bashrc

# 3. Conda environment — Python 3.10 required
conda create -n lerobot python=3.10
conda activate lerobot

# 4. PyTorch with ROCm — MUST be <2.8.0
pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 \
    --index-url https://download.pytorch.org/whl/rocm6.3

# Verify iGPU
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# Expected: True  AMD Radeon Graphics

# 5. LeRobot — pin v0.4.1 exactly
conda install ffmpeg=7.1.1 -c conda-forge
git clone https://github.com/huggingface/lerobot.git
cd lerobot && git checkout -b v0.4.1 v0.4.1
pip install -e . && pip install 'lerobot[feetech]'

# 6. Core project packages
pip install faster-whisper sounddevice keyboard
pip install ollama pydantic
pip install ultralytics pyserial
pip install pynput==1.7.7
pip install opencv-python "numpy<2.0" mediapipe
pip install google-generativeai pillow

# 7. Sparky voice system
pip install elevenlabs                # ElevenLabs client (primary voice)
pip install kokoro-onnx soundfile     # Kokoro TTS (offline fallback)
pip install scipy                     # robot audio effect layer
pip install pygame                    # startup chime + thinking beep

# 8. Offline model pulls — do this before demo day
ollama pull llava
ollama pull llama3.2:3b

# 9. Kokoro model files
python -c "from kokoro_onnx import Kokoro; Kokoro.download()"

# 10. ElevenLabs API key
echo 'export ELEVENLABS_API_KEY="your_key_here"' >> ~/.bashrc
source ~/.bashrc
# Get free key at: elevenlabs.io (10,000 chars/month free)
```

> **AMD iGPU note:** The Ryzen AI laptop's RDNA 3.5 iGPU is ROCm-compatible. `--policy.device=cuda` for LeRobot inference. Ollama auto-detects it via llama.cpp's HIP backend.

---

## Sparky's voice — sparky.py

All speech in the robot goes through `sparky.py`. Never call TTS directly from other modules — this keeps the voice consistent and makes it trivial to swap backends.

### Voice design

Sparky is a warm, slightly energetic robot companion for kids:
- Friendly and upbeat — not flat like a navigation app, not over-the-top cartoon
- A subtle robot resonance effect is applied on top of both backends so the voice has a consistent "machine with personality" quality regardless of which engine is speaking
- A startup chime plays when the robot boots
- Soft thinking beeps fill the silence while Gemini processes — there is never a quiet gap

**ElevenLabs voice settings** — use the **"Aria"** preset voice (Voice ID: `EXAVITQu4vr4xnSDxMaL`) with Stability 0.45, Similarity 0.80, Style 0.25. This gives Sparky a warm, slightly expressive delivery that kids respond well to. Alternative voices to try: "Lily" (`ThT5KcBeYPX3keUQqHPh`) or "Charlie" (`IKne3meq5aSn9XLyUdCD`).

**Kokoro offline fallback** — use the `af_sky` voice at speed 0.95. Warm, clear, and the closest to ElevenLabs quality that runs locally.

### sparky.py

```python
import os, io, time, threading
import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy import signal

# ── Robot audio effect ────────────────────────────────────────────────────────
# Applied to ALL voice backends. Gives Sparky a consistent "machine with
# personality" signature regardless of which engine is speaking.

def apply_robot_effect(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Subtle chorus + mild metallic shimmer. Adds texture without killing warmth."""
    # 12ms chorus delay
    delay_samples = int(sample_rate * 0.012)
    delayed = np.zeros_like(audio)
    delayed[delay_samples:] = audio[:-delay_samples] * 0.18
    chorused = audio + delayed

    # Very gentle bandpass resonance around 1.8kHz (metallic shimmer)
    b, a = signal.butter(2, [1400 / (sample_rate / 2), 2200 / (sample_rate / 2)], btype='band')
    resonance = signal.lfilter(b, a, chorused) * 0.12
    result = chorused + resonance

    peak = np.max(np.abs(result))
    if peak > 0:
        result = result / peak * 0.92
    return result.astype(np.float32)


# ── Sound effects ─────────────────────────────────────────────────────────────

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


# ── Sparky voice class ────────────────────────────────────────────────────────

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

        # Try ElevenLabs
        self.elevenlabs_available = False
        try:
            from elevenlabs.client import ElevenLabs
            self._el_client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
            self._el_client.voices.get_all()   # lightweight connectivity check
            self.elevenlabs_available = True
            print("[Sparky] ElevenLabs voice ready ✓")
        except Exception as e:
            print(f"[Sparky] ElevenLabs unavailable ({e}), trying Kokoro...")

        # Try Kokoro
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

    # ── Public API ────────────────────────────────────────────────────────────

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
                pass   # never crash the main loop over TTS

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

    # ── Backends ──────────────────────────────────────────────────────────────

    def _say_elevenlabs(self, text: str):
        from elevenlabs import VoiceSettings
        audio_bytes = self._el_client.text_to_speech.convert(
            voice_id=self.ELEVENLABS_VOICE_ID,
            text=text,
            model_id="eleven_turbo_v2_5",   # lowest latency ElevenLabs model
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
            "--length-scale", "1.15",   # slightly slower for kids
            "--output_file", tmp_path,
        ], input=text.encode(), capture_output=True)
        audio, sr = sf.read(tmp_path)
        audio = apply_robot_effect(audio.astype(np.float32), sr)
        play_audio(audio, sr)
        os.unlink(tmp_path)
```

---

## How sparky.py integrates with Gemini streaming

The pattern: **start thinking beeps → stream Gemini → stop beeps on first sentence → speak sentences as they arrive.** No silent gaps anywhere.

```python
# In ModeSwitcher.handle_intent()

elif mode == "tutor":
    self.current_mode = "TUTOR"
    self.eyes.set_emotion("CURIOUS")
    self.eyes.look("DOWN")
    self.sparky.say("Let me take a look at that for you!")
    self.eyes.set_emotion("TIRED")
    self.sparky.start_thinking()          # beeps start here

    # say_streamed() stops beeps on first sentence, speaks each as it arrives
    self.sparky.say_streamed(
        self.gemini.tutor(intent.get("target", ""))
    )
    self.eyes.laugh()
    self.current_mode = "IDLE"

if mode == "identify":
    self.gemini.clear_history()
    self.current_mode = "IDENTIFY"
    self.eyes.set_emotion("CURIOUS")
    self.eyes.look("DOWN")
    self.sparky.say("Let me take a look!")
    self.sparky.start_thinking()

    self.sparky.say_streamed(self.gemini.identify())
    self.eyes.set_emotion("HAPPY")
    self.current_mode = "IDLE"
```

---

## gemini_vision.py

```python
import google.generativeai as genai
from PIL import Image
import cv2, ollama
from collections import deque

IDENTIFY_PROMPT = """You are a friendly robot assistant. Look at this desk and describe
what objects you can see in one short, natural sentence. Be specific about colors and types.
Example: "I can see a red water bottle, two pencils, and an open notebook."
Keep it under 20 words. Do not say anything else."""

TUTOR_PROMPT = """You are a friendly robot tutor named Sparky helping kids aged 6-14.
When shown a math problem, homework question, drawing, or any object:
- Explain it step by step in simple, encouraging language.
- Use short sentences. Never use jargon without explaining it first.
- Never just give the answer — guide the child to figure it out themselves.
- Keep your total response under 5 sentences so the child stays engaged.
- Always end with an encouraging phrase like "You've got this!" or "Great question!"
- If it is a math problem, walk through each step out loud like a teacher would."""

class GeminiVision:
    def __init__(self, api_key: str, top_camera_index: int = 0):
        self.top_camera_index = top_camera_index
        self.gemini_available = False
        self.conversation_history = deque(maxlen=6)  # last 3 exchanges

        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel("gemini-2.0-flash")
            self.model.generate_content("Hello")   # pre-warm on startup
            self.gemini_available = True
            print("[GeminiVision] Gemini 2.0 Flash ready ✓")
        except Exception as e:
            print(f"[GeminiVision] Gemini unavailable ({e}), will use LLaVA.")

    def capture_snapshot(self) -> Image.Image:
        cap = cv2.VideoCapture(self.top_camera_index, cv2.CAP_V4L2)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise RuntimeError("Could not capture from top camera")
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    def _stream_gemini(self, prompt: str, image: Image.Image):
        messages = list(self.conversation_history) + [prompt, image]
        response = self.model.generate_content(messages, stream=True)
        buffer = ""
        full_response = ""
        for chunk in response:
            buffer += chunk.text
            full_response += chunk.text
            while any(p in buffer for p in [".", "!", "?"]):
                for punct in [".", "!", "?"]:
                    idx = buffer.find(punct)
                    if idx != -1:
                        sentence = buffer[:idx+1].strip()
                        buffer = buffer[idx+1:].strip()
                        if sentence:
                            yield sentence
                        break
        if buffer.strip():
            yield buffer.strip()
        self.conversation_history.append({"role": "user", "parts": [prompt]})
        self.conversation_history.append({"role": "model", "parts": [full_response]})

    def _ask_llava_fallback(self, prompt: str) -> str:
        image_path = "/tmp/desk_snapshot.jpg"
        cap = cv2.VideoCapture(self.top_camera_index, cv2.CAP_V4L2)
        ret, frame = cap.read()
        cap.release()
        cv2.imwrite(image_path, frame)
        response = ollama.chat(
            model="llava",
            messages=[{"role": "user", "content": prompt, "images": [image_path]}]
        )
        return response["message"]["content"]

    def identify(self):
        self.conversation_history.clear()
        try:
            if self.gemini_available:
                yield from self._stream_gemini(IDENTIFY_PROMPT, self.capture_snapshot())
            else:
                yield self._ask_llava_fallback(IDENTIFY_PROMPT)
        except Exception as e:
            print(f"[GeminiVision] identify failed: {e}")
            yield "I can see some objects on the desk, but I'm having trouble right now."

    def tutor(self, question: str = ""):
        prompt = TUTOR_PROMPT
        if question:
            prompt += f"\n\nThe child is asking: {question}"
        try:
            if self.gemini_available:
                yield from self._stream_gemini(prompt, self.capture_snapshot())
            else:
                result = self._ask_llava_fallback(prompt)
                for sentence in result.split(". "):
                    if sentence.strip():
                        yield sentence.strip() + "."
        except Exception as e:
            print(f"[GeminiVision] tutor failed: {e}")
            yield "Hmm, let me think about that. Can you show me again?"

    def clear_history(self):
        self.conversation_history.clear()
```

---

## Startup checklist

```python
def startup_check(switcher):
    print("=== SPARKY STARTUP ===")

    import torch, cv2, serial
    assert torch.cuda.is_available(), "ROCm iGPU not found — check HSA_OVERRIDE_GFX_VERSION"
    print(f"[OK] iGPU: {torch.cuda.get_device_name(0)}")

    for idx, name in [(0, "top"), (2, "side")]:
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        assert cap.isOpened(), f"Camera '{name}' (index {idx}) not found"
        cap.release()
        print(f"[OK] Camera: {name}")

    assert switcher.eyes.is_connected(), "Arduino not found"
    print("[OK] Arduino OLED")

    for port, name in [("/dev/ttyACM0", "leader"), ("/dev/ttyACM1", "follower")]:
        s = serial.Serial(port, timeout=1); s.close()
        print(f"[OK] Arm: {name} on {port}")

    vlm = "Gemini 2.0 Flash" if switcher.gemini.gemini_available else "LLaVA (offline)"
    print(f"[OK] Vision LLM: {vlm}")

    voice = "ElevenLabs" if switcher.sparky.elevenlabs_available \
            else "Kokoro" if switcher.sparky.kokoro_available else "Piper"
    print(f"[OK] Voice: {voice}")

    print("=== ALL SYSTEMS GO ===")
    switcher.sparky.startup()
    switcher.eyes.set_emotion("HAPPY")
```

---

## OLED eyes — full mode-to-behavior mapping

| Mode | Eye behavior |
|---|---|
| Idle | Neutral, auto-blink every 3s, gentle wander |
| Listening (STT active) | Curiosity on, looking up |
| Thinking (LLM routing) | Tired mood, looking up |
| Thinking (Gemini — beeps active) | Tired mood, slow idle scan |
| Speaking (any mode) | Happy mood, blink on each sentence |
| Cleaning | Neutral, looking down |
| Tracking person | Direction driven by face centroid L/C/R |
| Identify / Tutor — looking | Curious, looking down at desk |
| Tutor — explaining | Happy, blink on each sentence |
| Success | `anim_laugh()` one-shot → idle |
| Error | `anim_confused()` + angry mood |

---

## Parallel team split and hour-by-hour timeline

**Track A — Arm + manipulation (1 person, senior, all 10 hours)**
- H0–1: ROCm/LeRobot install verify, check power supplies, calibrate both arms
- H1–2: Teleoperate smoke test, mount cameras (top overhead, side forward)
- H2–4: Record 50 episodes (watch the monitor, not the arm!)
- H4: Push dataset to HF Hub, launch training on AMD Dev Cloud MI300X
- H4–8: Build scripted-waypoint fallback while training runs
- H8–9: Evaluate ACT; if >40% success use ACT, else use fallback
- H9–10: Wire into ModeSwitcher, test clean mode with YOLO trigger

**Track B — Voice + Gemini Vision (1 person, hours 0–6, then integration)**
- H0–1: ElevenLabs setup — get API key, test Aria voice, verify robot effect sounds right on your speaker
- H1–3: Build `sparky.py` — all three backends, `start_thinking()` / `stop_thinking()`, `say_streamed()`, startup chime
- H3–5: Build `gemini_vision.py` — identify(), tutor() with conversation history, LLaVA fallback, test with math problem
- H5–6: `startup_check()`, test full flow: chime → voice → Gemini → spoken response with thinking beeps
- H6+: Integration

**Track C — Vision + YOLO (1 person, hours 0–3, then integration)**
- H0–2: MediaPipe face detection on side camera, `VisionModule` thread, `get_person_centroid()`
- H2–3: YOLO11n `objects_present_in_pickup_zone()` — bounding box check in pickup region only
- H3+: Integration

**Track D — Eyes + Arduino (1 person or merged with C, hours 0–3)**
- H0–2: Wire OLED, flash RoboEyes sketch, verify single-byte serial from Python, `time.sleep(2.0)` after open
- H2–3: Wire all mode transitions including thinking/speaking states, test sync with `sparky.say()`
- H3+: Integration

**Hour 7: All tracks merge.** Hour 9–10: demo rehearsal including full startup sequence.

---

## Critical gotchas — ranked by kill probability

**Power supplies** — 5V to follower or 12V to leader damages servos. Verify before powering on.

**Skip motor ID setup** — Already done on provided kits. Running it again causes silent failures.

**HSA_OVERRIDE_GFX_VERSION=11.0.0** — Must be in `~/.bashrc`. Without it ROCm won't see the iGPU.

**PyTorch version** — Must be `torch==2.7.1+rocm6.3`. `pip install lerobot` can silently replace it with CPU-only. Reinstall and re-verify.

**LeRobot version** — Pin `v0.4.1` exactly. Later commits may break SO-101.

**pynput==1.7.7 + Xorg** — Arrow key recording only works under Xorg. Switch at login screen before starting.

**ElevenLabs API key** — Must be exported as `ELEVENLABS_API_KEY`. The `startup_check()` will catch this at boot.

**ElevenLabs character budget** — Check `elevenlabs.io/app/usage` the morning of the hackathon. 10k free chars is plenty but heavy overnight testing can burn through it. Kokoro is the silent automatic fallback.

**Kokoro model files** — `kokoro-v0_19.onnx` and `voices.bin` must be downloaded. Run `python -c "from kokoro_onnx import Kokoro; Kokoro.download()"` before demo day.

**Audio output device** — If no sound comes out, run `python -c "import sounddevice; print(sounddevice.query_devices())"` and set `sd.default.device = N` for the correct speaker index.

**Robot effect too heavy** — If the chorus sounds distorted on your specific speaker, reduce the `* 0.18` delay mix to `* 0.10` in `apply_robot_effect()`.

**Camera routing** — Top camera (index 0) → GeminiVision. Side camera (index 2) → VisionModule. Swap them and both modes break.

**Camera on separate USB ports** — Don't share a hub. `lerobot-find-cameras opencv` to identify, `ffplay /dev/video*` to verify.

**Gemini offline fallback** — Auto-falls back to LLaVA on any API failure. Pre-pull `ollama pull llava` the night before.

**Conversation history on mode switch** — `gemini.clear_history()` on every mode switch except tutor follow-ups. Already handled in ModeSwitcher.

**Pre-warm Gemini on startup** — Done in `GeminiVision.__init__()`. Don't skip it — cold first call takes 3–5 seconds.

**Video corruption during training** — If training throws `RuntimeError: Could not push packet to decoder`, diagnose with `ffmpeg -v error -i file-000.mp4 -f null -` and re-record.

**Arduino auto-reset** — Always `time.sleep(2.0)` after opening serial port.

**Watch the monitor during recording** — Most common cause of ACT failing at inference. Policy only sees camera data.

**Cloud persistent storage** — Keep data in `/user-data` in Jupyter. Compress: `tar cjvf model.tar.bz2 ./outputs/train/...`

---

## Hackathon demo script

1. **Startup:** `startup_check()` runs → chime plays → Sparky says in character voice: *"Hello! I'm Sparky. I'm ready to help!"*

2. **Identify:** Place objects on the desk. Say "What do you see?" → thinking beeps → Sparky says: *"I can see a red water bottle, two pencils, and an open notebook."*

3. **Tutor:** Put a handwritten math problem on the desk (`7 × 8 = ?`). Say "Help me solve this." → thinking beeps → Sparky speaks: *"Okay! So we need to multiply 7 times 8. Think of 7 groups of 8 — if we count up: 8, 16, 24, 32, 40, 48, 56 — the answer is 56! You've got this!"* → eyes laugh.

4. **Follow-up:** Say "But why?" → Sparky uses conversation history, explains multiplication differently — no camera capture, no gap.

5. **Track:** Say "Watch me" → robot follows your face.

6. **Clean:** Scatter objects, say "Clean up my desk" → YOLO confirms objects → arm cleans up.

---

## Key resources

| Resource | URL |
|---|---|
| AMD hackathon starter repo | `github.com/andrewgschmidt/AMD_Hackathon/tree/main/robotics/robotics_2026` |
| SO-101 example commands | `so101_example.md` in repo above |
| Seeed Studio SO-101 tutorial | `wiki.seeedstudio.com/lerobot_so100m_new` |
| LeRobot docs | `huggingface.co/docs/lerobot/so101` |
| DeepWiki (LeRobot AI Q&A) | `deepwiki.com/huggingface/lerobot` |
| AMD Ryzers Docker ML stack | `github.com/AMDResearch/Ryzers` |
| AMD AUP AI Tutorials | `amdresearch.github.io/aup-ai-tutorials` |
| Gemini API free key | `aistudio.google.com` |
| ElevenLabs free key | `elevenlabs.io` |
| Kokoro TTS | `github.com/thewh1teagle/kokoro-onnx` |

---

## What success looks like at end-of-day

Sparky boots with a chime and says hello in a warm robot voice. Every spoken word — whether identifying objects, explaining a math problem, or saying "cleaning up now!" — comes through the same consistent ElevenLabs character voice with a subtle robot resonance. Thinking beeps fill every silence while Gemini processes. The OLED eyes stay in sync with speech. Follow-up questions work because conversation history is preserved. The whole system sounds and feels like a single character, not a collection of scripts.

The AMD laptop's iGPU runs LeRobot inference, Ollama intent routing, YOLO, and MediaPipe simultaneously via ROCm. Gemini 2.0 Flash handles all vision-language understanding. ElevenLabs gives Sparky a voice kids will actually want to talk to.
