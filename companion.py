"""
companion.py — Voice-controlled robot main loop.

States:
  SLEEPING       Sparky is idle, waiting for "wake up"
  FACE_TRACKING  face_track_eyes.py subprocess runs, listening for commands
  DESK_VIEW      arm at home pose, Gemini analyzes what's shown on the table

Usage:
  python companion.py
"""

import os
import signal
import subprocess
import sys
import threading
import time
import cv2
import numpy as np
import serial
import serial.tools.list_ports

os.environ.setdefault("HSA_OVERRIDE_GFX_VERSION", "11.0.0")
os.environ.setdefault("DISPLAY", ":0")

from config import GEMINI_API_KEY
from voice import VoiceModule
from gemini_vision import GeminiVision
from sparky import SparkyVoice

FACE_TRACK_CMD  = ["python3", "/home/aup/lerobot/face_track_eyes.py"]
GOTO_HOLD_CMD   = ["python3", "/home/aup/BOB-OT-Desk-Companion/goto_pose.py", "home"]
GOTO_ONCE_CMD   = ["python3", "/home/aup/BOB-OT-Desk-Companion/goto_pose.py", "home", "--once"]
FOLLOWER_PORT   = "/dev/ttyACM1"
DESK_TIMEOUT    = 12.0

_PROC_ENV = {
    **os.environ,
    "DISPLAY": ":0",
    "QT_QPA_PLATFORM": "xcb",
    "HSA_OVERRIDE_GFX_VERSION": "11.0.0",
}


# ── Eyes controller ───────────────────────────────────────────────────────────

class EyesController:
    """Serial link to Arduino Nano OLED. Companion owns it when face_track is NOT running."""

    def __init__(self):
        self._ser     = None
        self._current = None
        self._port    = None

    def connect(self) -> bool:
        """Find and open the Arduino. Returns True on success."""
        for port in serial.tools.list_ports.comports():
            name = port.device
            if name == FOLLOWER_PORT:
                continue
            desc = (port.description or "").lower()
            mfr  = (port.manufacturer or "").lower()
            preferred = any(k in desc or k in mfr
                            for k in ("arduino", "ch340", "ch341", "ftdi", "nano"))
            is_candidate = preferred or name.startswith("/dev/ttyUSB")
            if not is_candidate:
                continue
            try:
                s = serial.Serial(name, 115200, timeout=1)
                time.sleep(2.0)
                s.reset_input_buffer()   # flush startup message ("BOB-OT eyes ready")
                s.write(b"NEUTRAL\n")
                ack = s.readline().decode("utf-8", errors="ignore").strip()
                if ack.startswith("ACK:"):
                    self._ser  = s
                    self._port = name
                    print(f"[eyes] Arduino on {name} ✓")
                    return True
                s.close()
            except Exception as e:
                print(f"[eyes] tried {name}: {e}")
        print("[eyes] Arduino not found — running without OLED")
        return False

    def disconnect(self) -> None:
        """Close serial so face_track_eyes.py can open it."""
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser     = None
            self._current = None

    def reconnect(self) -> None:
        """Reopen after face_track_eyes.py exits. Skip reset delay with dtr=False."""
        if self._port is None:
            return
        try:
            s = serial.Serial()
            s.port     = self._port
            s.baudrate = 115200
            s.timeout  = 1
            s.dtr      = False   # prevent Arduino reset on open
            s.open()
            time.sleep(0.3)
            s.reset_input_buffer()
            s.write(b"NEUTRAL\n")
            s.readline()         # consume ACK
            self._ser     = s
            self._current = None
            print(f"[eyes] reconnected on {self._port}")
        except Exception as e:
            print(f"[eyes] reconnect failed: {e}")

    def set(self, emotion: str) -> None:
        if self._ser is None or emotion == self._current:
            return
        try:
            self._ser.write(f"{emotion}\n".encode())
            self._ser.flush()
            self._current = emotion
        except Exception as e:
            print(f"[eyes] send error: {e}")


# ── Process helpers ───────────────────────────────────────────────────────────

def start_face_track() -> subprocess.Popen:
    return subprocess.Popen(FACE_TRACK_CMD, env=_PROC_ENV)


def stop_proc(proc: subprocess.Popen) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


stop_face_track = stop_proc


def start_home_hold() -> subprocess.Popen:
    return subprocess.Popen(GOTO_HOLD_CMD, env=_PROC_ENV)


def go_home() -> None:
    subprocess.run(GOTO_ONCE_CMD, env=_PROC_ENV)


# ── Voice helpers ─────────────────────────────────────────────────────────────

def listen_with_timeout(voice: VoiceModule, sparky: SparkyVoice, seconds: float):
    result    = [None]
    done      = threading.Event()
    speaking  = threading.Event()  # set when user presses spacebar

    def _worker():
        speaking.set()
        result[0] = voice.listen_once()
        done.set()

    threading.Thread(target=_worker, daemon=True).start()

    deadline = time.time() + seconds
    warned   = False
    while not done.is_set():
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        # only warn if user hasn't already pressed spacebar
        if remaining <= 2.0 and not warned and not speaking.is_set():
            warned = True
            sparky.say("I'll go back to tracking.")
        time.sleep(0.1)

    return result[0] if done.is_set() else None


_STOP_WORDS = {"stop", "rest", "sleep", "goodbye", "bye", "quit", "exit", "never mind", "nevermind"}


# ── Desk view mode ────────────────────────────────────────────────────────────

def desk_view_mode(voice: VoiceModule, gemini: GeminiVision,
                   sparky: SparkyVoice, eyes: EyesController, question: str) -> str:
    sparky.say("Let me take a look at that for you!")
    hold_proc = start_home_hold()
    time.sleep(1.5)

    eyes.set("SCANNING")

    # Capture once — show preview AND pass same frame to Gemini
    cap = cv2.VideoCapture(2, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    for _ in range(20):
        cap.read()
    ret, frame = cap.read()
    cap.release()

    pil_image = None
    if ret:
        cv2.imshow("Sparky's View", frame)
        cv2.waitKey(1)
        pil_image = __import__("PIL.Image", fromlist=["Image"]).fromarray(
            cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        )

    gemini.clear_history()
    sparky.start_thinking()
    sparky.say_streamed(gemini.tutor(question, image=pil_image))

    while True:
        intent = listen_with_timeout(voice, sparky, DESK_TIMEOUT)

        if intent is None:
            stop_proc(hold_proc)
            cv2.destroyWindow("Sparky's View")
            return "tracking"

        transcript = intent.get("transcript", "") or intent.get("target", "")

        if any(w in transcript.lower() for w in _STOP_WORDS) or intent.get("mode") == "idle":
            stop_proc(hold_proc)
            cv2.destroyWindow("Sparky's View")
            return "sleeping"

        sparky.start_thinking()
        sparky.say_streamed(gemini.reply(transcript))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("[Companion] Starting up …")
    sparky = SparkyVoice()
    sparky.startup()

    print("[Companion] Loading voice recognition …")
    sparky.say("Loading voice recognition, one moment!")
    voice  = VoiceModule()
    gemini = GeminiVision(api_key=GEMINI_API_KEY, top_camera_index=2)

    eyes = EyesController()
    eyes.connect()
    eyes.set("BORED")

    sparky.say("I'm ready. Say wake up to start!")

    state = "sleeping"
    proc  = None

    try:
        while True:
            # ── SLEEPING ──────────────────────────────────────────────────────
            if state == "sleeping":
                eyes.set("BORED")
                intent = voice.listen_once()
                mode   = intent.get("mode", "idle")

                if mode == "wake":
                    eyes.set("FOUND")
                    sparky.say("Welcome back guys.")
                    time.sleep(0.8)      # let FOUND show briefly
                    eyes.disconnect()    # hand serial to face_track_eyes.py
                    proc  = start_face_track()
                    state = "tracking"

            # ── FACE_TRACKING ─────────────────────────────────────────────────
            elif state == "tracking":
                intent = voice.listen_once()
                mode   = intent.get("mode", "idle")

                if mode == "wake":
                    sparky.say("Already on it!")

                elif mode == "knowledge":
                    q = intent.get("target", "").lower()
                    if any(k in q for k in ("your name", "who are you", "what's your name", "what is your name")):
                        sparky.say("I am Sparky, your AMD powered Physical AI enabled robot. I am here to answer all your questions.")
                    elif any(k in q for k in ("running on", "powered by", "what are you", "your hardware", "your cpu", "your chip")):
                        sparky.say("I am powered by AMD's high performance Ryzen AI Pro 9 HX CPU.")
                    else:
                        sparky.start_thinking()
                        sparky.say_streamed(gemini.ask_text(intent.get("target", "")))

                elif mode in ("tutor", "identify"):
                    stop_face_track(proc)
                    proc = None
                    time.sleep(0.5)      # let face_track release the serial port
                    eyes.reconnect()
                    next_state = desk_view_mode(
                        voice, gemini, sparky, eyes,
                        question=intent.get("target", "")
                    )
                    if next_state == "sleeping":
                        eyes.set("BORED")
                        sparky.say("Going to sleep. Moving to home position.")
                        go_home()
                        sparky.say("Goodnight!")
                        state = "sleeping"
                    else:
                        eyes.disconnect()
                        sparky.say("Back to tracking!")
                        proc  = start_face_track()
                        state = "tracking"

                elif mode == "idle":
                    stop_face_track(proc)
                    proc = None
                    time.sleep(0.5)
                    eyes.reconnect()
                    eyes.set("BORED")
                    sparky.say("Going to sleep. Moving to home position.")
                    go_home()
                    sparky.say("Goodnight! Say wake up when you need me.")
                    state = "sleeping"

    except KeyboardInterrupt:
        sparky.say("Shutting down.")

    finally:
        stop_face_track(proc)
        eyes.set("NEUTRAL")
        time.sleep(0.3)
        eyes.disconnect()
        print("[Companion] Exited.")


if __name__ == "__main__":
    main()
