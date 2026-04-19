"""
goto_pose.py — Move the follower arm smoothly to a saved preset pose.

Usage:
  python goto_pose.py <pose_name>
  python goto_pose.py home

  python goto_pose.py list          # show all saved poses
"""

import json
import os
import sys
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("HSA_OVERRIDE_GFX_VERSION", "11.0.0")

from lerobot.robots.so101_follower.so101_follower import SO101Follower
from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig

FOLLOWER_PORT = "/dev/ttyACM1"
FOLLOWER_ID   = "my_awesome_follower_arm"

CALIB_PATH = os.path.expanduser(
    "~/.cache/huggingface/lerobot/calibration/robots/so101_follower/my_awesome_follower_arm.json"
)
PRESETS_FILE = Path(__file__).parent / "pose_presets.json"

GOTO_STEPS   = 60    # steps for interpolation
GOTO_STEP_DT = 0.02  # ~1.2s total move time


def get_neutral() -> dict:
    with open(CALIB_PATH) as f:
        calib = json.load(f)
    return {f"{j}.pos": 0.0 for j in calib}


def load_presets() -> dict:
    if PRESETS_FILE.exists():
        return json.loads(PRESETS_FILE.read_text())
    return {}


if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)

cmd = sys.argv[1]

if cmd == "list":
    presets = load_presets()
    if not presets:
        print("No presets saved yet. Run teleop_save.py first.")
    else:
        for name, pose in presets.items():
            vals = "  ".join(f"{k.split('.')[0]}={v:.1f}" for k, v in pose.items())
            print(f"  {name}: {vals}")
    sys.exit(0)

pose_name = cmd
presets   = load_presets()

if pose_name not in presets:
    print(f"Error: no preset named '{pose_name}'.")
    print(f"Saved poses: {list(presets.keys()) or 'none'}")
    sys.exit(1)

target = presets[pose_name]

# ── Connect follower ───────────────────────────────────────────────────────────
print(f"[follower] connecting on {FOLLOWER_PORT} …")
robot = SO101Follower(SO101FollowerConfig(port=FOLLOWER_PORT, id=FOLLOWER_ID))
robot.connect()

obs   = robot.get_observation()
start = {j: float(obs.get(j, 0.0)) for j in target}

print(f"[goto] moving to '{pose_name}' …")
for step in range(1, GOTO_STEPS + 1):
    t   = step / GOTO_STEPS
    cmd = {j: start[j] + (target[j] - start[j]) * t for j in target}
    robot.send_action(cmd)
    time.sleep(GOTO_STEP_DT)

once = "--once" in sys.argv

if once:
    robot.disconnect()
    print("[done]")
else:
    print(f"[hold] holding '{pose_name}' — press Ctrl+C to release\n")
    try:
        while True:
            robot.send_action(target)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    robot.disconnect()
    print("\n[done]")
