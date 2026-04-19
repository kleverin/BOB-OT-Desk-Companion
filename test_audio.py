import sounddevice as sd
import numpy as np

tone = (np.sin(2*np.pi*440*np.arange(96000)/48000)*0.8).astype(np.float32)
stereo = np.stack([tone, tone], axis=1)

for dev in [5, 7]:
    print(f"Playing on device {dev}... (2 seconds)")
    sd.play(stereo, samplerate=48000, device=dev)
    sd.wait()
    print("Done")
