import threading
import cv2
import numpy as np
from PIL import Image
from config import GEMINI_API_KEY, CAMERA_TOP
from sparky import SparkyVoice
from gemini_vision import GeminiVision
from voice import VoiceModule


class SharedCamera:
    """Opens the camera once; preview thread reads continuously; gemini grabs latest frame."""

    def __init__(self, index: int):
        self._cap = cv2.VideoCapture(index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open camera index {index}")
        self._lock = threading.Lock()
        self._latest = None

    def read_raw(self):
        with self._lock:
            ret, frame = self._cap.read()
            if ret:
                self._latest = frame
            return ret, frame

    def snapshot(self) -> Image.Image:
        with self._lock:
            if self._latest is None:
                raise RuntimeError("No frame captured yet")
            frame = self._latest.copy()
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    def release(self):
        self._cap.release()


def _camera_preview(cam: SharedCamera, stop_event: threading.Event):
    while not stop_event.is_set():
        ret, frame = cam.read_raw()
        if not ret:
            continue
        cv2.imshow("Sparky's View", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cv2.destroyAllWindows()


class ModeSwitcher:
    """Central state machine. Track B stub: IDENTIFY + TUTOR functional; TRACK/CLEAN stubbed."""

    def __init__(self):
        self.current_mode = "IDLE"
        self._cam = SharedCamera(CAMERA_TOP)
        self.sparky = SparkyVoice()
        self.gemini = GeminiVision(api_key=GEMINI_API_KEY, cam=self._cam)
        self.voice = VoiceModule()
        self._preview_stop = threading.Event()
        self._preview_thread = threading.Thread(
            target=_camera_preview, args=(self._cam, self._preview_stop), daemon=True
        )


    def run(self):
        self._preview_thread.start()
        self.sparky.startup()
        print("[Sparky] Running. Hold SPACE to speak. Ctrl+C to quit.")
        while True:
            try:
                intent = self.voice.listen_once()
                self._handle(intent)
            except KeyboardInterrupt:
                self._preview_stop.set()
                self._cam.release()
                try:
                    self.sparky.say("Goodbye!")
                except Exception:
                    pass
                break

    def _handle(self, intent: dict):
        print(f"[Sparky] Intent: {intent}")
        mode = intent.get("mode", "idle")
        target = intent.get("target", "")

        if mode == "identify":
            self.current_mode = "IDENTIFY"
            self.gemini.clear_history()
            self.sparky.say("Let me take a look!")
            self.sparky.start_thinking()
            self.sparky.say_streamed(self.gemini.identify())
            self.current_mode = "IDLE"

        elif mode == "tutor":
            self.current_mode = "TUTOR"
            self.sparky.say("Let me take a look at that for you!")
            self.sparky.start_thinking()
            self.sparky.say_streamed(self.gemini.tutor(target))
            self.current_mode = "IDLE"

        elif mode == "track":
            self.sparky.say("Face tracking isn't wired up yet!")

        elif mode == "clean":
            self.sparky.say("Cleaning mode isn't wired up yet!")

        elif mode == "idle":
            print("[Sparky] Idle.")


if __name__ == "__main__":
    ModeSwitcher().run()
