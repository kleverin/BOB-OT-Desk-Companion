"""
pose_preset.py — Save and replay arm poses via the Leader arm.

Usage:
  python pose_preset.py record <name>   # Hold Leader in position, press Enter to save
  python pose_preset.py goto <name>     # Move Follower smoothly to saved pose
  python pose_preset.py list            # Print all saved poses
  python pose_preset.py delete <name>   # Remove a saved pose
"""

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("HSA_OVERRIDE_GFX_VERSION", "11.0.0")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PRESETS_FILE = Path(__file__).parent / "pose_presets.json"

LEADER_PORT   = "/dev/ttyACM0"
LEADER_ID     = "my_awesome_leader_arm"
FOLLOWER_PORT = "/dev/ttyACM1"
FOLLOWER_ID   = "my_awesome_follower_arm"

FOLLOWER_CALIB = os.path.expanduser(
    "~/.cache/huggingface/lerobot/calibration/robots/so101_follower/my_awesome_follower_arm.json"
)

JOINTS = [
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
    "gripper.pos",
]

GOTO_STEPS   = 50    # interpolation steps
GOTO_STEP_DT = 0.02  # seconds per step → ~1 s total


def get_neutral() -> dict:
    with open(FOLLOWER_CALIB) as f:
        calib = json.load(f)
    return {f"{joint}.pos": 0.0 for joint in calib}


def load_presets() -> dict:
    if PRESETS_FILE.exists():
        return json.loads(PRESETS_FILE.read_text())
    return {}


def save_presets(presets: dict) -> None:
    PRESETS_FILE.write_text(json.dumps(presets, indent=2))


def cmd_record(name: str) -> None:
    from lerobot.teleoperators.so101_leader.config_so101_leader import SO101LeaderConfig
    from lerobot.teleoperators.so101_leader.so101_leader import SO101Leader

    print(f"Connecting to Leader arm on {LEADER_PORT} …")
    cfg    = SO101LeaderConfig(port=LEADER_PORT, id=LEADER_ID)
    leader = SO101Leader(cfg)
    leader.connect()  # loads cached calib by ID, no re-calibration

    print("Move the Leader arm to the desired position, then press Enter.")
    input()

    action = leader.get_action()
    pose   = {j: float(action[j]) for j in JOINTS if j in action}

    leader.disconnect()

    presets = load_presets()
    presets[name] = pose
    save_presets(presets)

    print(f"Saved pose '{name}':")
    for j, v in pose.items():
        print(f"  {j}: {v:.2f}")


def cmd_goto(name: str) -> None:
    from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig
    from lerobot.robots.so101_follower.so101_follower import SO101Follower

    presets = load_presets()
    if name not in presets:
        print(f"Error: no preset named '{name}'. Run 'list' to see saved poses.")
        sys.exit(1)

    target = presets[name]

    print(f"Connecting to Follower arm on {FOLLOWER_PORT} …")
    cfg   = SO101FollowerConfig(port=FOLLOWER_PORT, id=FOLLOWER_ID)
    robot = SO101Follower(cfg)
    robot.connect()  # loads cached calib by ID, no re-calibration

    obs   = robot.get_observation()
    start = {j: float(obs.get(j, 0.0)) for j in JOINTS}

    print(f"Moving to '{name}' …")
    for step in range(1, GOTO_STEPS + 1):
        t   = step / GOTO_STEPS
        cmd = {j: start[j] + (target.get(j, start[j]) - start[j]) * t for j in JOINTS}
        robot.send_action(cmd)
        time.sleep(GOTO_STEP_DT)

    robot.disconnect()
    print("Done.")


def cmd_list() -> None:
    presets = load_presets()
    if not presets:
        print("No presets saved yet.")
        return
    for name, pose in presets.items():
        vals = "  ".join(f"{j.split('.')[0]}={v:.1f}" for j, v in pose.items())
        print(f"  {name}: {vals}")


def cmd_delete(name: str) -> None:
    presets = load_presets()
    if name not in presets:
        print(f"No preset named '{name}'.")
        sys.exit(1)
    del presets[name]
    save_presets(presets)
    print(f"Deleted '{name}'.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "record":
        if len(sys.argv) < 3:
            print("Usage: pose_preset.py record <name>")
            sys.exit(1)
        cmd_record(sys.argv[2])
    elif cmd == "goto":
        if len(sys.argv) < 3:
            print("Usage: pose_preset.py goto <name>")
            sys.exit(1)
        cmd_goto(sys.argv[2])
    elif cmd == "list":
        cmd_list()
    elif cmd == "delete":
        if len(sys.argv) < 3:
            print("Usage: pose_preset.py delete <name>")
            sys.exit(1)
        cmd_delete(sys.argv[2])
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)
