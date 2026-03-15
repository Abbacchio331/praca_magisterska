import pyaudio
import asyncio
import subprocess
import speech_recognition as sr
from typing import Optional
import wave
import numpy as np
from scipy.signal import resample_poly
import math
import pvporcupine
from regex import findall
from google.cloud import texttospeech
import simpleaudio as sa
from dotenv import load_dotenv

load_dotenv()

RESPEAKER_RATE = 44100
RESPEAKER_CHANNELS = 2 
RESPEAKER_WIDTH = 2
# run getDeviceInfo.py to get index
CHUNK = 1024
RECORD_SECONDS = 5
WAVE_OUTPUT_FILENAME = "outputs/output.wav"
TTS_FILE_LOCATION = "outputs/tts.wav"


async def text_to_speech(text_to_tell: str, tts_loc: str = TTS_FILE_LOCATION):
    # Inicjalizacja klienta
    client = texttospeech.TextToSpeechClient()

    # Konfiguracja żądania
    synthesis_input = texttospeech.SynthesisInput(
        text=text_to_tell
    )

    voice = texttospeech.VoiceSelectionParams(
        language_code="pl-PL",
        name="pl-PL-Chirp3-HD-Laomedeia"
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16  # lub MP3, OGG_OPUS
    )

    # Wywołanie API
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )

    # Zapisz do pliku
    with open(tts_loc, "wb") as out:
        out.write(response.audio_content)

    print(f"Zapisano dźwięk do {tts_loc}")
    await play_voice(tts_loc)


async def speech_to_text() -> Optional[str | None]:
    recognizer = sr.Recognizer()
    with sr.AudioFile(WAVE_OUTPUT_FILENAME) as source:
        audio = recognizer.record(source)
    # Send to Google for recognition
    try:
        text = recognizer.recognize_google(audio, language="pl-PL") # type: ignore
        return text
    except sr.UnknownValueError:
        print("Google Speech could not understand the audio")
        return None
    except sr.RequestError as e:
        print(f"Could not request results from Google: {e}")
        return None


async def listen_for_keyword(pa, respeaker_index, porcupine) -> bool:
    stream = None

    valid_sample_rates = []
    test_sample_rates = [8000, 16000, 22050, 32000, 44100, 48000, 96000]

    for rate in test_sample_rates:
        try:
            if pa.is_format_supported(
                rate,
                input_device=respeaker_index,
                input_channels=1,
                input_format=pyaudio.paInt16
            ):
                valid_sample_rates.append(rate)
        except ValueError:
            pass

    info = pa.get_device_info_by_index(respeaker_index)
    print(f"Device {respeaker_index} info: {info['name']}, max input channels: {info['maxInputChannels']}, max output channels: {info['maxOutputChannels']}")
    print(f"Device supports sample rates: {valid_sample_rates}")

    if not valid_sample_rates:
        raise RuntimeError("No valid sample rates found for device")

    # Prefer 16000 Hz, if not available - wybierz pierwszy obs?ugiwany rate
    if 16000 in valid_sample_rates:
        chosen_rate = 16000
    else:
        chosen_rate = valid_sample_rates[0]

    print(f"[DEBUG] Opening stream with rate={chosen_rate}, channels=1, device={respeaker_index}")

    try:
        stream = pa.open(
            rate=chosen_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            input_device_index=respeaker_index,
            frames_per_buffer=porcupine.frame_length
        )
    except Exception as e:
        print(str(e))
        raise e
    else:
        print("Started a stream.")

    print("Nasluchiwanie slowa kluczowego...")

    try:
        while True:
            if chosen_rate != 16000:
                # calculate how many input samples to read
                input_samples = int(porcupine.frame_length * chosen_rate / 16000)

                # read input_samples from stream
                data = stream.read(input_samples, exception_on_overflow=False)
                audio_data = np.frombuffer(data, dtype=np.int16)

                # resample to 16000 Hz
                audio_data = resample_poly(audio_data, 16000, chosen_rate)

                # now make sure it is exactly porcupine.frame_length
                if len(audio_data) > porcupine.frame_length:
                    audio_data = audio_data[:porcupine.frame_length]
                elif len(audio_data) < porcupine.frame_length:
                    # pad with zeros if needed (rare)
                    audio_data = np.pad(audio_data, (0, porcupine.frame_length - len(audio_data)))
            else:
                # no resampling needed
                data = stream.read(porcupine.frame_length, exception_on_overflow=False)
                audio_data = np.frombuffer(data, dtype=np.int16)

            pcm = tuple(audio_data.astype(np.int16))

            keyword_index = porcupine.process(pcm)
            if keyword_index >= 0:
                print("Keyword detected!")
                return True

    finally:
        if stream is not None:
            stream.stop_stream()
            stream.close()




async def rec(p: pyaudio.PyAudio, respeaker_index: int, chunk_size: int):
    actual_chunk_size = chunk_size if chunk_size is not None else pvporcupine.Porcupine.frame_length

    # Sprawdz dostepne sample rates
    valid_sample_rates = []
    test_sample_rates = [8000, 16000, 22050, 32000, 44100, 48000, 96000]

    for rate in test_sample_rates:
        try:
            if p.is_format_supported(
                rate,
                input_device=respeaker_index,
                input_channels=RESPEAKER_CHANNELS,
                input_format=pyaudio.paInt16
            ):
                valid_sample_rates.append(rate)
        except ValueError:
            pass

    info = p.get_device_info_by_index(respeaker_index)
    print(f"Device {respeaker_index} info: {info['name']}, max input channels: {info['maxInputChannels']}, max output channels: {info['maxOutputChannels']}")
    print(f"Device supports sample rates: {valid_sample_rates}")

    if not valid_sample_rates:
        raise RuntimeError("No valid sample rates found for device")

    # Preferowany sample rate
    if 16000 in valid_sample_rates:
        chosen_rate = 16000
    else:
        chosen_rate = valid_sample_rates[0]

    print(f"[DEBUG] Opening stream for keyword with rate={chosen_rate}, channels={RESPEAKER_CHANNELS}, device={respeaker_index}")

    stream = p.open(
        rate=chosen_rate,
        format=p.get_format_from_width(RESPEAKER_WIDTH),
        channels=RESPEAKER_CHANNELS,
        input=True,
        input_device_index=respeaker_index,
        frames_per_buffer=actual_chunk_size
    )

    print("* recording")

    frames = []

    try:
        for _ in range(0, int(chosen_rate / CHUNK * RECORD_SECONDS)):
            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)
    finally:
        print("* done recording")
        stream.stop_stream()
        stream.close()

    # Połącz surowe dane
    raw_data = b''.join(frames)
    audio_data = np.frombuffer(raw_data, dtype=np.int16)

    # Jesli trzeba, przeskaluj do 16000 Hz
    if chosen_rate != 16000:
        print(f"[DEBUG] Resampling from {chosen_rate} to 16000 Hz")
        audio_data = resample_poly(audio_data, 16000, chosen_rate)
        audio_data = np.asarray(audio_data, dtype=np.int16)

    # Zapisz do pliku WAV
    wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
    wf.setnchannels(RESPEAKER_CHANNELS)
    wf.setsampwidth(p.get_sample_size(p.get_format_from_width(RESPEAKER_WIDTH)))
    wf.setframerate(16000)  # Docelowy rate po resamplingu
    wf.writeframes(audio_data.tobytes())
    wf.close()

async def play_voice(file_location: str = WAVE_OUTPUT_FILENAME):
    wave_obj = sa.WaveObject.from_wave_file(file_location)
    play_obj = wave_obj.play()
    play_obj.wait_done()


async def get_respeaker_index():
    try:
        arecord_output: str = str(subprocess.run(
            ["arecord", "-l"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        ))
        respeaker_index: int = int(findall(r'seeed2micvoicec\], device (\d+)', arecord_output)[0])
        print(f"Respeaker index: {respeaker_index}")
        return respeaker_index
    except Exception as e:
        raise Exception(f"Couldn't get the respreaker index. {e}")
