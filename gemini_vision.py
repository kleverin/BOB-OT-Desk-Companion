import google.generativeai as genai
from PIL import Image
import cv2, ollama
from collections import deque

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


class GeminiVision:
    def __init__(self, api_key: str, top_camera_index=4):
        self.top_camera_index = top_camera_index
        self.gemini_available = False
        self.conversation_history = deque(maxlen=6)  # last 3 exchanges

        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel("gemini-2.0-flash")
            self.model.generate_content("Hello")   # pre-warm on startup
            self.gemini_available = True
            print("[GeminiVision] Gemini 2.0 Flash ready ✓")
        except Exception as e:
            print(f"[GeminiVision] Gemini unavailable ({e}), will use LLaVA.")

    def capture_snapshot(self) -> Image.Image:
        cap = cv2.VideoCapture(self.top_camera_index, cv2.CAP_V4L2)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise RuntimeError("Could not capture from top camera")
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    def _stream_gemini(self, prompt: str, image: Image.Image):
        messages = list(self.conversation_history) + [prompt, image]
        response = self.model.generate_content(messages, stream=True)
        buffer = ""
        full_response = ""
        for chunk in response:
            buffer += chunk.text
            full_response += chunk.text
            while any(p in buffer for p in [".", "!", "?"]):
                for punct in [".", "!", "?"]:
                    idx = buffer.find(punct)
                    if idx != -1:
                        sentence = buffer[:idx+1].strip()
                        buffer = buffer[idx+1:].strip()
                        if sentence:
                            yield sentence
                        break
        if buffer.strip():
            yield buffer.strip()
        self.conversation_history.append({"role": "user", "parts": [prompt]})
        self.conversation_history.append({"role": "model", "parts": [full_response]})

    def _ask_llava_fallback(self, prompt: str) -> str:
        image_path = "/tmp/desk_snapshot.jpg"
        cap = cv2.VideoCapture(self.top_camera_index, cv2.CAP_V4L2)
        ret, frame = cap.read()
        cap.release()
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
            yield "I can see some objects on the desk, but I'm having trouble right now."

    def tutor(self, question: str = ""):
        prompt = TUTOR_PROMPT
        if question:
            prompt += f"\n\nThe child is asking: {question}"
        try:
            if self.gemini_available:
                yield from self._stream_gemini(prompt, self.capture_snapshot())
            else:
                result = self._ask_llava_fallback(prompt)
                for sentence in result.split(". "):
                    if sentence.strip():
                        yield sentence.strip() + "."
        except Exception as e:
            print(f"[GeminiVision] tutor failed: {e}")
            yield "Hmm, let me think about that. Can you show me again?"

    def clear_history(self):
        self.conversation_history.clear()
