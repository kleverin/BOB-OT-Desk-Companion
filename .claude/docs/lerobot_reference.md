# LeRobot Library Reference

Complete symbol index for `/home/aup/lerobot/src/lerobot/`. Use this to find the right class, function, or constant when writing BOB-OT code without re-exploring the library.

---

## Quick Reference (Most-Used in BOB-OT)

```python
# Connect arm
from lerobot.robots.so101_follower.so101_follower import SO101Follower
from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig
cfg = SO101FollowerConfig(port="/dev/ttyACM2", id="my_awesome_follower_arm")
robot = SO101Follower(cfg)
robot.connect()                          # calibrate=True by default
obs = robot.get_observation()            # dict: {"shoulder_pan.pos": float, ..., "observation.images.front": np.ndarray}
robot.send_action({"shoulder_pan.pos": 0.0, "shoulder_lift.pos": 10.0})
robot.disconnect()

# Connect leader (teleop)
from lerobot.teleoperators.so101_leader.so101_leader import SO101Leader
from lerobot.teleoperators.so101_leader.config_so101_leader import SO101LeaderConfig
leader = SO101Leader(SO101LeaderConfig(port="/dev/ttyACM1"))
leader.connect()
action = leader.get_action()             # same key format as robot action

# Open camera
from lerobot.cameras.opencv.camera_opencv import OpenCVCamera
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
cam = OpenCVCamera(OpenCVCameraConfig(index_or_path="/dev/video2", width=640, height=480, fps=30))
cam.connect()
frame = cam.read()                       # np.ndarray HWC BGR
frame = cam.async_read(timeout_ms=200)  # non-blocking

# Device / seed utils
from lerobot.utils.utils import auto_select_torch_device
from lerobot.utils.random_utils import set_seed
device = auto_select_torch_device()     # picks cuda/rocm/mps/cpu
set_seed(42)

# Busy-wait (real-time loops)
from lerobot.utils.robot_utils import busy_wait
busy_wait(0.016)                         # 16ms, platform-aware (not time.sleep)

# Policy inference
from lerobot.utils.control_utils import predict_action, init_keyboard_listener
```

---

## robots/

**Abstract base** — `src/lerobot/robots/robot.py`
- `Robot` (ABC) L30 — base for all robots
  - `observation_features` (property, abstract) L62 — dict describing obs keys and shapes
  - `action_features` (property, abstract) L77 — dict describing action keys and shapes
  - `is_connected` (property, abstract) L90
  - `connect(calibrate=True)` L99
  - `is_calibrated` (property, abstract) L111
  - `calibrate()` L116
  - `get_observation() -> dict` L156
  - `send_action(action: dict) -> dict` L168
  - `disconnect()` L183
  - `_load_calibration(fpath=None)` L125
  - `_save_calibration(fpath=None)` L136
- `RobotConfig` (dataclass ABC) — `src/lerobot/robots/config.py:23`
  - `id: str | None`, `calibration_dir: Path | None`

**Factory** — `src/lerobot/robots/utils.py`
- `make_robot_from_config(config: RobotConfig) -> Robot` L25
- `ensure_safe_goal_position(goal_present_pos, max_relative_target) -> dict` L71 — safety clamp

**SO101 Follower** — `src/lerobot/robots/so101_follower/`
- `SO101Follower(Robot)` — `so101_follower.py:37`
  - Motors: shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper (all Feetech STS3215)
  - `connect()` L85, `calibrate()` L110, `configure()` L153
  - `get_observation()` L175 — returns motor positions + camera frames
  - `send_action(action)` L195
- `SO101FollowerConfig(RobotConfig)` — `config_so101_follower.py`
  - `port: str`, `disable_torque_on_disconnect: bool = True`
  - `max_relative_target: float | dict | None = None`
  - `cameras: dict[str, CameraConfig] = {}`
  - `use_degrees: bool = False`

**SO100 Follower** — `src/lerobot/robots/so100_follower/`
- `SO100Follower(Robot)` — `so100_follower.py:37` (same interface as SO101)
- `SO100FollowerConfig(RobotConfig)` — `config_so100_follower.py`

**Koch Follower** — `src/lerobot/robots/koch_follower/`
- `KochFollower(Robot)` — `koch_follower.py:37` (uses Dynamixel motors)
- `KochFollowerConfig(RobotConfig)` — `config_koch_follower.py`

**BiSO100 Follower** (dual-arm) — `src/lerobot/robots/bi_so100_follower/`
- `BiSO100Follower(Robot)` — `bi_so100_follower.py`
- `BiSO100FollowerConfig` — `config_bi_so100_follower.py`

**Hope Jr** — `src/lerobot/robots/hope_jr/`
- `HopeJrArm(Robot)` — `hope_jr_arm.py:37` — 7-DOF (SM8512BL + STS3250)
- `HopeJrHand(Robot)` — `hope_jr_hand.py:61`
- `HopeJrArmConfig`, `HopeJrHandConfig` — `config_hope_jr.py`

**LeKiwi** (mobile) — `src/lerobot/robots/lekiwi/`
- `LeKiwi(Robot)` — `lekiwi.py:40` — 9 motors (6 arm + 3 wheels)
- `LeKiwiConfig`, `LeKiwiHostConfig`, `LeKiwiClientConfig` — `config_lekiwi.py`
- `LeKiwiHost` — `lekiwi_host.py`, `LeKiwiClient` — `lekiwi_client.py`

**Reachy2** — `src/lerobot/robots/reachy2/`
- `Reachy2Robot(Robot)` — `robot_reachy2.py:70`
- `Reachy2RobotConfig` — `configuration_reachy2.py`

---

## teleoperators/

**Abstract base** — `src/lerobot/teleoperators/teleoperator.py`
- `Teleoperator` (ABC) L28
  - `action_features` (property, abstract) L61
  - `feedback_features` (property, abstract) L74
  - `connect(calibrate=True)` L96, `calibrate()` L112
  - `get_action() -> dict` L152
  - `send_feedback(feedback: dict)` L163
  - `disconnect()` L178
- `TeleoperatorConfig` (dataclass ABC) — `src/lerobot/teleoperators/config.py:23`
- `TeleopEvents(Enum)` — `utils.py:24`
  - SUCCESS, FAILURE, RERECORD_EPISODE, IS_INTERVENTION, TERMINATE_EPISODE
- `make_teleoperator_from_config(config)` — `utils.py:34`

**SO101 Leader** — `src/lerobot/teleoperators/so101_leader/`
- `SO101Leader(Teleoperator)` — `so101_leader.py:33`
- `SO101LeaderConfig` — `config_so101_leader.py`
  - `port: str`, `id: str | None`, `calibration_dir: Path | None`

**SO100 Leader** — `src/lerobot/teleoperators/so100_leader/`
- `SO100Leader(Teleoperator)` — `so100_leader.py:33`
- `SO100LeaderConfig` — `config_so100_leader.py`

**Koch Leader** — `src/lerobot/teleoperators/koch_leader/`
- `KochLeader(Teleoperator)` — `koch_leader.py` (Dynamixel)
- `KochLeaderConfig` — `config_koch_leader.py`

**Keyboard** — `src/lerobot/teleoperators/keyboard/`
- `KeyboardTeleop(Teleoperator)` — `teleop_keyboard.py:46` (pynput)
- `KeyboardEndEffectorTeleop` — `teleop_keyboard.py:151`
- `KeyboardTeleopConfig`, `KeyboardEndEffectorTeleopConfig` — `configuration_keyboard.py`

**Gamepad** — `src/lerobot/teleoperators/gamepad/`
- `GamepadTeleop(Teleoperator)` — `teleop_gamepad.py:41`
  - Action keys: `delta_x, delta_y, delta_z, gripper`
- `GripperAction(IntEnum)` L28 — CLOSE(0), STAY(1), OPEN(2)
- `GamepadController`, `KeyboardController`, `GamepadControllerHID` — `gamepad_utils.py`

**Phone** — `src/lerobot/teleoperators/phone/`
- `Phone(Teleoperator)` — `teleop_phone.py` (dispatches to iOS/Android)
- `IOSPhone`, `AndroidPhone` — `teleop_phone.py`
- `PhoneConfig`, `PhoneOS(Enum)` — `config_phone.py`

**Homunculus** — `src/lerobot/teleoperators/homunculus/`
- `HomunculusGlove(Teleoperator)` — `homunculus_glove.py:60`
- `HomunculusArm(Teleoperator)` — `homunculus_arm.py:34`
- `HomunculusGloveConfig`, `HomunculusArmConfig` — `config_homunculus.py`

---

## cameras/

**Abstract base** — `src/lerobot/cameras/camera.py:25`
- `Camera` (ABC)
  - `connect(warmup=True)` L81, `disconnect()` L118
  - `read(color_mode=None) -> np.ndarray` L92 — blocking, returns HWC
  - `async_read(timeout_ms=200) -> np.ndarray` L105 — non-blocking
  - `find_cameras() -> list[dict]` L71 (static)
- `CameraConfig` (dataclass ABC) — `src/lerobot/cameras/configs.py:37`
  - `fps: int | None`, `width: int | None`, `height: int | None`
- `ColorMode(str, Enum)` — `configs.py:24` — RGB, BGR
- `Cv2Rotation(int, Enum)` — `configs.py:29`
  - NO_ROTATION(0), ROTATE_90(90), ROTATE_180(180), ROTATE_270(-90)

**Factory** — `src/lerobot/cameras/utils.py`
- `make_cameras_from_configs(camera_configs: dict[str, CameraConfig]) -> dict[str, Camera]` L26
- `get_cv2_rotation(rotation: Cv2Rotation) -> int | None` L55
- `get_cv2_backend() -> int` L68 — platform-specific

**OpenCV Camera** — `src/lerobot/cameras/opencv/`
- `OpenCVCamera(Camera)` — `camera_opencv.py:51`
  - Supports index (0,1,...) or device path ("/dev/video2")
  - `MAX_OPENCV_INDEX = 60` L46
- `OpenCVCameraConfig(CameraConfig)` — `configuration_opencv.py`
  - `index_or_path: int | str | Path`
  - `color_mode: ColorMode = ColorMode.RGB`
  - `rotation: Cv2Rotation = Cv2Rotation.NO_ROTATION`
  - `warmup_s: float = 1`
  - `fourcc: str | None = None`

**RealSense Camera** — `src/lerobot/cameras/realsense/`
- `RealSenseCamera(Camera)` — `camera_realsense.py:43`
- `RealSenseCameraConfig(CameraConfig)` — `configuration_realsense.py`
  - `serial_number_or_name: str | int`, `use_depth: bool = False`

**Reachy2 Camera** — `src/lerobot/cameras/reachy2_camera/`
- `Reachy2Camera(Camera)` — `reachy2_camera.py:46`
- `Reachy2CameraConfig` — `configuration_reachy2_camera.py`

---

## motors/

**Abstract base + helpers** — `src/lerobot/motors/motors_bus.py`
- `MotorCalibration` (dataclass) L87 — `id, drive_mode, homing_offset, range_min, range_max`
- `Motor` (dataclass) L96 — `id, model, norm_mode`
- `MotorNormMode(str, Enum)` L80 — RANGE_0_100, RANGE_M100_100, DEGREES
- `MotorsBus` (ABC) L206 — abstract motor communication bus
- `get_ctrl_table(model_ctrl_table, model)` L44
- `get_address(model_ctrl_table, model, data_name)` L51

**Encoding** — `src/lerobot/motors/encoding_utils.py`
- `encode_sign_magnitude(value, sign_bit_index)` L16
- `decode_sign_magnitude(encoded_value, sign_bit_index)` L29
- `encode_twos_complement(value, n_bytes)` L39
- `decode_twos_complement(value, n_bytes)` L59

**Calibration GUI** — `src/lerobot/motors/calibration_gui.py`
- `RangeFinderGUI` L218 — interactive Tkinter GUI for motor range calibration
- `RangeSlider` L56, `RangeValues` L50

**Feetech** (SO-100/101 motors) — `src/lerobot/motors/feetech/`
- `FeetechMotorsBus(MotorsBus)` — `feetech.py:99`
  - DEFAULT_BAUDRATE = 1,000,000
  - NORMALIZED_DATA = ["Goal_Position", "Present_Position"]
- `OperatingMode(Enum)` L45 — POSITION(0), VELOCITY(1), PWM(2), STEP(3)
- `DriveMode(Enum)` L59 — NON_INVERTED(0), INVERTED(1)
- `TorqueMode(Enum)` L64 — ENABLED(1), DISABLED(0)
- Motor models in `tables.py`: STS3215, STS3250, SMS3215, SM8512BL

**Dynamixel** (Koch motors) — `src/lerobot/motors/dynamixel/`
- `DynamixelMotorsBus(MotorsBus)` — `dynamixel.py:103`
  - DEFAULT_BAUDRATE = 1,000,000
- `OperatingMode(Enum)` L46 — CURRENT(0), VELOCITY(1), POSITION(3), EXTENDED_POSITION(4), CURRENT_POSITION(5), PWM(16)
- `DriveMode(Enum)` L76, `TorqueMode(Enum)` L81
- Motor models: XL330-M288, XL430-W250 (in `tables.py`)

---

## policies/

**Abstract base** — `src/lerobot/policies/pretrained.py`
- `PreTrainedPolicy(nn.Module, HubMixin, ABC)` L44
  - `get_optim_params() -> dict` L160 (abstract)
  - `reset()` L167 (abstract) — call on env reset
  - `forward(batch) -> tuple[Tensor, dict | None]` L176 (abstract)
  - `predict_action_chunk(batch, **kwargs)` L189 (abstract)
  - `select_action(batch, **kwargs)` L198 (abstract)
  - `from_pretrained(pretrained_name_or_path, config, ...)` L75 (classmethod)
  - `push_model_to_hub(cfg)` L206

**Factory** — `src/lerobot/policies/factory.py`
- `get_policy_class(name: str)` L53 — "act", "diffusion", "tdmpc", "vqbet", "pi0", "pi05", "sac", "smolvla", "groot"
- `make_policy_config(policy_type, **kwargs)` L114
- `make_pre_post_processors(policy_cfg, pretrained_path, **kwargs)` L179
- `make_policy(cfg, ds_meta, env_cfg, rename_map)` L339

**Utilities** — `src/lerobot/policies/utils.py`
- `prepare_observation_for_inference(observation, device, task, robot_type)` L99
- `build_inference_frame(observation, device, ds_features, task, robot_type)` L142
- `make_robot_action(action_tensor, ds_features)` L176
- `populate_queues(queues, batch, exclude_keys)` L32
- `get_device_from_parameters(module)` L52, `get_dtype_from_parameters(module)` L60

**ACT** — `src/lerobot/policies/act/`
- `ACTPolicy(PreTrainedPolicy)` — `modeling_act.py`
- `ACTConfig` — `configuration_act.py` (@register_subclass("act"))
  - `n_obs_steps=1`, `chunk_size=100`, `n_action_steps=100`
  - `vision_backbone="resnet18"`, `dim_model=512`, `n_heads=8`
  - `use_vae=True`, `latent_dim=32`, `kl_weight=10.0`
  - `optimizer_lr=1e-5`

**Diffusion** — `src/lerobot/policies/diffusion/`
- `DiffusionPolicy(PreTrainedPolicy)` — `modeling_diffusion.py`
- `DiffusionConfig` — `configuration_diffusion.py` (@register_subclass("diffusion"))
  - `n_obs_steps=2`, `horizon=16`, `n_action_steps=8`
  - `noise_scheduler_type="DDPM"`, `num_train_timesteps=100`

**SmolVLA** — `src/lerobot/policies/smolvla/`
- `SmolVLAConfig` — `configuration_smolvla.py` (@register_subclass("smolvla"))
  - `vlm_model_name="HuggingFaceTB/SmolVLM2-500M-Video-Instruct"`
  - `chunk_size=50`, `max_state_dim=32`, `max_action_dim=32`
  - `freeze_vision_encoder=True`, `train_expert_only=True`

**PI0** — `src/lerobot/policies/pi0/`
- `PI0Config` — `configuration_pi0.py` (@register_subclass("pi0"))
  - `paligemma_variant="gemma_2b"`, `chunk_size=50`, `num_inference_steps=10`

**PI05** — `src/lerobot/policies/pi05/`
- `PI05Config` — `configuration_pi05.py` (@register_subclass("pi05"))

**TDMPC** — `src/lerobot/policies/tdmpc/`
- `TDMPCConfig` — `configuration_tdmpc.py` (@register_subclass("tdmpc"))
  - `horizon=5`, `n_action_repeats=2`, `latent_dim=50`

**VQ-BeT** — `src/lerobot/policies/vqbet/`
- `VQBeTConfig` — `configuration_vqbet.py` (@register_subclass("vqbet"))

**GR00T** — `src/lerobot/policies/groot/`
- `GrootConfig` — `configuration_groot.py` (@register_subclass("groot"))
  - `base_model_path="nvidia/GR00T-N1.5-3B"`

**SAC (RL)** — `src/lerobot/policies/sac/`
- `configuration_sac.py`, `modeling_sac.py`, `processor_sac.py`

---

## datasets/

**Main class** — `src/lerobot/datasets/lerobot_dataset.py`
- `LeRobotDataset(torch.utils.data.Dataset)` L542
  - `dataset[idx]` — returns frame dict
  - `dataset[idx, delta_timestamps={"observation.image": [-1.0, -0.5, 0.0]}]` — multi-frame temporal query
- `LeRobotDatasetMetadata` L82 — manages metadata and parquet writing
- `MultiLeRobotDataset` L1512 — concatenates multiple datasets

**Factory** — `src/lerobot/datasets/factory.py`
- `make_dataset(cfg: TrainPipelineConfig)` L71
- `resolve_delta_timestamps(cfg, ds_meta)` L38

**Utilities** — `src/lerobot/datasets/utils.py`
- `validate_frame(frame, features)` L973
- `build_dataset_frame(ds_features, observation, prefix)` L655
- `dataset_to_policy_features(features)` L684
- `hf_transform_to_torch(items_dict)` L397
- `flatten_dict(d, parent_key, sep)` L140 / `unflatten_dict(d, sep)` L166
- `load_json(fpath)` L242, `write_json(data, fpath)` L255
- Key path constants: `INFO_PATH="meta/info.json"`, `STATS_PATH="meta/stats.json"`

**Image transforms** — `src/lerobot/datasets/transforms.py`
- `ImageTransforms(Transform)` L231
- `ImageTransformsConfig` L166 — `enable: bool = False`
- `ImageTransformConfig` L148, `make_transform_from_config(cfg)` L218
- `RandomSubsetApply(Transform)` L29, `SharpnessJitter(Transform)` L98

**Other dataset tools**
- `OnlineBuffer` — `online_buffer.py` — ring buffer for live data collection
- `EpisodeAwareSampler` — `sampler.py`
- `AsyncImageWriter` — `image_writer.py`
- `StreamingLeRobotDataset` — `streaming_dataset.py`
- `compute_stats` — `compute_stats.py`

---

## configs/

**Types** — `src/lerobot/configs/types.py`
- `FeatureType(str, Enum)` L20 — STATE, VISUAL, ENV, ACTION, REWARD, LANGUAGE
- `NormalizationMode(str, Enum)` L35 — MIN_MAX, MEAN_STD, IDENTITY, QUANTILES, QUANTILE10
- `PolicyFeature(type: FeatureType, shape: tuple[int, ...])` L44

**Policy config base** — `src/lerobot/configs/policies.py`
- `PreTrainedConfig(draccus.ChoiceRegistry, HubMixin, ABC)` L40
  - `n_obs_steps: int = 1`
  - `input_features: dict[str, PolicyFeature]`
  - `output_features: dict[str, PolicyFeature]`
  - `device: str`, `use_amp: bool = False`
  - Abstract: `observation_delta_indices`, `action_delta_indices`, `get_optimizer_preset()`, `validate_features()`

**Training config** — `src/lerobot/configs/train.py`
- `TrainPipelineConfig(HubMixin)` L37 — dataset + policy + training params

**Dataset/WandB/Eval configs** — `src/lerobot/configs/default.py`
- `DatasetConfig` L17 — `repo_id, root, episodes, image_transforms, revision, video_backend`
- `WandBConfig` L35 — `enable, project, entity, notes, run_id, mode`
- `EvalConfig` L50 — `n_episodes=50, batch_size=50, use_async_envs=False`

**Parser** — `src/lerobot/configs/parser.py`
- `wrap(config_path)` L195 — decorator for config-driven scripts

---

## scripts/ (CLI Entry Points)

| Command | Script | Purpose |
|---|---|---|
| `lerobot-train` | `lerobot_train.py` | Train policy from dataset |
| `lerobot-eval` | `lerobot_eval.py` | Evaluate policy on environment |
| `lerobot-record` | `lerobot_record.py` | Record robot demos to dataset |
| `lerobot-replay` | `lerobot_replay.py` | Replay recorded episodes |
| `lerobot-teleoperate` | `lerobot_teleoperate.py` | Live teleoperation |
| `lerobot-calibrate` | `lerobot_calibrate.py` | Calibrate robot motors |
| `lerobot-find-cameras` | `lerobot_find_cameras.py` | Discover cameras |
| `lerobot-find-port` | `lerobot_find_port.py` | Discover serial ports |
| `lerobot-find-joint-limits` | `lerobot_find_joint_limits.py` | Find motor limits |
| `lerobot-setup-motors` | `lerobot_setup_motors.py` | Configure motor parameters |
| `lerobot-dataset-viz` | `lerobot_dataset_viz.py` | Visualize dataset (Rerun) |
| `lerobot-edit-dataset` | `lerobot_edit_dataset.py` | Modify dataset |
| `lerobot-info` | `lerobot_info.py` | Display dataset/model info |

---

## utils/

**`utils.py`**
- `auto_select_torch_device() -> torch.device` L40 — picks cuda/rocm/mps/cpu
- `get_safe_torch_device(device_str) -> torch.device` L57
- `get_safe_dtype(dtype, device) -> torch.dtype` L80 — handles MPS/XPU limitations
- `is_amp_available(device) -> bool` L121
- `init_logging()` L130 — logging with optional file output
- `inside_slurm() -> bool` L34

**`robot_utils.py`**
- `busy_wait(seconds: float)` L19 — platform-aware sleep (busy-wait on Mac/Win, sleep on Linux)

**`control_utils.py`**
- `predict_action(observation, policy, device, use_amp)` L67 — full preprocessing → inference → postprocessing
- `init_keyboard_listener(events)` L118 — pynput listener for keyboard control
- `is_headless() -> bool` L40 — detect headless environment

**`random_utils.py`**
- `set_seed(seed, accelerator=None)` L167
- `seeded_context(seed)` L182 — context manager
- `save_rng_state(path)` L130, `load_rng_state(path)` L136
- `get_rng_state() -> dict` L142, `set_rng_state(state)` L154

**`train_utils.py`**
- `save_checkpoint(step, policy, optimizer, scheduler, ...)` L65
- `load_training_state(checkpoint_dir, ...)` L136
- `save_training_state(step, optimizer, scheduler, ...)` L109
- `get_step_checkpoint_dir(output_dir, step)` L42

**`logging_utils.py`**
- `AverageMeter` L22 — tracks avg/current metric: `.update(val)`, `.reset()`
- `MetricsTracker` L50 — tracks loss, steps, episodes, epochs

**`hub.py`**
- `HubMixin` L26 — `save_pretrained()`, `from_pretrained()`, `push_to_hub()`

**`errors.py`**
- `DeviceNotConnectedError` L16, `DeviceAlreadyConnectedError` L24

**`constants.py`** — key constants:
- `OBS_STR = "observation"`, `OBS_IMAGE = "observation.image"`, `OBS_IMAGES = "observation.images"`
- `ACTION = "action"`, `REWARD = "reward"`, `TRUNCATED`, `DONE`
- `HF_LEROBOT_HOME` — base cache directory
- `HF_LEROBOT_CALIBRATION` — calibration JSON directory
- `CHECKPOINTS_DIR`, `PRETRAINED_MODEL_DIR`, `TRAINING_STATE_DIR`
- `ROBOTS` — list of registered robot type names
- `TELEOPERATORS` — list of registered teleoperator type names

**`rotation.py`**
- `Rotation` L22 — quaternion/rotvec/matrix conversions
  - `from_rotvec(rotvec)` L38, `from_matrix(mat)` L66, `from_quat(quat)` L110
  - `as_matrix()` L123, `as_rotvec()` L142, `as_quat()` L167
  - `apply(vectors, inverse=False)` L176, `inv()` L224
  - `__mul__` L240 — compose rotations

**`visualization_utils.py`**
- `init_rerun()` L25, `log_rerun_data(observation, action)` L40

**`io_utils.py`**
- `write_video(path, frames)` L27
- `deserialize_json_into_object(path, cls)` L36

**`import_utils.py`**
- `is_package_available(pkg_name) -> bool` L24
- `register_third_party_devices()` L133 — discovers `lerobot_*` plugins

**`transition.py`**
- `Transition` (TypedDict) L24 — state, action, reward, next_state, done, truncated, complementary_info
- `move_transition_to_device(transition, device)` L34

---

## processor/

**`pipeline.py`**
- `DataProcessorPipeline` — chains `ProcessorStep`s with Hub save/load
- `ProcessorStepRegistry` L59 — `.register()` decorator

**`factory.py`**
- `make_default_teleop_action_processor()` L27
- `make_default_robot_action_processor()` L38
- `make_default_robot_observation_processor()` L49
- `make_default_processors()` L58

**`core.py`**
- `TransitionKey(Enum)` L26 — OBSERVATION, ACTION, REWARD, DONE, TRUNCATED, INFO, COMPLEMENTARY_DATA
- `PolicyAction` = torch.Tensor, `RobotAction` = dict, `EnvAction` = np.ndarray
- `EnvTransition` (TypedDict) L45

---

## async_inference/

**`policy_server.py`**
- `PolicyServer` L66 — gRPC servicer for real-time inference

**`robot_client.py`**
- `RobotClient` L82 — gRPC client connecting robot to policy server

**`configs.py`**
- `PolicyServerConfig` L46 — `host, port, fps, inference_latency, obs_queue_timeout`
- `RobotClientConfig` L102 — `policy type, robot config, actions_per_chunk, server_address`
- `SUPPORTED_POLICIES` — ["act", "smolvla", "diffusion", "tdmpc", "vqbet", "pi0", "pi05"]
- `SUPPORTED_ROBOTS` — ["so100_follower", "so101_follower", "bi_so100_follower"]

**`constants.py`**
- `DEFAULT_FPS = 30`, `DEFAULT_INFERENCE_LATENCY = 1/30`, `DEFAULT_OBS_QUEUE_TIMEOUT = 2`

---

## envs/

**`factory.py`**
- `make_env(cfg, n_envs=1, use_async_envs=False)` L36 — returns `dict[str, dict[int, VectorEnv]]`
- `make_env_config(env_type, **kwargs)` L25

**`configs.py`**
- `EnvConfig(draccus.ChoiceRegistry, ABC)` L28 — `task, fps=30, features, max_parallel_tasks`
- Registered subclasses: `AlohaEnv` ("aloha"), `PushtEnv` ("pusht"), `LiberoEnv` ("libero"), `MetaWorldEnv`

**`utils.py`**
- `preprocess_observation(observations)` L36 — numpy → torch
- `env_to_policy_features(env_cfg)` L90
- `close_envs(obj)` L173

---

## optim/

**`optimizers.py`**
- `OptimizerConfig` (ABC) L34 — `.build(params) -> Optimizer`
- `AdamConfig` L62 — `lr, betas, eps, weight_decay, grad_clip_norm`
- `AdamWConfig` L76, `SGDConfig` L91

**`schedulers.py`**
- `LRSchedulerConfig` (ABC) L32
- `DiffuserSchedulerConfig` L46, `VQBeTSchedulerConfig` L58, `CosineDecayWithWarmupSchedulerConfig` L82

**`factory.py`**
- `make_optimizer_and_scheduler(policy, cfg)` L25

---

## rl/

**`buffer.py`** — `ReplayBuffer` L80, `BatchTransition` L31
**`wandb_utils.py`** — `WandBLogger` L59, `cfg_to_group(cfg)` L29
**`eval_policy.py`** — `eval_policy(policy, env, n_episodes)` L38
**`process.py`** — `ProcessSignalHandler` L24 — graceful SIGINT/SIGTERM handling

---

## transport/ (gRPC)

**`utils.py`**
- `CHUNK_SIZE = 2MB`, `MAX_MESSAGE_SIZE = 4MB`
- `send_bytes_in_chunks(data)` L42, `receive_bytes_in_chunks(stream)` L70

---

## palm_track.py (Prototype)

`/home/aup/lerobot/palm_track.py` — standalone hand tracking → arm control
- `FOLLOWER_PORT = "/dev/ttyACM2"`, `CAMERA_INDEX = "/dev/video2"` (or current value)
- `SMOOTHING = 0.6`, `PAN_MIN/MAX = -60/60`, `TILT_MIN/MAX = -30/45`
- `clamp(val, lo, hi)` L15, `map_range(val, in_lo, in_hi, out_lo, out_hi)` L18
- Controls: shoulder_pan.pos, shoulder_lift.pos

---

## Key Calibration Path

```
~/.cache/huggingface/lerobot/calibration/
├── robots/so101_follower/my_awesome_follower_arm.json
└── teleoperators/so101_leader/my_awesome_leader_arm.json
```
Delete only when physically recalibrating. Stale cache causes arm drift.
