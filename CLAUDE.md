# BOB-OT Desk Companion

Interactive tabletop robot companion for children built on a WowRobo SO-101 arm, designed for the AMD StarkHacks hackathon. Integrates voice, vision-language AI, and teleoperative arm control into a six-mode desk assistant ("Sparky").

**Companion library:** `/home/aup/lerobot` (LeRobot v0.4.1) — all arm control and camera abstraction flows through it.

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10.20 |
| Arm control | LeRobot 0.4.1 (`SO101Follower`, `SO101Leader`) |
| ML runtime | PyTorch 2.7.1+rocm6.3 (AMD ROCm iGPU) |
| Vision-language | Gemini 2.0 Flash (primary), LLaVA via Ollama (offline fallback) |
| Object detection | YOLO11n (ultralytics) |
| Hand/face tracking | MediaPipe 0.10.9 |
| STT | faster-whisper |
| TTS chain | ElevenLabs → Kokoro-ONNX → Piper |
| Local LLM | Ollama (llava, llama3.2:3b) |
| OLED display | Arduino + SSD1306 via PySerial |

## Project Structure

```
BOB-OT-Desk-Companion/
├── main.py            # ModeSwitcher state machine — entry point
├── arm.py             # LeRobot SO101Follower wrapper + ACT inference
├── voice.py           # faster-whisper STT + Ollama intent routing
├── vision.py          # YOLO detection + MediaPipe face/hand tracking
├── eyes.py            # Arduino serial controller for OLED expression
├── sparky.py          # TTS abstraction (ElevenLabs → Kokoro → Piper)
├── gemini_vision.py   # Gemini 2.0 Flash API + LLaVA fallback
├── config.py          # Global constants: ports, device paths, API keys
├── arduino/
│   └── eyes_sketch/eyes_sketch.ino
├── desk_companion_final.md   # Hardware pinouts, mode specs, full setup
├── PROGRESS.md               # Live hackathon status and TODOs
└── TROUBLESHOOTING.md        # Port mapping, quick-start checklist
```

**Prototype (in lerobot repo):** `~/lerobot/palm_track.py` — MediaPipe hand → arm tracking proof-of-concept.

## Six Robot Modes

`IDLE → IDENTIFY → TRACK → CLEAN → TUTOR → LISTEN`

Each mode maps to a distinct backend; `main.py` prevents concurrent execution.

## Hardware

- SO-101 Leader: `/dev/ttyACM1` (5V 6A — **do not swap power**)
- SO-101 Follower: `/dev/ttyACM2` (12V 8A — **do not swap power**)
- Arduino OLED: `/dev/ttyUSB0`
- Camera TOP: `/dev/video4` (vision AI input)
- Camera SIDE: face tracking input

## Essential Commands

```bash
# One-time: grant port access
sudo chmod 666 /dev/ttyACM1 /dev/ttyACM2

# Activate environment
conda activate lerobot && cd ~/lerobot

# Verify GPU (must print AMD Radeon Graphics)
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# Teleoperation (verified working at 16.73ms / 60Hz)
lerobot-teleoperate \
  --robot.type=so101_follower --robot.port=/dev/ttyACM2 \
  --robot.id=my_awesome_follower_arm \
  --robot.cameras="{ front: {type: opencv, index_or_path: /dev/video4, width: 1920, height: 1080, fps: 30}}" \
  --teleop.type=so101_leader --teleop.port=/dev/ttyACM1 \
  --teleop.id=my_awesome_leader_arm --display_data=true

# Run prototype hand-tracking
python3 ~/lerobot/palm_track.py

# Pull offline models before demo (do once, needs network)
ollama pull llava && ollama pull llama3.2:3b
python -c "from kokoro_onnx import Kokoro; Kokoro.download()"

# Discover hardware
lerobot-find-cameras opencv
lerobot-find-port
```

## ROCm Environment Variable (required for iGPU)

```bash
export HSA_OVERRIDE_GFX_VERSION=11.0.0
```

Add to `~/.bashrc` or set in `config.py` via `os.environ`.

## Additional Documentation

| File | When to check |
|---|---|
| `desk_companion_final.md` | Hardware pinouts, power wiring, mode trigger phrases, camera routing |
| `PROGRESS.md` | Current hackathon status, what's working, what's pending |
| `TROUBLESHOOTING.md` | Device port issues, calibration cache location, quick-start steps |
| `.claude/docs/architectural_patterns.md` | Module responsibilities, fallback chains, state machine design |
| `.claude/docs/lerobot_reference.md` | Full LeRobot symbol index: every class, function, constant with file:line |
