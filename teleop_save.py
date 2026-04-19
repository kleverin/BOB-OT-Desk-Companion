"""
teleop_save.py — Manually position the Leader arm, press Enter to save.

Usage:
  python teleop_save.py <pose_name>
  python teleop_save.py home
"""

import json
import os
import sys
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("HSA_OVERRIDE_GFX_VERSION", "11.0.0")

from lerobot.teleoperators.so101_leader.so101_leader import SO101Leader
from lerobot.teleoperators.so101_leader.config_so101_leader import SO101LeaderConfig

LEADER_PORT  = "/dev/ttyACM0"
LEADER_ID    = "my_awesome_leader_arm"
PRESETS_FILE = Path(__file__).parent / "pose_presets.json"

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)

pose_name = sys.argv[1]

print(f"[leader] connecting on {LEADER_PORT} …")
leader = SO101Leader(SO101LeaderConfig(port=LEADER_PORT, id=LEADER_ID))
leader.connect()

print("Move the Leader arm to the desired position.")
input("Press Enter to capture …")

action = leader.get_action()
pose   = {k: float(v) for k, v in action.items()}

leader.disconnect()

presets = {}
if PRESETS_FILE.exists():
    presets = json.loads(PRESETS_FILE.read_text())

presets[pose_name] = pose
PRESETS_FILE.write_text(json.dumps(presets, indent=2))

print(f"\nSaved '{pose_name}':")
for j, v in pose.items():
    print(f"  {j}: {v:.2f}")
