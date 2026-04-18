# BOB-OT Desk Companion — Project Progress Report
**Date:** April 18, 2026  
**Time:** 03:40 AM
**Hackathon:** AMD StarkHacks  
**Team:** kleverin/BOB-OT-Desk-Companion  
**Hardware:** WowRobo SO-101 + AMD Ryzen AI 9 HX370 laptop (Ubuntu 24.04)

---

## Environment Status

| Component | Version | Status |
|---|---|---|
| LeRobot | 0.4.1 (pinned) | confirmed |
| PyTorch | 2.7.1+rocm6.3 | confirmed |
| Python | 3.10.20 | confirmed |
| ROCm | 6.3 | confirmed |
| GPU | AMD Radeon Graphics (RDNA 3.5 iGPU) | recognized |
| Platform | Linux 6.17.0-20-generic x86_64 | confirmed |
| HuggingFace Hub | 0.35.3 | confirmed |
| MediaPipe | 0.10.9 | confirmed |
| OpenCV | confirmed | confirmed |
| Conda env | lerobot | active |

---

## Completed Steps

### Track A — Arm + Manipulation

- [x] LeRobot v0.4.1 installed and verified via `lerobot-info`
- [x] PyTorch ROCm wheel confirmed (`torch==2.7.1+rocm6.3`)
- [x] iGPU detected as `AMD Radeon Graphics`
- [x] USB ports identified via `lerobot-find-port`
- [x] Port permissions set:
  - Follower arm → `/dev/ttyACM2`
  - Leader arm → `/dev/ttyACM1`
- [x] Teleoperation with camera confirmed running at **16.73ms / 60 Hz**
- [x] Cameras found via `lerobot-find-cameras opencv`
- [x] Front camera confirmed at `/dev/video4` (1920×1080 @ 30fps)
- [x] Follower arm calibration file present at:
  `~/.cache/huggingface/lerobot/calibration/robots/so101_follower/my_awesome_follower_arm.json`
- [x] Leader arm calibration file present at:
  `~/.cache/huggingface/lerobot/calibration/teleoperators/so101_leader/my_awesome_leader_arm.json`
- [x] Palm tracking script written and tested — MediaPipe detects palm, arm tracks correctly
- [x] Verified SO101Follower API keys: `shoulder_pan.pos`, `shoulder_lift.pos`, `elbow_flex.pos`, `wrist_flex.pos`, `wrist_roll.pos`, `gripper.pos`
- [x] Arm moves to neutral (0.0 on all joints) on script startup and returns to neutral on quit

### Infrastructure

- [x] SSH server installed and enabled (`openssh-server`)
- [x] GitHub SSH key added for `kseelams@purdue.edu`
- [x] Repo cloned: `kleverin/BOB-OT-Desk-Companion`
- [x] `conda activate lerobot` confirmed working

---

## Key Commands

### Teleoperation with camera
```bash
sudo chmod 666 /dev/ttyACM1 /dev/ttyACM2
conda activate lerobot
cd ~/lerobot

lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=/dev/ttyACM2 \
  --robot.id=my_awesome_follower_arm \
  --robot.cameras="{ front: {type: opencv, index_or_path: /dev/video4, width: 1920, height: 1080, fps: 30}}" \
  --teleop.type=so101_leader \
  --teleop.port=/dev/ttyACM1 \
  --teleop.id=my_awesome_leader_arm \
  --display_data=true
```

### Palm tracking (follower arm follows your hand)
```bash
sudo chmod 666 /dev/ttyACM2
conda activate lerobot
cd ~/lerobot
python3 palm_track.py
```

Script location: `~/lerobot/palm_track.py`

- Show palm to side camera (index 2, `/dev/video*`)
- Arm tracks left/right and up/down in real time at ~60Hz
- Arm moves to neutral position on startup
- Press **Q** to quit — arm returns to neutral before disconnecting
- Smoothing factor: 0.6 (adjustable at top of script)
- Pan range: -60° to +60° | Tilt range: -30° to +45°

---

## In Progress

### Track A — Arm
- [ ] Data collection — 50 episodes target
- [ ] Dataset push to HuggingFace Hub
- [ ] ACT policy training on AMD Dev Cloud MI300X
- [ ] Scripted waypoint fallback

### Track B — Voice + Gemini Vision
- [ ] `sparky.py` — ElevenLabs + Kokoro + Piper TTS chain
- [ ] `gemini_vision.py` — identify() + tutor() with streaming
- [ ] ElevenLabs API key setup
- [ ] Gemini API key setup (aistudio.google.com)
- [ ] Kokoro model download
- [ ] Ollama LLaVA fallback pull

### Track C — Vision
- [ ] `vision.py` — MediaPipe face detection on side camera
- [ ] YOLO11n `objects_present_in_pickup_zone()`
- [ ] VisionModule background thread

### Track D — Eyes
- [ ] Arduino wired to SSD1306 OLED
- [ ] RoboEyes sketch flashed
- [ ] `eyes.py` serial controller
- [ ] All mode transitions mapped

### Integration
- [ ] `main.py` ModeSwitcher
- [ ] `config.py` constants
- [ ] `startup_check()` all systems
- [ ] Hour 7 branch merge
- [ ] Demo rehearsal

---

## Robot Modes Planned

| Mode | Trigger | Backend |
|---|---|---|
| IDLE | "stop" / "rest" | OLED eyes only |
| IDENTIFY | "what do you see?" | Gemini 2.0 Flash → LLaVA fallback |
| TRACK | "follow me" | MediaPipe face detection |
| CLEAN | "clean up" | YOLO + ACT policy / scripted fallback |
| TUTOR | "help me" / "explain this" | Gemini 2.0 Flash with conversation history |
| LISTEN | spacebar held | faster-whisper STT |

---

## Port + Device Map

| Device | Port | Notes |
|---|---|---|
| Follower arm | `/dev/ttyACM2` | SO101 Follower |
| Leader arm | `/dev/ttyACM1` | SO101 Leader |
| Front camera | `/dev/video4` | 1920×1080 @ 30fps, overhead |
| Side camera | index 2 | 640×480, used for palm/face tracking |
| Arduino (OLED) | `/dev/ttyUSB0` | TBD — not yet connected |

---

## Known Issues / Blockers

- `HSA_OVERRIDE_GFX_VERSION=11.0.0` — verify set in `~/.bashrc` and `torch.cuda.is_available()` returns `True`
- ElevenLabs and Gemini API keys not yet configured
- Kokoro model files not yet downloaded
- `pynput==1.7.7` + Xorg required for arrow key recording — confirm Xorg at login before data collection
- protobuf downgraded to 3.20.3 by mediapipe==0.10.9 — monitor for conflicts with other packages

---

## Next Immediate Steps

```bash
# 1. Verify GPU
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# 2. Start data collection (switch to Xorg first at login screen)
# 3. Pull offline models
ollama pull llava
ollama pull llama3.2:3b
python -c "from kokoro_onnx import Kokoro; Kokoro.download()"

# 4. Set API keys
echo 'export ELEVENLABS_API_KEY="your_key_here"' >> ~/.bashrc
echo 'export GEMINI_API_KEY="your_key_here"' >> ~/.bashrc
source ~/.bashrc
```

---

## File Structure (current)

```
BOB-OT-Desk-Companion/
├── PROGRESS.md                  # this file
~/lerobot/
├── palm_track.py                # palm tracking script (arm follows hand)
~/.cache/huggingface/lerobot/calibration/
├── robots/so101_follower/my_awesome_follower_arm.json
└── teleoperators/so101_leader/my_awesome_leader_arm.json
```

## File Structure (target)

```
BOB-OT-Desk-Companion/
├── main.py               # ModeSwitcher — entry point
├── arm.py                # LeRobot arm + waypoint fallback
├── voice.py              # faster-whisper STT + Ollama intent routing
├── vision.py             # YOLO + MediaPipe background thread
├── eyes.py               # Arduino OLED serial controller
├── sparky.py             # Character TTS — ElevenLabs/Kokoro/Piper
├── gemini_vision.py      # Gemini 2.0 Flash + LLaVA fallback
├── config.py             # All constants
├── requirements.txt
├── PROGRESS.md
└── arduino/
    └── eyes_sketch/
        └── eyes_sketch.ino
```
