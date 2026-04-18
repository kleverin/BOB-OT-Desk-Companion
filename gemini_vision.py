import io
import cv2
import ollama
from PIL import Image
from collections import deque
from google import genai
from google.genai import types

IDENTIFY_PROMPT = """You are a friendly robot assistant. Look at this desk and describe
what objects you can see in one short, natural sentence. Be specific about colors and types.
Example: "I can see a red water bottle, two pencils, and an open notebook."
Keep it under 20 words. Do not say anything else."""

TUTOR_PROMPT = """You are a friendly robot tutor named Sparky helping kids aged 6-14.
When shown a math problem, homework question, drawing, or any object:
- Explain it step by step in simple, encouraging language.
- Use short sentences. Never use jargon without explaining it first.
- Never just give the answer — guide the child to figure it out themselves.
- Keep your total response under 5 sentences so the child stays engaged.
- Always end with an encouraging phrase like "You've got this!" or "Great question!"
- If it is a math problem, walk through each step out loud like a teacher would."""

MODEL = "gemini-2.5-flash"


class GeminiVision:
    def __init__(self, api_key: str, cam=None, top_camera_index: int = 4):
        self._cam = cam
        self.top_camera_index = top_camera_index
        self.gemini_available = False
        self.conversation_history = deque(maxlen=6)  # last 3 exchanges

        try:
            self._client = genai.Client(api_key=api_key)
            # Lightweight connectivity check — won't burn quota if it fails
            self._client.models.get(model=MODEL)                                       
            self.gemini_available = True
            print(f"[GeminiVision] {MODEL} ready ✓")
        except Exception as e:
            print(f"[GeminiVision] Gemini unavailable ({e}), will use LLaVA.")

    def capture_snapshot(self) -> Image.Image:
        if self._cam is not None:
            return self._cam.snapshot()
        cap = cv2.VideoCapture(self.top_camera_index, cv2.CAP_V4L2)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise RuntimeError("Could not capture from top camera")
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    def _image_to_part(self, image: Image.Image) -> types.Part:
        buf = io.BytesIO()
        image.save(buf, format="JPEG")
        return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")

    def _build_contents(self, prompt: str, image: Image.Image | None) -> list:
        parts = [types.Part.from_text(text=prompt)]
        if image is not None:
            parts.append(self._image_to_part(image))
        new_turn = types.Content(role="user", parts=parts)
        return list(self.conversation_history) + [new_turn]

    def _stream_gemini(self, prompt: str, image: Image.Image | None):
        contents = self._build_contents(prompt, image)
        buffer = ""
        full_response = ""
        for chunk in self._client.models.generate_content_stream(
            model=MODEL, contents=contents
        ):
            text = chunk.text or ""
            buffer += text
            full_response += text
            while any(p in buffer for p in [".", "!", "?"]):
                for punct in [".", "!", "?"]:
                    idx = buffer.find(punct)
                    if idx != -1:
                        sentence = buffer[:idx + 1].strip()
                        buffer = buffer[idx + 1:].strip()
                        if sentence:
                            yield sentence
                        break
        if buffer.strip():
            yield buffer.strip()
        self.conversation_history.append(
            types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
        )
        self.conversation_history.append(
            types.Content(role="model", parts=[types.Part.from_text(text=full_response)])
        )

    def _ask_llava_fallback(self, prompt: str) -> str:
        image_path = "/tmp/desk_snapshot.jpg"
        if self._cam is not None:
            img = self._cam.snapshot()
            img.save(image_path)
        else:
            cap = cv2.VideoCapture(self.top_camera_index)
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return "I'm having trouble seeing the desk right now."
            cv2.imwrite(image_path, frame)
        response = ollama.chat(
            model="llava",
            messages=[{"role": "user", "content": prompt, "images": [image_path]}]
        )
        return response["message"]["content"]

    def identify(self):
        self.conversation_history.clear()
        try:
            if self.gemini_available:
                yield from self._stream_gemini(IDENTIFY_PROMPT, self.capture_snapshot())
            else:
                yield self._ask_llava_fallback(IDENTIFY_PROMPT)
        except Exception as e:
            print(f"[GeminiVision] identify failed: {e}")
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print("[GeminiVision] Quota exceeded — switching to LLaVA for this session")
                self.gemini_available = False
                yield self._ask_llava_fallback(IDENTIFY_PROMPT)
            else:
                yield "I can see some objects on the desk, but I'm having trouble right now."

    def tutor(self, question: str = ""):
        prompt = TUTOR_PROMPT
        if question:
            prompt += f"\n\nThe child is asking: {question}"
        is_followup = len(self.conversation_history) > 0
        image = None if is_followup else self.capture_snapshot()
        if image is not None:
            image.save("/tmp/sparky_sees.jpg")
            print("[GeminiVision] Snapshot saved to /tmp/sparky_sees.jpg")
        try:
            if self.gemini_available:
                yield from self._stream_gemini(prompt, image)
            else:
                result = self._ask_llava_fallback(prompt)
                for sentence in result.split(". "):
                    if sentence.strip():
                        yield sentence.strip() + "."
        except Exception as e:
            print(f"[GeminiVision] tutor failed: {e}")
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print("[GeminiVision] Quota exceeded — switching to LLaVA for this session")
                self.gemini_available = False
                result = self._ask_llava_fallback(prompt)
                for sentence in result.split(". "):
                    if sentence.strip():
                        yield sentence.strip() + "."
            else:
                yield "Hmm, let me think about that. Can you show me again?"

    def clear_history(self):
        self.conversation_history.clear()
