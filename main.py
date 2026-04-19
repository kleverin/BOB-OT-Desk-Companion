import cv2
from PIL import Image
from config import GEMINI_API_KEY, CAMERA_TOP
from sparky import SparkyVoice
from gemini_vision import GeminiVision
from voice import VoiceModule


class SharedCamera:
    """Opens the camera on demand per snapshot — avoids background thread segfaults."""

    def __init__(self, index: int):
        self.index = index

    def snapshot(self) -> Image.Image:
        cap = cv2.VideoCapture(self.index, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open camera {self.index}")
        for _ in range(5):  # flush stale frames
            cap.read()
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise RuntimeError("Camera capture failed")
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    def release(self):
        pass


class ModeSwitcher:
    """Central state machine. Track B stub: IDENTIFY + TUTOR functional; TRACK/CLEAN stubbed."""

    def __init__(self):
        self.current_mode = "IDLE"
        self._cam = SharedCamera(CAMERA_TOP)
        self.sparky = SparkyVoice()
        self.gemini = GeminiVision(api_key=GEMINI_API_KEY, cam=self._cam)
        self.voice = VoiceModule()
    def run(self):
        self.sparky.startup()
        print("[Sparky] Running. Hold SPACE to speak. Ctrl+C to quit.")
        while True:
            try:
                intent = self.voice.listen_once()
                self._handle(intent)
            except KeyboardInterrupt:
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
