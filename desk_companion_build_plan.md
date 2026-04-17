# Desk Companion Robot in One Day
### AMD StarkHacks — SO-101 + Ryzen AI Laptop Build Plan (AMD-Verified)

---

## Hardware you actually have (confirmed from AMD docs)

| Item | Details |
|---|---|
| Robot | WowRobo SO-101 Leader/Follower kit (pre-assembled) |
| Compute | AMD Ryzen AI laptop (Ryzen AI 9 HX370) — RDNA 3.5 iGPU + XDNA 2 NPU |
| OS | Ubuntu 24.04 LTS |
| Cloud GPU | AMD Developer Cloud — 2× MI300X Jupyter notebooks provided per team |
| Cameras | 2× USB cameras (overhead bracket + side/wrist mount) |
| OLED | SSD1306 128×64 I²C connected to Arduino |
| Power | **5V 6A** → Leader arm; **12V 8A** → Follower arm ← DO NOT SWAP |

---

## Central architecture: one mode-switching process

Everything hangs off one Python process dispatching between five modes: **idle**, **listen**, **identify**, **track**, and **clean**. Voice commands or spacebar transitions modes; each mode owns which subsystems are active and what the OLED eyes do.

```
                     ┌──────────────┐
                     │ ModeSwitcher │  (main thread, state machine)
                     └──────┬───────┘
                            │
     ┌──────────┬───────────┼──────────┬──────────┐
     ▼          ▼           ▼          ▼          ▼
 voice.py   vision.py   eyes.py    arm.py     tts.py
 (STT+LLM)  (YOLO+MP)   (serial)  (lerobot)  (Piper)
     └── all background threads; ModeSwitcher polls via thread-safe APIs
```

Use threads + queues — not asyncio. Easier to debug under time pressure.

---

## Environment setup — exact AMD-pinned versions

Follow these precisely. Do not freestyle the installs.

```bash
# 1. ROCm 6.3 (if not pre-installed on AMD laptop)
wget https://repo.radeon.com/amdgpu-install/6.3.4/ubuntu/noble/amdgpu-install_6.3.60304-1_all.deb
sudo apt install ./amdgpu-install_6.3.60304-1_all.deb
amdgpu-install -y --usecase=rocm --no-dkms   # --no-dkms is critical — use built-in kernel driver
sudo reboot

# 2. Set iGPU compatibility mode for Ryzen AI 300 series (REQUIRED)
echo "export HSA_OVERRIDE_GFX_VERSION=11.0.0" >> ~/.bashrc
source ~/.bashrc

# 3. Conda environment
conda create -n lerobot python=3.10
conda activate lerobot

# 4. PyTorch with ROCm — MUST be <2.8.0 (LeRobot's hard constraint)
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

# 6. Project-specific packages
pip install faster-whisper piper-tts sounddevice keyboard ollama pydantic
pip install ultralytics pyserial
pip install pynput==1.7.7         # MUST be this version for Ubuntu keyboard arrow key recording
```

> **Key insight from AMD docs:** The Ryzen AI laptop's RDNA 3.5 iGPU IS ROCm-compatible. Use `--policy.device=cuda` for LeRobot inference, and Ollama auto-detects the iGPU via llama.cpp's HIP backend. No cloud needed for inference — only for training.

---

## Pick ACT for manipulation — policy comparison

| Policy | Params | Day-1 feasible | Why |
|---|---|---|---|
| **ACT** | ~52M | ✅ Yes | No extra deps, trains in 2–4h on MI300X, proven on SO-101 |
| SmolVLA | 450M | ⚠️ Tight | Needs `pip install -e ".[smolvla]"`, radians/degrees bug risk |
| Pi-0 / Pi-0-FAST | ~3B | ❌ No | Needs `pip install -e ".[pi]"`, too slow to fine-tune in a day |
| OpenVLA | 7B | ❌ No | Requires massive GPU + RLDS conversion overhead |

ACT ingests joint state through a transformer encoder, decodes over ResNet-18 camera features, and emits a chunk of k absolute joint targets at once. Temporal ensembling smooths motion; L1 loss keeps grasps precise. Expect 50–70% pick-and-place success with 50 clean episodes.

---

## Training on AMD Developer Cloud (MI300X) — not Colab

AMD provides 2× MI300X Jupyter notebook instances per team at the hackathon. This replaces any need for Colab or personal cloud credits.

**Flow:**
1. Record 50+ episodes on the Ryzen AI laptop → upload dataset to HuggingFace Hub (`hf auth login` first)
2. Log into AMD Dev Cloud portal with team credentials → Launch Notebook 1
3. In the Jupyter terminal or notebook cells, run the training setup from the AMD repo README, then:

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

4. While training runs (2–4 hours), build voice + vision + eyes in parallel
5. Download trained model to laptop → run `lerobot-record --policy.path=...` for eval

> **Important:** Keep important data in the `/user-data` persistent folder in Jupyter. Everything else is ephemeral. Compress before downloading: `tar cjvf model.tar.bz2 outputs/train/...`

---

## Arm setup — exact commands from AMD example docs

**Skip motor ID and baudrate setup** — pre-done on provided kits. Go straight to calibration.

```bash
# USB permissions
sudo chmod 666 /dev/ttyACM0   # Leader (connect leader FIRST to get ACM0)
sudo chmod 666 /dev/ttyACM1   # Follower

# Find camera ports
lerobot-find-cameras opencv
ffplay /dev/video0   # verify angle, then try video2 etc.

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

# Smoke test teleoperation
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

**Arrow key recording on Ubuntu:** Requires Xorg (not Wayland). At the login screen → gear icon → "Ubuntu on Xorg". Also requires `pynput==1.7.7`.

**The #1 data collection failure:** Watching the physical arm instead of the camera feed on your monitor. The policy only sees what the camera captures. Watch only the screen during recording.

---

## Scripted-waypoint fallback (build this in parallel with training)

Build this simultaneously so the demo always works regardless of ACT convergence:

1. During teleoperation, save named poses with a keyboard hotkey (pickup zone, drop bin, home)
2. Implement `arm.run_cleanup()` as a hard-coded joint-space trajectory between those poses
3. Trigger only when YOLO detects objects in the pickup zone
4. Demo "cleanup mode" with this even if the neural policy underperforms

---

## Voice pipeline

Stack: `faster-whisper base.en` → push-to-talk spacebar → `Ollama llama3.2:3b` (iGPU via HIP) → `Piper en_US-amy-medium`

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
python -m piper.download_voices en_US-amy-medium
```

End-to-end latency: ~1.5–2 seconds from spacebar release to spoken reply. Use `vad_filter=True` and `beam_size=1` on Whisper. Use `sounddevice` not `pyaudio`. Dual-layer intent routing: regex fast-path for ~80% of commands (<1ms), Ollama for ambiguous paraphrases.

---

## Vision: YOLO + MediaPipe

YOLO11n covers virtually all desk objects at 30–80 FPS. MediaPipe FaceDetection for person tracking at 30+ FPS. Both run in a single `VisionModule` background thread that owns the `VideoCapture` — never let two subsystems open the camera simultaneously.

**Connect each camera to a different USB port**, not through the same hub. This is explicitly flagged in the AMD FAQ as a source of unstable video.

---

## OLED eyes on Arduino

**FluxGarage RoboEyes** library (Arduino Library Manager). 128×64 SSD1306 on I²C (`0x3C`), 4 wires to Uno.

Python side: `pyserial` + `time.sleep(2.0)` after opening serial port (Arduino auto-resets on DTR toggle and eats ~1.5 seconds of bytes).

| Mode | Eye behavior |
|---|---|
| Idle | Neutral, auto-blink, gentle wander |
| Listening | Curiosity on, looking up |
| Thinking (LLM) | Tired mood, looking up |
| Speaking | Happy + blink each sentence |
| Cleaning | Neutral, looking down |
| Tracking person | Direction driven by face centroid |
| Success | `anim_laugh()` one-shot |
| Error | `anim_confused()` + angry mood |

---

## Parallel team split and hour-by-hour timeline

**Track A — Arm + manipulation (1 person, senior, all 10 hours)**
- H0–1: ROCm/LeRobot install verify, calibrate both arms (CHECK POWER SUPPLIES FIRST)
- H1–2: Teleoperate smoke test, mount cameras rigidly, mark desk object positions
- H2–4: Record 50 episodes (watch the monitor!)
- H4: Push dataset to HF Hub, launch `lerobot-train` on AMD Dev Cloud MI300X
- H4–8: Build scripted-waypoint fallback while training runs on the cloud
- H8–9: Evaluate trained policy on laptop iGPU; if >40% success use ACT, else use fallback
- H9–10: Wire into ModeSwitcher

**Track B — Voice (1 person, hours 0–4, then integration)**
- H0–3: faster-whisper + sounddevice, push-to-talk loop, Ollama + llama3.2:3b, Piper TTS
- H3–4: Pre-download all models (~2.2 GB) before hackathon WiFi degrades
- H4+: Integration

**Track C — Vision (1 person, hours 0–4, then integration)**
- H0–3: YOLO11n + MediaPipe, VisionModule thread, `describe_scene()` formatter
- H3–4: Proportional aiming helper for person-track mode
- H4+: Integration

**Track D — Eyes + Arduino (1 person or merged with C, hours 0–3)**
- H0–2: Wire OLED, flash RoboEyes sketch, verify single-byte serial from Python
- H2–3: Wire all mode transitions, test EyesController with mock states
- H3+: Integration

**Hour 7: All tracks merge.** Hour 9–10 is demo rehearsal. If manipulation isn't working by hour 8, commit to scripted fallback and demo 4 of 5 features.

---

## Critical gotchas (ranked by kill probability)

**Power supplies** — 5V to follower or 12V to leader damages servos. Verify before powering on.

**Skip motor ID setup** — Already done on provided kits. Running it again causes silent failures.

**HSA_OVERRIDE_GFX_VERSION=11.0.0** — Must be set or ROCm won't see the iGPU. Add to `~/.bashrc`, source it, verify `torch.cuda.is_available()` before anything else.

**PyTorch version** — Must be `torch==2.7.1+rocm6.3`. `pip install lerobot` can silently replace it with a CPU wheel. Reinstall the ROCm wheel afterward and re-verify.

**LeRobot version** — Pin `v0.4.1` exactly. Later commits may have breaking SO-101 changes.

**pynput==1.7.7 + Xorg** — Arrow key recording only works under Xorg, not Wayland. Switch at login screen before starting. Wrong pynput version = no keyboard control during recording.

**Camera on different USB ports** — Don't share a hub. Use `lerobot-find-cameras opencv` to identify ports, `ffplay /dev/video*` to verify angles.

**Video corruption** — If training throws `RuntimeError: Could not push packet to decoder`, a video is corrupted (usually from Ctrl+C during recording). Diagnose with `ffmpeg -v error -i file-000.mp4 -f null -` and re-record.

**Arduino auto-reset** — Always `time.sleep(2.0)` after opening serial port. Skip this and you'll wonder why the eyes don't respond to the first commands.

**Watch the monitor during recording** — The single most common ACT failure. Policy can only use camera data. If you demonstrate by watching the arm, you're injecting information the policy will never have.

**Cloud persistent storage** — Keep models and datasets in `/user-data` in Jupyter. Compress before downloading: `tar cjvf model.tar.bz2 ./outputs/train/...`

---

## Key AMD resources

| Resource | URL |
|---|---|
| AMD hackathon starter repo | `github.com/andrewgschmidt/AMD_Hackathon/tree/main/robotics/robotics_2026` |
| SO-101 example commands | `so101_example.md` in repo above |
| Seeed Studio SO-101 tutorial | `wiki.seeedstudio.com/lerobot_so100m_new` |
| LeRobot docs | `huggingface.co/docs/lerobot/so101` |
| DeepWiki (AI-powered LeRobot Q&A) | `deepwiki.com/huggingface/lerobot` |
| AMD Ryzers (Docker ML stack) | `github.com/AMDResearch/Ryzers` |
| AMD AUP AI Tutorials | `amdresearch.github.io/aup-ai-tutorials` |

---

## What success looks like at end-of-day

Voice → robot replies via Piper TTS within ~2 seconds → mode transitions with matching OLED eye expressions → "identify" speaks detected objects → "track" follows your face → "clean" runs either the ACT policy (50–70% success if training converges) or the scripted-waypoint fallback (guaranteed) → "idle" returns to neutral blinking eyes.

The AMD laptop's iGPU runs both LeRobot inference and Ollama via ROCm. It's a capable on-device AI platform — not just a USB controller for the arm.
