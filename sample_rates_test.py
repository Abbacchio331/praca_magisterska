import pyaudio

p = pyaudio.PyAudio()
device_index = 1

for rate in [8000, 16000, 22050, 32000, 44100, 48000, 96000]:
    try:
        stream = p.open(format=pyaudio.paInt16,
                        channels=1,
                        rate=rate,
                        input=True,
                        input_device_index=device_index)
        stream.close()
        print(f"Sample rate {rate} supported")
    except Exception as e:
        print(f"Sample rate {rate} NOT supported: {e}")

p.terminate()
