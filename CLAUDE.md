# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project: Sparky — AI Desk Companion

A voice-controlled robotic desk companion for children built on a WowRobo SO-101 arm. Sparky tracks faces, tutors kids by looking at their homework through a camera, and responds to voice commands. Built for the AMD StarkHacks hackathon. The robot character is named **Sparky**; the repo is **BOB-OT**.

---

## Hardware

| Device | Port | Power |
|---|---|---|
| SO-101 Follower arm | `/dev/ttyACM1` | 12V 8A — **do not swap** |
| SO-101 Leader arm | `/dev/ttyACM2` | 5V 6A — **do not swap** |
| Arduino Nano (OLED) | `/dev/ttyUSB0` (auto-detected) | USB |
| Side camera (face tracking) | `/dev/video2` | USB |
| Top camera (Gemini vision) | `/dev/video4` | USB |

Calibration files live at:
```
~/.cache/huggingface/lerobot/calibration/robots/so101_follower/my_awesome_follower_arm.json
~/.cache/huggingface/lerobot/calibration/teleoperators/so101_leader/my_awesome_leader_arm.json
```

---

## Environment

```bash
conda activate lerobot          # always required
export HSA_OVERRIDE_GFX_VERSION=11.0.0   # required for AMD iGPU — already in ~/.bashrc
sudo chmod 666 /dev/ttyACM1 /dev/ttyACM2 # required after each reboot
```

API keys must be set in `~/.bashrc`:
```bash
export GEMINI_API_KEY="..."
```

---

## Running the Project

**Primary entry point (full system):**
```bash
python companion.py
```

**Simple voice+vision only (no arm):**
```bash
python main.py
```

**Face tracking + OLED eyes only:**
```bash
python /home/aup/lerobot/face_track_eyes.py
```

**Move arm to a saved pose:**
```bash
python goto_pose.py home          # move and hold
python goto_pose.py home --once   # move and release torque
python goto_pose.py list          # show all saved poses
```

**Audio/hardware diagnostics:**
```bash
python test_audio.py              # test speaker devices
python /home/aup/lerobot/preview_cameras.py   # preview both cameras
```

---

## Architecture

### `companion.py` — Main entry point for full system

Three-state machine: `sleeping → tracking → desk_view`

- **sleeping**: Waits for "wake up". OLED shows BORED. Serial port owned by companion.
- **tracking**: Launches `face_track_eyes.py` as subprocess. OLED controlled by that subprocess. companion.py releases the serial port before launching it, reclaims it after killing it.
- **desk_view**: arm moves to home pose (held by `goto_pose.py` subprocess), camera captures frame, Gemini analyzes. OLED shows SCANNING. Follow-up answers go directly to `gemini.reply()` — no re-classification, no new snapshot.

**Serial port handoff pattern**: companion.py calls `eyes.disconnect()` before starting face_track_eyes.py, then `eyes.reconnect()` (with `dtr=False` to skip Arduino reset) after killing it.

**Intent routing** (`voice.py`):
- `knowledge` → answer via `gemini.ask_text()`, no arm movement
- `tutor` / `identify` → arm moves to home, camera snapshot, full Gemini tutor response
- `wake` / `idle` / `track` / `clean` → state transitions

**Hardcoded responses** (in companion.py `knowledge` handler):
- "what is your name" / "who are you" → fixed Sparky intro
- "running on" / "powered by" / "your cpu" → AMD Ryzen AI response

### `face_track_eyes.py` — Face tracking subprocess (`~/lerobot/`)

PID face tracker with integrated OLED control. Runs as a subprocess of companion.py. On SIGTERM, does NOT run finally cleanup (Python default SIGTERM behavior) — the OS releases the serial port and arm holds last position.

Key arm constants:
- `SHOULDER_LIFT = -55.0` (fixed)
- `ELBOW_FLEX = 40.0` (fixed)
- `WRIST_ROLL = -50.0` (fixed)
- `shoulder_pan` is the only moving joint, range ±60°

High-confidence lock: when face score > 0.5, arm freezes for 3 seconds (renews each frame the face stays above threshold).

OLED state map: SCANNING → FOUND (1s hold when face spotted) → TRACKING → LOST → back to SCANNING.

Camera frame is rotated 90° **clockwise** (`cv2.ROTATE_90_CLOCKWISE`) before face detection.

### `sparky.py` — TTS

Backend chain: ~~ElevenLabs~~ (disabled — IP flagged) → **Kokoro-ONNX** (primary) → espeak-ng (fallback).

- Voices file: `voices/voices-v1.0.bin` (54 voices, numpy pickled dict)
- Model file: `kokoro.onnx`
- Speaker device: `7` (amd-soundwire hw:3,2)
- All audio is converted mono→stereo before playback (device requires 2ch)

### `gemini_vision.py` — Vision-language AI

- `tutor(question, image)` — always captures a fresh snapshot; pass `image=` to skip capture
- `reply(answer)` — conversational follow-up, no snapshot, uses `conversation_history`
- `ask_text(question)` — pure text, no image, no history (for `knowledge` intents)
- `identify()` — scan desk, no question context
- Conversation history: `deque(maxlen=6)` — last 3 exchanges

### `voice.py` — STT + Intent

- Mic device: `8` (amd-soundwire hw:3,4)
- Record rate: 48000 Hz → resampled to 16000 Hz for Whisper
- Returns dict with `mode`, `target`, and `transcript` keys
- `transcript` = raw Whisper output (used for follow-up replies, bypasses intent classification)

### `goto_pose.py` — Arm pose control

Pose presets stored in `pose_presets.json`. Smoothly interpolates over 60 steps (~1.2s).
- `--once`: move then disconnect (releases torque, arm falls if unsupported)
- Without `--once`: holds pose in loop until Ctrl+C (used by companion.py to keep torque during Gemini analysis)

### `companion.py` `EyesController`

Manages serial lifecycle. Key methods:
- `connect()`: scans ports, flushes startup buffer with `reset_input_buffer()` before ACK check
- `disconnect()`: closes port so face_track_eyes.py can open it
- `reconnect()`: reopens with `dtr=False` to avoid Arduino reset delay

---

## OLED Emotions (Arduino Nano)

Commands sent as plain strings over serial at 115200 baud. Arduino ACKs each with `ACK:<command>`.

| Command | Expression |
|---|---|
| `SCANNING` | Pupils slide left/right |
| `FOUND` | Eyes grow wide |
| `TRACKING` | Happy squint + smile |
| `LOST` | Darting eyes + floating `?` |
| `BORED` | Droopy eyelids + wavy mouth |
| `NEUTRAL` | Gentle blink |

Sketch location: `arduino/eyes_sketch/eyes_sketch.ino`

---

## Known Quirks

- **Camera warmup**: After face_track_eyes.py releases `/dev/video2`, capture_snapshot() flushes 20 frames before reading to avoid black/stale frames.
- **kokoro-onnx v0.5.0 bug**: `speed` input was `int32` instead of `float32` — patched directly in the installed package at `kokoro_onnx/__init__.py`.
- **voices file format**: `voices-v1.0.bin` is a numpy pickled dict requiring `allow_pickle=True` — also patched in the installed package.
- **DESK_TIMEOUT**: 12 seconds. The "going back to tracking" warning only fires if the user has not yet pressed spacebar.
- **face_track_pid.py** exists as a legacy version without OLED — use `face_track_eyes.py` for all runs via companion.
