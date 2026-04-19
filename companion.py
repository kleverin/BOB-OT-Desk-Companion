"""
companion.py — Voice-controlled robot main loop.

States:
  SLEEPING       Sparky is idle, waiting for "wake up"
  FACE_TRACKING  face_track_pid.py subprocess runs, listening for commands
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

os.environ.setdefault("HSA_OVERRIDE_GFX_VERSION", "11.0.0")
os.environ.setdefault("DISPLAY", ":0")

from config import GEMINI_API_KEY
from voice import VoiceModule
from gemini_vision import GeminiVision
from sparky import SparkyVoice

FACE_TRACK_CMD  = ["python3", "/home/aup/lerobot/face_track_pid.py"]
GOTO_HOLD_CMD   = ["python3", "/home/aup/BOB-OT-Desk-Companion/goto_pose.py", "home"]
GOTO_ONCE_CMD   = ["python3", "/home/aup/BOB-OT-Desk-Companion/goto_pose.py", "home", "--once"]
DESK_TIMEOUT    = 5.0  # seconds of silence before returning to face tracking

_PROC_ENV = {
    **os.environ,
    "DISPLAY": ":0",
    "QT_QPA_PLATFORM": "xcb",
    "HSA_OVERRIDE_GFX_VERSION": "11.0.0",
}


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


stop_face_track = stop_proc  # alias kept for clarity


def start_home_hold() -> subprocess.Popen:
    """Move to home pose and keep holding torque — returns Popen to kill when done."""
    return subprocess.Popen(GOTO_HOLD_CMD, env=_PROC_ENV)


def go_home() -> None:
    """Move arm to home pose then release torque (arm can be moved freely)."""
    subprocess.run(GOTO_ONCE_CMD, env=_PROC_ENV)


def listen_with_timeout(voice: VoiceModule, sparky: SparkyVoice, seconds: float):
    """Run voice.listen_once() in a thread; return intent or None on timeout."""
    result = [None]
    done   = threading.Event()

    def _worker():
        result[0] = voice.listen_once()
        done.set()

    threading.Thread(target=_worker, daemon=True).start()

    deadline = time.time() + seconds
    warned   = False
    while not done.is_set():
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        if remaining <= 1.0 and not warned:
            warned = True
            sparky.say("I'll go back to tracking.")
        time.sleep(0.1)

    return result[0] if done.is_set() else None


_STOP_WORDS = {"stop", "rest", "sleep", "goodbye", "bye", "quit", "exit", "never mind", "nevermind"}


def desk_view_mode(voice: VoiceModule, gemini: GeminiVision, sparky: SparkyVoice, question: str) -> str:
    """
    Capture snapshot, analyze with Gemini, then hold an open conversation.
    Follow-up answers go directly to Gemini without re-classification or new snapshots.
    Returns next state: 'tracking' or 'sleeping'.
    """
    sparky.say("Let me take a look at that for you!")
    hold_proc = start_home_hold()
    time.sleep(1.5)  # wait for arm to reach home pose

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

    # Follow-up loop — any speech goes straight to Gemini as conversation
    while True:
        intent = listen_with_timeout(voice, sparky, DESK_TIMEOUT)

        if intent is None:
            stop_proc(hold_proc)
            cv2.destroyWindow("Sparky's View")
            return "tracking"

        transcript = intent.get("transcript", "") or intent.get("target", "")

        # Explicit stop commands exit the mode
        if any(w in transcript.lower() for w in _STOP_WORDS) or intent.get("mode") == "idle":
            stop_proc(hold_proc)
            cv2.destroyWindow("Sparky's View")
            return "sleeping"

        # Everything else is a conversational reply — no new snapshot
        sparky.start_thinking()
        sparky.say_streamed(gemini.reply(transcript))


def main():
    print("[Companion] Starting up …")
    sparky = SparkyVoice()
    sparky.startup()

    print("[Companion] Loading voice recognition …")
    sparky.say("Loading voice recognition, one moment!")
    voice  = VoiceModule()
    gemini = GeminiVision(api_key=GEMINI_API_KEY, top_camera_index=2)

    sparky.say("I'm ready. Say wake up to start!")

    state = "sleeping"
    proc  = None

    try:
        while True:
            # ── SLEEPING — wait for wake command ──────────────────────────────
            if state == "sleeping":
                intent = voice.listen_once()
                mode   = intent.get("mode", "idle")

                if mode == "wake":
                    sparky.say("Hey guys, how is it going?")
                    proc  = start_face_track()
                    state = "tracking"
                # any other command while sleeping → stay sleeping

            # ── FACE_TRACKING — listen for task commands ───────────────────────
            elif state == "tracking":
                intent = voice.listen_once()
                mode   = intent.get("mode", "idle")

                if mode == "wake":
                    sparky.say("Already on it!")

                elif mode in ("tutor", "identify"):
                    stop_face_track(proc)
                    proc  = None
                    next_state = desk_view_mode(
                        voice, gemini, sparky, question=intent.get("target", "")
                    )
                    if next_state == "sleeping":
                        sparky.say("Going to sleep. Moving to home position.")
                        go_home()
                        sparky.say("Goodnight!")
                        state = "sleeping"
                    else:
                        sparky.say("Back to tracking!")
                        proc  = start_face_track()
                        state = "tracking"

                elif mode == "idle":
                    stop_face_track(proc)
                    proc = None
                    sparky.say("Going to sleep. Moving to home position.")
                    go_home()
                    sparky.say("Goodnight! Say wake up when you need me.")
                    state = "sleeping"

    except KeyboardInterrupt:
        sparky.say("Shutting down.")

    finally:
        stop_face_track(proc)
        print("[Companion] Exited.")


if __name__ == "__main__":
    main()
