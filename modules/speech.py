import pyaudio
import os
import json
import anyio
import pyaudio
import speech_recognition as sr
from typing import Optional
from datetime import date
import wave
import numpy as np
from scipy.signal import resample_poly
from google.cloud import texttospeech
from dotenv import load_dotenv

load_dotenv()

RESPEAKER_RATE = 44100
RESPEAKER_CHANNELS = 2 
RESPEAKER_WIDTH = 2
CHUNK = 1024
RECORD_SECONDS = 5
DAILY_CHAR_LIMIT = 30000
WAVE_OUTPUT_FILENAME = "outputs/output.wav"
TTS_FILE_LOCATION = "outputs/tts.wav"
SOUNDS_PATH: str = "assets/sounds/"
STATE_FILE = "assets/tts_usage_state.json"
EXCEEDED_TTS_RATE_LIMIT_VOICE_LOCATION: str = SOUNDS_PATH + "exceeded_tts_rate_limit.wav"

# Zmienne do sterowania zakańczania nagrywania głosu ciszą
SILENCE_DURATION_SEC = 2.0  # ile sekund ciszy kończy nagrywanie
SILENCE_THRESHOLD_RATIO = 0.20  # ...% najwyższej głośności to próg ciszy
MIN_RECORD_SECONDS = 2.0  # nagrywaj zawsze przez co najmniej ... sekundy
MAX_RECORD_SECONDS = 10.0  # nie nagrywaj dluzej niz ... sekund
ABSOLUTE_MIN_VOLUME = 300  # minimalny próg głośności - ignoruje szum


def exceeded_tts_rate_limit(text_to_tell: str) -> bool:
    """
    Sprawdza, czy dodanie nowego tekstu przekroczy dzienny limit znaków TTS.
    Zapisuje stan do pliku, aby pamiętać zużycie pomiędzy restartami programu.
    """
    current_date = str(date.today())
    text_length = len(text_to_tell)

    # Wczytywanie obecnego stan z pliku (jeśli istnieje)
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            try:
                state = json.loads(f.read())
            except json.JSONDecodeError:
                state = {"date": current_date, "used_chars": 0}
    else:
        state = {"date": current_date, "used_chars": 0}

    # Resetowanie limitu, jeśli zmienił się dzień
    if state.get("date") != current_date:
        state["date"] = current_date
        state["used_chars"] = 0

    # Sprawdzanie, czy nowy tekst przekracza limit
    if state["used_chars"] + text_length > DAILY_CHAR_LIMIT:
        print(
            f"Błąd: Przekroczono limit TTS. Użyto {state['used_chars']}/{DAILY_CHAR_LIMIT}. "
            f"Próba dodania {text_length} znaków zakończyła się niepowodzeniem."
        )
        return True

    # Jeśli limit nie został przekroczony następuje zaktualizowanie zużycia i zapis do pliku
    state["used_chars"] += text_length
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(state))

    print(f"Zużycie TTS: {state['used_chars']}/{DAILY_CHAR_LIMIT} znaków dzisiaj.")
    return False


async def text_to_speech(text_to_tell: str, tts_loc: str = TTS_FILE_LOCATION):
    if exceeded_tts_rate_limit(text_to_tell):
        play_voice(EXCEEDED_TTS_RATE_LIMIT_VOICE_LOCATION)
        return
    if text_to_tell == "":
        return

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
    async with await anyio.open_file(tts_loc, "wb") as out:
        await out.write(response.audio_content)

    print(f"Zapisano dźwięk do {tts_loc}")
    play_voice(tts_loc)


def speech_to_text() -> Optional[str | None]:
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


def get_supported_sample_rate(pa, respeaker_index: int) -> int:
    """Sprawdza i zwraca optymalną częstotliwość próbkowania dla mikrofonu."""
    test_sample_rates = [8000, 16000, 22050, 32000, 44100, 48000, 96000]
    valid_sample_rates = []

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

    return 16000 if 16000 in valid_sample_rates else valid_sample_rates[0]


def read_and_process_audio(stream, chosen_rate: int, frame_length: int) -> np.ndarray:
    """Odczytuje dane ze strumienia i w razie potrzeby wykonuje resampling do 16000 Hz."""
    if chosen_rate != 16000:
        input_samples = int(frame_length * chosen_rate / 16000)
        data = stream.read(input_samples, exception_on_overflow=False)
        audio_data = np.frombuffer(data, dtype=np.int16)

        audio_data = resample_poly(audio_data, 16000, chosen_rate)

        if len(audio_data) > frame_length:
            audio_data = audio_data[:frame_length]
        elif len(audio_data) < frame_length:
            audio_data = np.pad(audio_data, (0, frame_length - len(audio_data)))
    else:
        data = stream.read(frame_length, exception_on_overflow=False)
        audio_data = np.frombuffer(data, dtype=np.int16)

    return audio_data.astype(np.int16)


def listen_for_keyword(pa, respeaker_index: int, oww_model) -> bool:
    chunk_size: int = 1280
    chosen_rate = get_supported_sample_rate(pa, respeaker_index)

    print(f"Rozpoczynanie transmisji z parametrami:\nczęstotliwość próbkowania = {chosen_rate},\nkanały = 1,\nurządzenie = {respeaker_index}")

    try:
        stream = pa.open(
            rate=chosen_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            input_device_index=respeaker_index,
            frames_per_buffer=chunk_size
        )
    except Exception as e:
        print(str(e))
        raise e

    print("Nasłuchiwanie słowa wybudzającego...")
    oww_model.reset()
    try:
        while True:
            pcm = read_and_process_audio(stream, chosen_rate, chunk_size)

            pcm = (pcm - np.mean(pcm)).astype(np.int16)

            prediction = oww_model.predict(pcm)
            for model_name, score in prediction.items():
                if score > 0.7:
                    print(f"Wykryto słowo kluczowe! (pewność: {score:.2f})")
                    return True
    finally:
        if stream is not None:
            stream.stop_stream()
            stream.close()


def rec(p: pyaudio.PyAudio, respeaker_index: int):
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
    print(
        f"Urządzenie {respeaker_index} - {info['name']}, maksymalne kanały wejścia: {info['maxInputChannels']}, maksymalne kanały wyjścia {info['maxOutputChannels']}")
    print(f"Urządzenie wspiera następujące częstotliwości próbkowania: {valid_sample_rates}")

    if not valid_sample_rates:
        raise RuntimeError("Nie znaleziono żadnych częstotliwości próbkowania dla tego urządzenia.")

    if 16000 in valid_sample_rates:
        chosen_rate = 16000
    else:
        chosen_rate = valid_sample_rates[0]

    print(
        f"Otwieranie strumienia z częstotliwością próbkowania: {chosen_rate}, kanały: {RESPEAKER_CHANNELS}, urządzenie: {respeaker_index}")

    stream = p.open(
        rate=chosen_rate,
        format=p.get_format_from_width(RESPEAKER_WIDTH),
        channels=RESPEAKER_CHANNELS,
        input=True,
        input_device_index=respeaker_index,
        frames_per_buffer=1280
    )

    print("Nagrywanie...")

    frames = []

    # Zmienne do śledzenia głośności i czasu
    max_volume_seen = ABSOLUTE_MIN_VOLUME
    silent_chunks_count = 0

    chunks_per_second = chosen_rate / 1280
    max_silent_chunks = int(SILENCE_DURATION_SEC * chunks_per_second)
    min_total_chunks = int(MIN_RECORD_SECONDS * chunks_per_second)
    max_total_chunks = int(MAX_RECORD_SECONDS * chunks_per_second)

    try:
        for i in range(max_total_chunks):
            data = stream.read(1280, exception_on_overflow=False)
            frames.append(data)

            chunk_data = np.frombuffer(data, dtype=np.int16).astype(np.float32)

            current_volume = np.sqrt(np.mean(np.square(chunk_data)))

            if current_volume > max_volume_seen:
                max_volume_seen = current_volume

            dynamic_threshold = max(ABSOLUTE_MIN_VOLUME, max_volume_seen * SILENCE_THRESHOLD_RATIO)

            if current_volume < dynamic_threshold:
                silent_chunks_count += 1
            else:
                silent_chunks_count = 0

            if silent_chunks_count > max_silent_chunks and i > min_total_chunks:
                print(f"Wykryto ciszę przez {SILENCE_DURATION_SEC}s. Przerywam nagrywanie.")
                break

    finally:
        print("Koniec nagrywania.")
        stream.stop_stream()
        stream.close()

    raw_data = b''.join(frames)
    audio_data = np.frombuffer(raw_data, dtype=np.int16)

    audio_data = audio_data.reshape(-1, RESPEAKER_CHANNELS)

    mono_audio = audio_data[:, 0]

    if chosen_rate != 16000:
        print(f"Zmiana częstotliwości z {chosen_rate} na 16000 Hz...")
        mono_audio = resample_poly(mono_audio, 16000, chosen_rate)
        mono_audio = np.asarray(mono_audio, dtype=np.int16)

    wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(p.get_sample_size(p.get_format_from_width(RESPEAKER_WIDTH)))
    wf.setframerate(16000)
    wf.writeframes(mono_audio.tobytes())
    wf.close()

def play_voice(file_location: str = WAVE_OUTPUT_FILENAME):
    os.system(f"aplay -D plughw:2,0 {file_location} > /dev/null 2>&1")


def get_respeaker_index(pa):
    """
    Szuka indeksu urządzenia ReSpeaker bezpośrednio w instancji PyAudio.
    """
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        name = info.get('name', '')
        if 'seeed2micvoicec' in name or 'seeed-2mic-voicecard' in name:
            print(f"Znaleziono ReSpeaker w PyAudio: Indeks {i} (Nazwa: {name})")
            return i
            
    print("Nie znaleziono ReSpeakera po nazwie, szukanie domyślnego urządzenia...")
    try:
        default_device = pa.get_default_input_device_info()
        return default_device['index']
    except:
        raise RuntimeError("Nie znaleziono żadnego urządzenia nagrywającego.")
    
def setup_dynamic_audio(index: int):
    """ Automatycznie konfiguruje domyślny głośnik w systemie. """
    try:
        # Tworzenie treści pliku konfiguracyjnego ALSA
        asoundrc_content = f"""pcm.!default {{
    type plug
    slave.pcm "hw:{index},0"
}}

ctl.!default {{
    type hw
    card {index}
}}
"""
        # Nadpisanie starych ustawień
        asoundrc_path = os.path.expanduser("~/.asoundrc")
        with open(asoundrc_path, "w+") as f:
            f.write(asoundrc_content)
            
        # Wymuszenie zmiennej środowiskowej dla wewnętrznych bibliotek
        os.environ["AUDIODEV"] = f"hw:{index},0"
        print("Zaaktualizowano ustawienia ALSA.")
        
    except Exception as e:
        print(f"Błąd podczas dynamicznej konfiguracji audio: {e}")
