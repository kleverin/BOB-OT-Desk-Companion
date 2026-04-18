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
| Cameras | 2× USB cameras (overhead bracket + side/wrist mount) |
| OLED | SSD1306 128×64 I²C connected to Arduino Uno/Nano |
| Power | **5V 6A** → Leader arm · **12V 8A** → Follower arm ← DO NOT SWAP |

---

## What the robot does — six modes

| Mode | Trigger phrase | What happens |
|---|---|---|
| **IDLE** | "stop" / "rest" | Neutral blinking eyes, waiting |
| **IDENTIFY** | "what is this?" / "name this" | YOLO scans desk, TTS speaks detected objects |
| **TRACK** | "follow me" / "watch me" | MediaPipe tracks your face, arm aims |
| **CLEAN** | "clean up" / "tidy this" | ACT policy or scripted-waypoint cleanup |
| **TUTOR** | "help me" / "explain this" / "how do I solve this" | Gemini 2.0 Flash sees the desk, explains to the child step by step |
| **LISTEN** | spacebar held | STT active, waiting for a command |

---

## Central architecture — one mode-switching process

Everything runs from one Python process dispatching between six modes. Voice commands or spacebar transitions modes. Each mode owns which subsystems are active and what the OLED eyes show.

```
                        ┌──────────────────┐
                        │   ModeSwitcher   │  (main thread, state machine)
                        └────────┬─────────┘
                                 │
   ┌──────────┬──────────────────┼──────────┬──────────┬──────────┐
   ▼          ▼                  ▼          ▼          ▼          ▼
voice.py  vision.py           eyes.py    arm.py     tts.py   tutor.py
(STT+LLM) (YOLO+MediaPipe)   (serial)  (lerobot)  (Piper)  (Gemini 2.0 Flash)

All run as background threads.
ModeSwitcher polls vision.get_*, calls eyes.set_*, tts.say(), arm.run_task(), tutor.ask_streamed()
```

Use **threads + queues** — not asyncio. Easier to debug under time pressure.

---

## Environment setup — exact AMD-pinned versions

Follow these precisely. Do not freestyle the installs.

```bash
# 1. ROCm 6.3 (if not pre-installed on AMD laptop)
wget https://repo.radeon.com/amdgpu-install/6.3.4/ubuntu/noble/amdgpu-install_6.3.60304-1_all.deb
sudo apt install ./amdgpu-install_6.3.60304-1_all.deb
amdgpu-install -y --usecase=rocm --no-dkms   # --no-dkms is critical
sudo reboot

# 2. Set iGPU compatibility mode for Ryzen AI 300 series (REQUIRED)
echo "export HSA_OVERRIDE_GFX_VERSION=11.0.0" >> ~/.bashrc
source ~/.bashrc

# 3. Conda environment — Python 3.10 is required (MediaPipe has no 3.13 wheels)
conda create -n lerobot python=3.10
conda activate lerobot

# 4. PyTorch with ROCm — MUST be <2.8.0 (LeRobot hard constraint)
pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 \
    --index-url https://download.pytorch.org/whl/rocm6.3

# Verify iGPU is recognized
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# Expected: True  AMD Radeon Graphics

# 5. LeRobot — pin v0.4.1 exactly
conda install ffmpeg=7.1.1 -c conda-forge
git clone https://github.com/huggingface/lerobot.git
cd lerobot
git checkout -b v0.4.1 v0.4.1     # pin this — do not use main
pip install -e .
pip install 'lerobot[feetech]'    # Feetech servo support for SO-101

# 6. All project packages
pip install faster-whisper piper-tts sounddevice keyboard
pip install ollama pydantic
pip install ultralytics pyserial
pip install pynput==1.7.7         # MUST be this version for Ubuntu keyboard arrow keys
pip install opencv-python "numpy<2.0" mediapipe

# 7. Tutor mode (Gemini 2.0 Flash)
pip install google-generativeai pillow
# Get free API key at: aistudio.google.com (free with Google account)

# 8. Local VLM fallback (offline demo insurance)
ollama pull llava    # 4GB multimodal model, works without internet
ollama pull llama3.2:3b
python -m piper.download_voices en_US-amy-medium
```

> **Key AMD insight:** The Ryzen AI laptop's RDNA 3.5 iGPU IS ROCm-compatible. Use `--policy.device=cuda` for LeRobot inference and Ollama auto-detects the iGPU via llama.cpp's HIP backend. No cloud needed for inference — only for training.

---

## Manipulation policy — use ACT

| Policy | Params | Day-1 feasible | Why |
|---|---|---|---|
| **ACT** | ~52M | ✅ Yes | No extra deps, trains 2–4h on MI300X, proven on SO-101 |
| SmolVLA | 450M | ⚠️ Tight | Needs `pip install -e ".[smolvla]"`, radians/degrees bug risk |
| Pi-0 / Pi-0-FAST | ~3B | ❌ No | Needs `pip install -e ".[pi]"`, too slow to fine-tune in one day |
| OpenVLA | 7B | ❌ No | Requires massive GPU + RLDS conversion overhead |

ACT ingests joint state through a transformer encoder, decodes over ResNet-18 camera features, and emits a chunk of k absolute joint targets at once. Temporal ensembling smooths motion. Expect 50–70% pick-and-place success with 50 clean episodes.

---

## Training on AMD Developer Cloud (MI300X)

AMD provides 2× MI300X Jupyter notebook instances per team. This is your training compute — better than Colab.

**Flow:**
1. Record 50+ episodes on the Ryzen AI laptop → upload to HuggingFace Hub (`hf auth login`)
2. Log into AMD Dev Cloud portal with team credentials → Launch Notebook 1
3. Run training:

```bash
lerobot-train \
  --dataset.repo_id=YOUR_HF_USER/desk_cleanup_dataset \
  --batch_size=64 \
  --steps=20000 \
  --save_freq=5000 \
  --output_dir=outputs/train/act_so101_desk \
  --job_name=act_so101_desk \
  --policy.device=cuda \
  --policy.type=act \
  --policy.push_to_hub=true \
  --policy.repo_id=YOUR_HF_USER/act_so101_desk \
  --wandb.enable=true
```

4. While training runs (2–4 hours), build voice + vision + eyes + tutor in parallel
5. Download trained model → `lerobot-record --policy.path=...` for eval on laptop

> Keep data in the `/user-data` persistent folder. Compress before downloading: `tar cjvf model.tar.bz2 outputs/train/...`

---

## Arm setup

**Skip motor ID and baudrate setup** — pre-done on provided kits. Go straight to calibration.

```bash
# USB permissions
sudo chmod 666 /dev/ttyACM0   # Leader (connect leader FIRST)
sudo chmod 666 /dev/ttyACM1   # Follower

# Find cameras
lerobot-find-cameras opencv
ffplay /dev/video0             # verify angle, repeat for video2, video4 etc.

# Calibrate follower
lerobot-calibrate \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM1 \
    --robot.id=my_follower_arm

# Calibrate leader
lerobot-calibrate \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM0 \
    --teleop.id=my_leader_arm

# Smoke test
lerobot-teleoperate \
    --robot.type=so101_follower --robot.port=/dev/ttyACM1 --robot.id=my_follower_arm \
    --teleop.type=so101_leader  --teleop.port=/dev/ttyACM0 --teleop.id=my_leader_arm
```

Start calibration from a **neutral/middle position** to avoid extreme joint values. If you see a `Lock` error, unplug and replug the arm's power.

---

## Data collection for desk cleanup

```bash
lerobot-record \
    --robot.type=so101_follower --robot.port=/dev/ttyACM1 --robot.id=my_follower_arm \
    --robot.cameras="{top: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, \
                      side: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30}}" \
    --teleop.type=so101_leader --teleop.port=/dev/ttyACM0 --teleop.id=my_leader_arm \
    --display_data=true \
    --dataset.repo_id=${HF_USER}/desk_cleanup_dataset \
    --dataset.num_episodes=50 \
    --dataset.episode_time_s=20 \
    --dataset.reset_time_s=10 \
    --dataset.single_task="pick up objects from desk and return them to preset positions" \
    --dataset.root=${HOME}/desk_dataset/
```

**Ubuntu arrow keys for recording:** Requires Xorg. At login screen → gear icon → "Ubuntu on Xorg". Also requires `pynput==1.7.7` (already installed above).

**The #1 data collection failure:** Watching the physical arm instead of the camera feed on your monitor. The policy only sees what the camera captures — watch only the screen.

---

## Scripted-waypoint fallback (build in parallel with training)

Build this simultaneously so the demo always works:

1. Save named poses with a keyboard hotkey during teleoperation (pickup zone, drop bin, home)
2. Implement `arm.run_cleanup()` as a hard-coded joint-space trajectory between those poses
3. Trigger only when YOLO detects objects in the pickup zone
4. This reliably demos "cleanup mode" even if the neural policy underperforms

---

## Voice pipeline

Stack: `faster-whisper base.en` → push-to-talk spacebar → `Ollama llama3.2:3b` (iGPU via HIP) → `Piper en_US-amy-medium`

End-to-end latency: ~1.5–2 seconds. Use `vad_filter=True` and `beam_size=1` on Whisper. Use `sounddevice` not `pyaudio`.

**Intent router system prompt** — update this to include the tutor mode:

```python
INTENT_SCHEMA = """
Return JSON only: {"mode": string, "target": string, "reply": string}

Modes:
- "clean"    → tidy, clean up, put away, organize
- "identify" → what is this, name this, identify, look at this
- "track"    → follow me, watch me, track me
- "tutor"    → help me, explain this, how do I solve, what is this problem,
               I don't understand, show me how, teach me, what does this say,
               how does this work
- "idle"     → stop, rest, nevermind, go to sleep

For tutor mode, capture any specific question in "target".
Example: "how do I solve this?" → {"mode":"tutor","target":"how do I solve this","reply":"Let me take a look!"}
"""
```

Use a regex fast-path for ~80% of commands (<1ms), Ollama for ambiguous paraphrases. Always wrap Ollama calls in try/except.

---

## Vision: YOLO + MediaPipe

YOLO11n (`yolo11n.pt`, ~5 MB) covers virtually all desk objects at 30–80 FPS on the iGPU. MediaPipe FaceDetection for person tracking at 30+ FPS. Both run in a single `VisionModule` background thread that owns the `VideoCapture` — never let two subsystems open the camera simultaneously.

Connect each camera to a **different USB port**, not through the same hub. Use `cv2.CAP_V4L2` on Linux for reliable capture.

---

## Tutor mode — Gemini 2.0 Flash vision for kids

This is the standout feature. The robot looks at whatever is on the desk — a math problem, a word, a drawing — and explains it to a child step by step in a friendly voice.

### How it works

```
Child says "help me with this"
         │
         ▼
   ModeSwitcher sets mode = TUTOR
         │
         ├──→ eyes.py:   CURIOUS mood, look DOWN at desk
         ├──→ tts.py:    say "Let me take a look!"
         ├──→ tutor.py:  capture snapshot from overhead camera
         │               send image + kid-friendly system prompt to Gemini 2.0 Flash
         │               stream response sentence by sentence
         ├──→ tts.py:    speak each sentence as it arrives (low latency)
         ├──→ eyes.py:   HAPPY mood, blink on each sentence
         └──→ eyes.py:   anim_laugh() when done → return to IDLE
```

### Which VLM to use

| Option | Model | Setup | Offline | Cost |
|---|---|---|---|---|
| **A — Gemini 2.0 Flash (recommended)** | `gemini-2.0-flash` | 15 min | No | Free tier |
| B — GPT-4o mini | `gpt-4o-mini` | 15 min | No | ~$0.01/image |
| C — LLaVA via Ollama (offline fallback) | `llava` | 30 min | ✅ Yes | Free |

**Use Gemini 2.0 Flash for the demo.** It's the closest thing to Gemini Live, free at `aistudio.google.com`, returns answers in ~1–2 seconds, and handles handwritten math and text very well. Pre-pull `llava` as your offline fallback in case venue WiFi fails.

### tutor.py

```python
import google.generativeai as genai
from PIL import Image
import cv2

SYSTEM_PROMPT = """You are a friendly robot tutor named Sparky helping kids aged 6-14.
When shown a math problem, homework question, drawing, or any object:
- Explain it step by step in simple, encouraging language
- Use short sentences. Never use jargon without explaining it first.
- Never just give the answer — guide the child to figure it out themselves.
- Keep your total response under 5 sentences so the child stays engaged.
- Always end with an encouraging phrase like "You've got this!" or "Great question!"
- If it's a math problem, walk through each step out loud like a teacher would."""

class TutorModule:
    def __init__(self, api_key: str, camera_index: int = 0):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        self.camera_index = camera_index

    def capture_snapshot(self) -> Image.Image:
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise RuntimeError("Could not capture frame")
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    def ask_streamed(self, extra_question: str = ""):
        """Yields sentences as they arrive — start speaking before full response is done."""
        image = self.capture_snapshot()
        prompt = SYSTEM_PROMPT
        if extra_question:
            prompt += f"\n\nThe child is specifically asking: {extra_question}"

        response = self.model.generate_content([prompt, image], stream=True)
        buffer = ""
        for chunk in response:
            buffer += chunk.text
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


# Local offline fallback using Ollama + LLaVA
class TutorModuleLocal:
    def __init__(self, model: str = "llava", camera_index: int = 0):
        self.model = model
        self.camera_index = camera_index

    def capture_snapshot(self) -> str:
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
        ret, frame = cap.read()
        cap.release()
        path = "/tmp/desk_snapshot.jpg"
        cv2.imwrite(path, frame)
        return path

    def ask(self, extra_question: str = "") -> str:
        import ollama
        image_path = self.capture_snapshot()
        prompt = SYSTEM_PROMPT
        if extra_question:
            prompt += f"\n\nThe child is asking: {extra_question}"
        response = ollama.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt, "images": [image_path]}]
        )
        return response["message"]["content"]
```

### Wiring tutor into ModeSwitcher

```python
from tutor import TutorModule

class ModeSwitcher:
    def __init__(self):
        # ... existing modules (voice, vision, arm, tts, eyes) ...
        self.tutor = TutorModule(api_key="YOUR_GEMINI_API_KEY", camera_index=0)

    def handle_intent(self, intent: dict):
        mode = intent.get("mode")

        if mode == "tutor":
            self.current_mode = "TUTOR"
            self.eyes.set_emotion("CURIOUS")
            self.eyes.look("DOWN")

            self.tts.say("Let me take a look at that for you!")
            self.eyes.set_emotion("TIRED")   # thinking face

            question = intent.get("target", "")
            self.eyes.set_emotion("HAPPY")

            for sentence in self.tutor.ask_streamed(question):
                self.tts.say(sentence)       # speaks each sentence as it arrives

            self.eyes.laugh()
            self.current_mode = "IDLE"
```

### System prompt tuning by age group

```python
# Ages 6–9 (early elementary)
PROMPT_YOUNG = """Use very simple words. Maximum 3 steps.
Use lots of encouragement. Say things like "Let's count together!"."""

# Ages 10–14 (middle school)
PROMPT_OLDER = """Explain the concept, not just the answer.
Use analogies they'd understand (pizza slices for fractions, etc.).
Challenge them: "What do you think comes next?"."""
```

---

## OLED eyes — full mode-to-behavior mapping

| Mode | Eye behavior |
|---|---|
| Idle | Neutral, auto-blink every 3s, gentle wander |
| Listening (STT active) | Curiosity on, looking up at user |
| Thinking (LLM routing) | Tired mood, looking up — "pondering" |
| Speaking (TTS active) | Happy mood, blink on each sentence |
| Cleaning (arm moving) | Neutral, looking down, curiosity off |
| Tracking person | Direction driven by face centroid |
| Tutor — looking at problem | Curious, looking down at desk |
| Tutor — thinking (VLM) | Tired mood, slow idle scan |
| Tutor — explaining | Happy, blink on each sentence |
| Success (any mode) | `anim_laugh()` one-shot → idle |
| Error | `anim_confused()` + angry mood |

**Arduino auto-reset reminder:** Always `time.sleep(2.0)` after opening the serial port. The Uno resets on DTR toggle and eats ~1.5 seconds of bytes silently.

---

## Parallel team split and hour-by-hour timeline

**Track A — Arm + manipulation (1 person, senior, all 10 hours)**
- H0–1: ROCm/LeRobot install verify, check power supplies, calibrate both arms
- H1–2: Teleoperate smoke test, mount cameras rigidly, mark object positions on desk
- H2–4: Record 50 episodes (watch the monitor, not the arm!)
- H4: Push dataset to HF Hub, launch `lerobot-train` on AMD Dev Cloud MI300X
- H4–8: Build scripted-waypoint fallback while training runs
- H8–9: Evaluate ACT policy on laptop iGPU; if >40% success use ACT, else use fallback
- H9–10: Wire into ModeSwitcher

**Track B — Voice + Tutor (1 person, hours 0–5, then integration)**
- H0–3: faster-whisper + sounddevice, push-to-talk loop, Ollama + llama3.2:3b, Piper TTS
- H3–5: Build `tutor.py` — Gemini API, `capture_snapshot()`, `ask_streamed()`, test with a math problem, pre-pull `llava` offline fallback
- H5+: Integration

**Track C — Vision (1 person, hours 0–4, then integration)**
- H0–3: YOLO11n + MediaPipe, VisionModule thread, `describe_scene()` TTS formatter
- H3–4: Proportional aiming helper for person-track mode
- H4+: Integration

**Track D — Eyes + Arduino (1 person or merged with C, hours 0–3)**
- H0–2: Wire OLED, flash RoboEyes sketch, verify single-byte serial from Python
- H2–3: Wire all mode transitions including new TUTOR states
- H3+: Integration

**Hour 7: All tracks merge** into ModeSwitcher integration. Hour 9–10 is demo rehearsal.

---

## Critical gotchas — ranked by kill probability

**Power supplies** — 5V to follower or 12V to leader damages servos. Verify before powering on. Most expensive mistake possible.

**Skip motor ID setup** — Already done on provided kits. Running it again causes silent failures.

**HSA_OVERRIDE_GFX_VERSION=11.0.0** — Must be set or ROCm won't see the iGPU. Add to `~/.bashrc`, source it, verify `torch.cuda.is_available()` returns `True` before doing anything else.

**PyTorch version** — Must be `torch==2.7.1+rocm6.3`. `pip install lerobot` can silently replace it with a CPU-only wheel. Reinstall the ROCm wheel and re-verify.

**LeRobot version** — Pin `v0.4.1` exactly with `git checkout -b v0.4.1 v0.4.1`. Later commits may break SO-101.

**pynput==1.7.7 + Xorg** — Arrow key recording only works under Xorg, not Wayland. Switch at login screen before starting. Wrong version = no keyboard control during recording.

**Camera on separate USB ports** — Don't share a hub. Use `lerobot-find-cameras opencv` to identify ports, `ffplay /dev/video*` to verify angles.

**Video corruption** — If training throws `RuntimeError: Could not push packet to decoder`, a video is corrupted (usually from Ctrl+C during recording). Diagnose with `ffmpeg -v error -i file-000.mp4 -f null -` and re-record that episode.

**Arduino auto-reset** — Always `time.sleep(2.0)` after opening serial port or the first commands are silently lost.

**Gemini offline** — If venue WiFi fails, switch to `TutorModuleLocal` with `llava`. Pre-pull before the event: `ollama pull llava`.

**Tutor camera index** — Point the **overhead/top camera** at the desk for tutor mode, not the wrist camera. Pass the correct `camera_index` to `TutorModule`.

**Gemini response length** — If answers are too long for kids, add `"Keep your response under 60 words."` to the system prompt.

**Watch the monitor during recording** — The most common ACT failure. Policy can only use camera data. Watching the arm while recording injects information the policy will never have, causing wild failures at inference.

**Cloud persistent storage** — Keep models/datasets in `/user-data` in Jupyter. Everything else is ephemeral. Compress before downloading: `tar cjvf model.tar.bz2 ./outputs/train/...`

---

## Hackathon demo script

A compelling sequence that shows off every feature in ~3 minutes:

1. **Identify mode:** Place a pen, cup, and phone on the desk. Say "What do you see?" → robot names all three objects.

2. **Tutor mode:** Put a handwritten math problem on the desk (e.g., `7 × 8 = ?`). Say "Help me solve this." → Eyes go curious and look down → "Let me take a look!" → thinking animation → "Okay! So we need to multiply 7 times 8. Let's think of 7 groups of 8... the answer is 56! You've got this!" → eyes laugh.

3. **Track mode:** Say "Watch me" and walk around → robot tracks your face.

4. **Clean mode:** Scatter the objects, say "Clean up my desk" → arm picks up and returns objects to preset positions (ACT policy or scripted fallback).

5. **OLED eyes throughout** — make sure judges can see the display reacting to each mode change.

---

## Key AMD resources

| Resource | URL |
|---|---|
| AMD hackathon starter repo | `github.com/andrewgschmidt/AMD_Hackathon/tree/main/robotics/robotics_2026` |
| SO-101 example commands | `so101_example.md` in repo above |
| Seeed Studio SO-101 tutorial | `wiki.seeedstudio.com/lerobot_so100m_new` |
| LeRobot official docs | `huggingface.co/docs/lerobot/so101` |
| DeepWiki (AI-powered LeRobot Q&A) | `deepwiki.com/huggingface/lerobot` |
| AMD Ryzers Docker ML stack | `github.com/AMDResearch/Ryzers` |
| AMD AUP AI Tutorials | `amdresearch.github.io/aup-ai-tutorials` |
| Gemini API (free key) | `aistudio.google.com` |

---

## What success looks like at end-of-day

Voice command → Piper TTS reply within ~2 seconds → mode transition with matching OLED eyes → "identify" speaks detected objects → "track" follows your face → "clean" runs ACT policy (50–70% success) or scripted fallback (guaranteed) → "tutor" looks at a math problem and explains it to a child step by step using Gemini 2.0 Flash → eyes laugh when done.

The AMD laptop's iGPU runs LeRobot inference, Ollama intent routing, and YOLO all via ROCm simultaneously. Gemini 2.0 Flash handles the vision-language tutoring. Together they make a robot that can see, speak, move, and teach — in one day.
