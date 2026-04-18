# BOB-OT Desk Companion — Troubleshooting Guide
**Hardware:** WowRobo SO-101 + AMD Ryzen AI 9 HX370 (Ubuntu 24.04)

---

## Quick session start checklist

Run this every time before doing anything:

```bash
# 1. Check what's connected
ls /dev/ttyACM* /dev/ttyUSB* /dev/video*

# 2. Set permissions on everything
sudo chmod 666 /dev/ttyACM0 /dev/ttyACM1 /dev/ttyACM2 2>/dev/null; true

# 3. Verify GPU
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# 4. Activate environment
conda activate lerobot && cd ~/lerobot
```

---

## Arm ports changed

Ports shift every time you unplug/replug. Always find them fresh.

```bash
# Option 1 — lerobot built-in
lerobot-find-port

# Option 2 — list all serial devices
ls /dev/ttyACM* /dev/ttyUSB*

# Option 3 — most reliable, shows exact device names
dmesg | tail -20 | grep tty
# look for: "cdc_acm 1-2: ttyACM0: USB ACM device"
# or:       "cp210x converter now attached to ttyUSB0"
```

**Tip:** Plug follower first, then leader. First plugged usually gets the lower number but don't rely on this — always verify.

Once you know the ports, set permissions:

```bash
sudo chmod 666 /dev/ttyACM1 /dev/ttyACM2   # replace with your actual ports
```

Update `palm_track.py` if the follower port changed:

```bash
sed -i 's|FOLLOWER_PORT = ".*"|FOLLOWER_PORT = "/dev/ttyACMX"|' ~/lerobot/palm_track.py
# replace X with actual port number
```

Verify the arm responds before running any script:

```bash
python3 -c "
from lerobot.robots.so101_follower.so101_follower import SO101Follower
from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig
cfg = SO101FollowerConfig(port='/dev/ttyACM2', id='my_awesome_follower_arm')
r = SO101Follower(cfg)
r.connect()
print('connected OK:', r.get_observation().keys())
r.disconnect()
"
```

Expected output:
```
connected OK: dict_keys(['shoulder_pan.pos', 'shoulder_lift.pos', 'elbow_flex.pos', 'wrist_flex.pos', 'wrist_roll.pos', 'gripper.pos'])
```

---

## Camera ports changed

```bash
# List all video devices
ls /dev/video*

# Find which index maps to which physical camera
lerobot-find-cameras opencv

# Preview each device to confirm it's the right one
ffplay /dev/video0    # press Q to close
ffplay /dev/video2
ffplay /dev/video4
```

Update `palm_track.py` if camera index changed:

```bash
sed -i 's|CAMERA_INDEX  = .*|CAMERA_INDEX  = 4|' ~/lerobot/palm_track.py
# replace 4 with your actual index
```

Update the teleoperation command with new ports:

```bash
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=/dev/ttyACMX \
  --robot.id=my_awesome_follower_arm \
  --robot.cameras="{ front: {type: opencv, index_or_path: /dev/videoX, width: 1920, height: 1080, fps: 30}}" \
  --teleop.type=so101_leader \
  --teleop.port=/dev/ttyACMX \
  --teleop.id=my_awesome_leader_arm \
  --display_data=true
```

Replace both `ttyACMX` and `videoX` with your actual port numbers.

---

## ROCm / GPU not detected

Symptom: `torch.cuda.is_available()` returns `False`

```bash
# Step 1 — check if HSA env var is set
echo $HSA_OVERRIDE_GFX_VERSION
# expected: 11.0.0

# Step 2 — if empty, add it and reload
echo "export HSA_OVERRIDE_GFX_VERSION=11.0.0" >> ~/.bashrc
source ~/.bashrc

# Step 3 — verify again
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# expected: True  AMD Radeon Graphics

# Step 4 — if still False, check ROCm is installed
rocminfo | grep "Agent 2" -A5
```

---

## PyTorch version got overwritten

Symptom: `torch.__version__` shows `2.x.x+cpu` instead of `2.7.1+rocm6.3`

This happens when `pip install lerobot` or any other package silently pulls in a CPU-only torch wheel.

```bash
# Check current version
python3 -c "import torch; print(torch.__version__)"

# Reinstall the correct ROCm wheel
pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 \
    --index-url https://download.pytorch.org/whl/rocm6.3 --force-reinstall

# Verify
python3 -c "import torch; print(torch.__version__, torch.cuda.is_available())"
# expected: 2.7.1+rocm6.3  True
```

---

## lerobot module not found

Symptom: `ModuleNotFoundError: No module named 'lerobot'`

```bash
# Make sure you are in the right directory and env
conda activate lerobot
cd ~/lerobot

# Reinstall in editable mode
pip install -e .
pip install 'lerobot[feetech]'

# Verify
python3 -c "import lerobot; print(lerobot.__version__)"
```

Always run scripts from inside `~/lerobot/`:

```bash
cd ~/lerobot
python3 palm_track.py    # correct
python3 ~/palm_track.py  # may fail if run from ~
```

---

## Arm connects but motors not found

Symptom:
```
RuntimeError: FeetechMotorsBus motor check failed
Missing motor IDs: 1, 2, 3, 4, 5, 6
```

Causes and fixes:

```bash
# 1. Wrong port — find the correct one
lerobot-find-port

# 2. Permissions not set
sudo chmod 666 /dev/ttyACM2

# 3. Arm not powered — check power supply
#    Follower = 12V 8A  |  Leader = 5V 6A  — DO NOT SWAP

# 4. USB cable issue — try a different cable or port
# plug into a different USB port on the laptop (not through a hub)
```

---

## Mediapipe has no attribute 'solutions'

Symptom: `AttributeError: module 'mediapipe' has no attribute 'solutions'`

```bash
pip uninstall mediapipe -y
pip install mediapipe==0.10.9
```

---

## numpy version conflict

Symptom after installing mediapipe:
```
ERROR: numpy 1.26.4 incompatible with opencv-python-headless which requires numpy>=2
```

Fix — restore numpy 2.x and reinstall mediapipe without deps:

```bash
pip install "numpy>=2.0" --force-reinstall
pip install mediapipe==0.10.9 --no-deps
python3 -c "import numpy; import mediapipe; print(numpy.__version__)"
# expected: 2.x.x
```

---

## Camera window doesn't open / black screen

```bash
# Check if camera is recognized at all
ls /dev/video*

# Test with ffplay first
ffplay /dev/video2

# If that works but OpenCV shows black, try a different backend
# In palm_track.py change:
# cap = cv2.VideoCapture(CAMERA_INDEX)
# to:
# cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
```

---

## Wayland warning on camera open

Symptom:
```
Warning: Ignoring XDG_SESSION_TYPE=wayland on Gnome. Use QT_QPA_PLATFORM=wayland
```

This is just a warning — camera still works. But for lerobot data collection with arrow keys you **must** be on Xorg not Wayland:

- Log out
- At login screen click the gear icon bottom right
- Select **Ubuntu on Xorg**
- Log back in

---

## Arduino not responding / eyes not working

```bash
# Find arduino port
ls /dev/ttyUSB* /dev/ttyACM*
dmesg | tail -10 | grep tty

# Set permissions
sudo chmod 666 /dev/ttyUSB0

# Test serial connection
python3 -c "
import serial, time
s = serial.Serial('/dev/ttyUSB0', 115200)
time.sleep(2.0)   # CRITICAL — arduino resets on connect, wait 2s
s.write(b'I')
print('sent OK')
s.close()
"
```

If no response — check the Arduino sketch baud rate matches (`115200` by default in our sketch).

---

## Git — pushed to wrong branch

```bash
# Check which branch you're on
git branch

# Switch to your track branch
git checkout track/arm    # or voice / vision / eyes

# If you accidentally committed to main
git checkout main
git log --oneline -5      # find the bad commit hash
git revert <hash>
git push origin main
```

---

## Git — merge conflict at hour 7

```bash
git checkout main
git pull origin main
git merge track/voice

# If conflict in main.py or config.py:
# Open VS Code and use the diff editor to pick changes
code .

# After resolving all conflicts:
git add .
git commit -m "merge: resolve conflicts in main.py"
git push origin main
```

---

## Known port assignments (confirmed working)

| Device | Port | Notes |
|---|---|---|
| Follower arm | `/dev/ttyACM2` | may change on replug |
| Leader arm | `/dev/ttyACM1` | may change on replug |
| Front camera | `/dev/video4` | 1920×1080 @ 30fps |
| Side camera | index `2` | 640×480, palm/face tracking |
| Arduino OLED | `/dev/ttyUSB0` | TBD |

