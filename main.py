import asyncio
import pyaudio
import pvporcupine
import subprocess
from modules.ai_tools import ask_gemini, GeminiAnswer
from modules.youtube import YouTubeSession
from modules.weather import say_weather
from modules.speech import setup_dynamic_audio, get_respeaker_index, rec, speech_to_text, listen_for_keyword, play_voice, text_to_speech
from modules.large_variables import NAMED_PROMPTS
from dotenv import load_dotenv
import time
import os
import re

load_dotenv()
SOUNDS_PATH: str = "assets/sounds/"
NOT_UNDERSTAND_VOICE_LOCATION: str = SOUNDS_PATH + "not_understand.wav"
COMMUNICATION_ERROR_VOICE_LOCATION: str = SOUNDS_PATH + "communication_error.wav"
THINKING_VOICE_LOCATION: str = SOUNDS_PATH + "thinking.wav"
YT_SEARCH_VOICE_LOCATION: str = SOUNDS_PATH + "youtube_search.wav"
SETUP_VOICE_LOCATION: str = SOUNDS_PATH + "setup.wav"
FAILED_SETUP_VOICE_LOCATION: str = SOUNDS_PATH + "failed_setup.wav"
REBOOT_VOICE_LOCATION: str = SOUNDS_PATH + "reboot.wav"
POWEROFF_VOICE_LOCATION: str = SOUNDS_PATH + "poweroff.wav"
HELP_VOICE_LOCATION: str = SOUNDS_PATH + "help.wav"
LISTENING_START_VOICE_LOCATION: str = SOUNDS_PATH + "listening_start.wav"
LOST_NETWORK_VOICE_LOCATION: str = SOUNDS_PATH + "lost_network.wav"
RETRY_LIMIT: int = 2  # Ile razy prosić o powtórzenie, gdy nie zrozumiano polecenia
WIFI_CONFIG_PATH: str = "/media/dawid/RPI config/config.txt"


async def handle_gemini_answer(yt: YouTubeSession, tool: str, content: str):
    if tool == "PLAY":
        play_voice(YT_SEARCH_VOICE_LOCATION)
        await yt.find_and_a_play_song(content)
    elif tool == "ANSWER":
        play_voice(THINKING_VOICE_LOCATION)
        await text_to_speech(content)
    elif tool == "RESUME":
        await yt.resume_song()
    elif tool == "WEATHER":
        play_voice(THINKING_VOICE_LOCATION)
        await say_weather(content)
    elif tool == "HELP":
        play_voice(HELP_VOICE_LOCATION)
    elif tool == "REBOOT":
        play_voice(REBOOT_VOICE_LOCATION)
        await asyncio.sleep(2)
        await asyncio.create_subprocess_shell('sudo reboot')
    elif tool == "POWEROFF":
        play_voice(POWEROFF_VOICE_LOCATION)
        await asyncio.sleep(2)
        await asyncio.create_subprocess_shell('sudo poweroff')


async def interactive_console(pa: pyaudio.PyAudio, respeaker_index: int, yt: YouTubeSession):
    try:
        porcupine = pvporcupine.create(
            access_key=os.environ.get("PORCUPINE_KEY"),
            keyword_paths=['assets/Hey-Raspberry_en_raspberry-pi_v4_0_0.ppn'],
        )
    except Exception as e:
        print(f"Problem z porcupine: {e}")
        return

    print("Stworzono instancję audio.")

    try:
        while True:
            if listen_for_keyword(pa, respeaker_index, porcupine):

                if not check_network_connection():
                    play_voice(LOST_NETWORK_VOICE_LOCATION)
                    break

                await yt.stop_song()
                play_voice(LISTENING_START_VOICE_LOCATION)
                await handle_interaction(pa, respeaker_index, porcupine.frame_length, yt)

    finally:
        porcupine.delete()
        pa.terminate()
        print("Zamknięto instancję audio.")


async def handle_interaction(pa, respeaker_index: int, frame_length: int, yt: YouTubeSession):
    """Obsługuje logikę nasłuchiwania i wysyłania komend do Gemini po wybudzeniu."""
    retry_count = 0

    while True:
        rec(pa, respeaker_index, frame_length)
        user_input = speech_to_text()
        print(f"Rozpoznany tekst: {user_input}")
        success = False
        if isinstance(user_input, str):
            gemini_answer = ask_gemini(user_input)

            if isinstance(gemini_answer, GeminiAnswer):
                if gemini_answer.tool == "ERROR":
                    break
                if gemini_answer.tool in NAMED_PROMPTS.keys():
                    await handle_gemini_answer(yt, gemini_answer.tool, gemini_answer.content)
                    success = True
                else:
                    print(f"Narzędzie '{gemini_answer.tool}' nie znajduje się na liście dozwolonych narzędzi!")

        if success:
            break

        if retry_count < RETRY_LIMIT:
            play_voice(NOT_UNDERSTAND_VOICE_LOCATION)
            retry_count += 1
        else:
            play_voice(COMMUNICATION_ERROR_VOICE_LOCATION)
            break


def check_network_connection() -> bool:
    """Zwraca True, jeżeli połączenie sieciowe jest aktywne."""
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "STATE", "general"],
            capture_output=True,
            text=True
        )
        print(result.stdout.strip())
        return result.stdout.strip().lower() == "connected"
    except FileNotFoundError:
        return False


def connect_with_wifi() -> bool:
    """Zwraca True, jeżeli udało się połączyć z Wi-Fi."""

    if not os.path.exists(WIFI_CONFIG_PATH):
        print("Błąd: Brak pliku konfiguracyjnego Wi-Fi.")
        return False

    with open(WIFI_CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    ssid_match = re.search(r"(?i)^\s*SSID\s*=\s*(.+?)\s*$", content, re.MULTILINE)
    password_match = re.search(r"(?i)^\s*PASSWORD\s*=\s*(.+?)\s*$", content, re.MULTILINE)

    if not ssid_match or not password_match:
        print("Błąd: Nie znaleziono poprawnych danych (SSID/PASSWORD) w pliku.")
        return False

    ssid = ssid_match.group(1)
    password = password_match.group(1)

    try:
        print(f"Brak sieci. Próbuję połączyć z Wi-Fi: {ssid}...")
        result = subprocess.run(
            ["nmcli", "device", "wifi", "connect", ssid, "password", password],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            time.sleep(2)
            print("Połączono pomyślnie!")
            return True
        else:
            print(f"Błąd łączenia: {result.stderr.strip()}")
            return False

    except FileNotFoundError:
        print("Błąd: Narzędzie nmcli nie jest zainstalowane w tym systemie.")
        return False
    
    except subprocess.TimeoutExpired:
        print("Błąd: Przekroczono limit czasu żądania.")
        return False
    
    except Exception as e:
        print(f"Nieznany błąd:\n{e}")
        return False




async def main():
    if check_network_connection() or connect_with_wifi():
        pa = pyaudio.PyAudio()
        yt = YouTubeSession()
        await yt.open_the_search_page()
        respeaker_index: int = get_respeaker_index(pa)
        setup_dynamic_audio(respeaker_index)
        play_voice(SETUP_VOICE_LOCATION)
        await interactive_console(pa, respeaker_index, yt)
    else:
        play_voice(FAILED_SETUP_VOICE_LOCATION)

if __name__ == "__main__":
    asyncio.run(main())
