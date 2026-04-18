# Architectural Patterns

Patterns observed across both BOB-OT-Desk-Companion and the LeRobot library it depends on.

---

## BOB-OT Application Patterns

### 1. Single-Responsibility Module Split

Each Python module owns exactly one system domain; no cross-domain logic:

| Module | Domain | Inputs | Outputs |
|---|---|---|---|
| `arm.py` | Motor control | joint position dicts | LeRobot `send_action()` calls |
| `voice.py` | Speech input | audio stream | intent string → mode dispatch |
| `vision.py` | Visual perception | camera frames | bounding boxes, face coords |
| `eyes.py` | OLED expression | expression enum | Arduino serial bytes |
| `sparky.py` | Speech output | text string | audio playback (no return value) |
| `gemini_vision.py` | Vision-language | PIL image + prompt | text description |

Implication: inter-module calls pass only simple types (dicts, strings, numpy arrays) — no shared mutable state.

### 2. Fallback Chain (Graceful Degradation)

Applied wherever a cloud service has an offline alternative. Pattern: try primary, catch exception, try next.

**TTS chain** (`sparky.py`):
```
ElevenLabs (cloud, "Aria" voice ID: EXAVITQu4vr4xnSDxMaL)
  ↓ on API error / no network
Kokoro-ONNX (local, af_sky voice)
  ↓ on model unavailable
Piper (minimal, always available)
```

**Vision-language chain** (`gemini_vision.py`):
```
Gemini 2.0 Flash (cloud API)
  ↓ on API error / no network
LLaVA via Ollama (local, must be pre-pulled)
```

**STT** (`voice.py`): faster-whisper runs locally — no fallback needed.

### 3. Mode-Based State Machine

`main.py` acts as a flat state machine with six states. No concurrent mode execution.

```
IDLE
├─► IDENTIFY  (Gemini vision: "what is this?")
├─► TRACK     (MediaPipe: follow face/hand)
├─► CLEAN     (ACT policy: learned cleaning motion)
├─► TUTOR     (Ollama LLM: explain/answer)
└─► LISTEN    (Whisper STT: transcribe + respond)
```

Mode transitions triggered by voice commands parsed in `voice.py`. The dispatcher in `main.py` calls the appropriate module and blocks until the mode exits.

### 4. Hardware Abstraction via LeRobot

BOB-OT never talks to servos directly. All motor I/O goes through LeRobot's `SO101Follower` and `SO101Leader` classes, which handle:
- Serial framing (Feetech protocol)
- Encoder calibration (cached at `~/.cache/huggingface/lerobot/calibration/`)
- Safety clamping (`max_relative_target`)
- Observation dict normalization

`arm.py` wraps these classes and exposes only what BOB-OT needs (current positions, send target).

### 5. Background Thread for Continuous Perception

`vision.py` runs face/object detection in a daemon thread, writing to a shared variable that `main.py` reads. The main thread issues commands; the vision thread updates state continuously. Use a `threading.Lock` around the shared variable.

---

## LeRobot Library Patterns

These patterns appear in `/home/aup/lerobot/src/lerobot/` and are relevant when reading or extending LeRobot internals.

### 6. Factory Functions with Dynamic Dispatch

Every major subsystem exposes a `make_*()` factory in its `factory.py`. Callers pass a type string; the factory imports the concrete class lazily (avoiding unnecessary dependency loading).

Files: `policies/factory.py`, `datasets/factory.py`, `envs/factory.py`, `optim/factory.py`, `processor/factory.py`, `cameras/utils.py`

```python
# Pattern seen in each factory.py:
def make_policy(cfg: PreTrainedConfig) -> PreTrainedPolicy:
    if cfg.type == "act":
        from lerobot.policies.act.modeling_act import ACTPolicy
        return ACTPolicy(cfg)
    elif cfg.type == "diffusion":
        ...
```

### 7. Dataclass Configuration with CLI Override (Draccus)

All configs are frozen dataclasses. Hierarchical composition (`TrainPipelineConfig` contains `DatasetConfig`, `PolicyConfig`, etc.). CLI args map directly to dataclass fields via dot notation.

Files: `configs/train.py`, `configs/eval.py`, `robots/*/config_*.py`, `policies/*/configuration_*.py`

```
# CLI override pattern
lerobot-train --policy.type=act --policy.dim_model=256 --dataset.repo_id=lerobot/pusht
```

### 8. Abstract Base Class Contract

`Robot`, `Camera`, `PreTrainedPolicy`, and `MotorsBus` all define ABCs. Concrete subclasses must implement `observation_features`, `action_features`, `connect()`, `disconnect()`, and `send_action()` / `read()`.

Files: `robots/robot.py`, `cameras/camera.py`, `policies/pretrained.py`, `motors/motors_bus.py`

### 9. Delta Timestamps for Temporal Observations

LeRobot datasets support multi-frame temporal queries via `delta_timestamps`. A single `dataset[idx]` call can return frames from multiple past timesteps, aligned by wall-clock offset.

Files: `datasets/lerobot_dataset.py`, `datasets/utils.py`

```python
batch = dataset[idx, delta_timestamps={"observation.image": [-1.0, -0.5, 0.0]}]
# Returns 3 stacked frames: 1s ago, 0.5s ago, current
```

### 10. Processor Pipeline (Pre/Post Normalization)

`PolicyProcessorPipeline` wraps every policy. It normalizes observations to zero-mean/unit-variance before the model and clips/denormalizes actions after. Statistics computed from dataset and stored in the checkpoint.

Files: `processor/factory.py`, `processor/converters.py`, `policies/utils.py`

### 11. HubMixin for Checkpoint Portability

Policy configs inherit `HubMixin`, enabling one-line push/pull to Hugging Face Hub. BOB-OT's ACT checkpoint trained on AMD MI300X can be loaded anywhere with:

```python
cfg = PreTrainedConfig.from_pretrained("username/bob-ot-act")
```

Files: `utils/hub.py`, all `configuration_*.py` files.

---

## Key Invariants

- **Power wiring**: SO-101 Leader = 5V 6A, Follower = 12V 8A. Swapping kills hardware.
- **ROCm env var**: `HSA_OVERRIDE_GFX_VERSION=11.0.0` must be set before any torch import on the Ryzen AI laptop.
- **Calibration cache**: Delete `~/.cache/huggingface/lerobot/calibration/` only when physically recalibrating; stale cache causes arm drift.
- **Numpy version**: Must be `<2.0` — LeRobot 0.4.1 has ABI incompatibilities with numpy 2.x.
