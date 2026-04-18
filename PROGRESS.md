# BOB-OT Desk Companion — Project Progress Report
**Date:** April 18, 2026
**Time:** 01:50 AM
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
| Conda env | lerobot | active |

---

## Completed Steps

### Track A — Arm + Manipulation

- [x] LeRobot v0.4.1 installed and verified via `lerobot-info`
- [x] PyTorch ROCm wheel confirmed (`torch==2.7.1+rocm6.3`)
- [x] iGPU detected as `AMD Radeon Graphics`
- [x] USB ports identified via `lerobot-find-port`
- [x] Port permissions set:
  - Follower arm → `/dev/ttyACM0` (`sudo chmod 666`)
  - Leader arm → `/dev/ttyACM1` (`sudo chmod 666`)
- [x] Teleoperation smoke test passed — running at **16.73ms / 60 Hz**
- [x] Cameras found via `lerobot-find-cameras opencv`
- [x] Teleoperation with camera feed confirmed:
  - Follower on `/dev/ttyACM2`
  - Leader on `/dev/ttyACM1`
  - Front camera at `/dev/video4` (1920×1080 @ 30fps)
  - `--display_data=true` active

### Infrastructure

- [x] SSH server installed and enabled (`openssh-server`)
- [x] GitHub SSH key added for `kseelams@purdue.edu`
- [x] Repo cloned: `kleverin/BOB-OT-Desk-Companion`
- [x] `conda activate lerobot` confirmed working

---

## In Progress

### Track A — Arm
- [ ] Arm calibration (follower + leader) — commands ready, not yet run
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
- [ ] YOLO11n objects_present_in_pickup_zone()
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

## Known Issues / Blockers

- `HSA_OVERRIDE_GFX_VERSION=11.0.0` — needs verification that it is set in `~/.bashrc` and `torch.cuda.is_available()` returns `True`
- Arm calibration not yet run — required before data collection
- ElevenLabs and Gemini API keys not yet configured
- Kokoro model files not yet downloaded
- `pynput==1.7.7` + Xorg required for arrow key recording — confirm login screen is set to Xorg before data collection

---

## Next Immediate Steps

```bash
# 1. Verify GPU is accessible
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# 2. Calibrate follower arm
lerobot-calibrate \
    --robot.type=so101_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=my_awesome_follower_arm

# 3. Calibrate leader arm
lerobot-calibrate \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM1 \
    --teleop.id=my_awesome_leader_arm

# 4. Pull offline models
ollama pull llava
ollama pull llama3.2:3b
python -c "from kokoro_onnx import Kokoro; Kokoro.download()"

# 5. Set API keys
echo 'export ELEVENLABS_API_KEY="your_key_here"' >> ~/.bashrc
echo 'export GEMINI_API_KEY="your_key_here"' >> ~/.bashrc
source ~/.bashrc
```

---

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
├── PROGRESS.md           # This file
└── arduino/
    └── eyes_sketch/
        └── eyes_sketch.ino
```
