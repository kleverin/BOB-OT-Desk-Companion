import numpy as np
import sounddevice as sd
from kokoro_onnx import Kokoro

k = Kokoro("kokoro.onnx", "voices/voices-v1.0.bin")
print("Generating speech...")
samples, sr = k.create("Hello! I am Sparky, your desk companion.", voice="af_sky", speed=0.95, lang="en-us")
audio = np.array(samples, dtype=np.float32).squeeze()
print(f"sr={sr}, shape={audio.shape}, max={np.max(np.abs(audio)):.3f}")

# resample to 48000
from scipy.signal import resample_poly
from math import gcd
g = gcd(48000, sr)
audio = resample_poly(audio, 48000 // g, sr // g).astype(np.float32)

stereo = np.stack([audio, audio], axis=1)
print("Playing on device 5...")
sd.play(stereo, samplerate=48000, device=5)
sd.wait()
print("Done")
