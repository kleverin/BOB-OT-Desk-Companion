import os

os.environ.setdefault("HSA_OVERRIDE_GFX_VERSION", "11.0.0")

# Serial ports
LEADER_PORT   = "/dev/ttyACM1"   # SO-101 Leader  — 5V 6A
FOLLOWER_PORT = "/dev/ttyACM2"   # SO-101 Follower — 12V 8A
ARDUINO_PORT  = "/dev/ttyUSB0"   # Arduino OLED

# Cameras
CAMERA_TOP  = 1  # overhead, 1920×1080 @ 30fps — GeminiVision + ACT
CAMERA_SIDE = 0  # forward-facing — MediaPipe face/hand tracking

# API keys (set these in ~/.bashrc before running)
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")

# LeRobot IDs (must match calibration cache filenames)
FOLLOWER_ID = "my_awesome_follower_arm"
LEADER_ID   = "my_awesome_leader_arm"
