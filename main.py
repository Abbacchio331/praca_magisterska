import asyncio
import pyaudio
import pvporcupine
import subprocess
from modules.large_variables import CORE_PROMPT, NAMED_PROMPTS
from modules.youtube import YouTubeSession
from modules.weather import say_weather
from modules.speech import get_respeaker_index, rec, speech_to_text, listen_for_keyword, play_voice, text_to_speech
from google import genai
from google.genai.types import GenerateContentConfig, ThinkingConfig
from dotenv import load_dotenv
from pydantic import BaseModel
import time
import os
import re

# Read the environmental variables
load_dotenv()

# Shared asyncio queue to communicate between button and console
button_event_queue = asyncio.Queue()

# Start Gemini AI session
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

SOUNDS_PATH: str = "assets/sounds/"
NOT_UNDERSTAND_VOICE_LOCATION: str = SOUNDS_PATH + "not_understand.wav"
COMMUNICATION_ERROR_VOICE_LOCATION: str = SOUNDS_PATH + "communication_error.wav"
THINKING_VOICE_LOCATION: str = SOUNDS_PATH + "thinking.wav"
YT_SEARCH_VOICE_LOCATION: str = SOUNDS_PATH + "youtube_search.wav"
SETUP_VOICE_LOCATION: str = SOUNDS_PATH + "setup.wav"
FAILED_SETUP_VOICE_LOCATION: str = SOUNDS_PATH + "failed_setup.wav"
REBOOT_VOICE_LOCATION: str = SOUNDS_PATH + "reboot.wav"
POWEROFF_VOICE_LOCATION: str = SOUNDS_PATH + "poweroff.wav"
LISTENING_START_VOICE_LOCATION: str = SOUNDS_PATH + "listening_start.wav"
LOST_NETWORK_VOICE_LOCATION: str = SOUNDS_PATH + "lost_network.wav"
RETRY_LIMIT: int = 2  # Ile razy prosić o powtórzenie, gdy nie zrozumiano polecenia
gemini_tools: list = ["PLAY", "ANSWER", "RESUME", "PAUSE", "WEATHER", "REBOOT", "POWEROFF"]
WIFI_CONFIG_PATH: str = "/media/dawid/RPI config/config.txt"

class GeminiAnswer(BaseModel):
    tool: str
    content: str

def ask_gemini(question: str):
    """
    Asks the Gemini AI a question and receives a structured response.

    Args:
        question (str): The user's question.

    Returns:
        GeminiAnswer: An instance of the GeminiAnswer class with the structured response.
    """
    system_prompt: str = CORE_PROMPT
    for prompt_name, prompt_text in NAMED_PROMPTS.items():
        system_prompt += prompt_text
    full_prompt = (system_prompt +
                   "\nZawsze używaj odpowiedniego narzędzia w zależności od kontekstu.\nUżytkownik mówi: " + question)
    
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "tool": {"type": "STRING"},
            "content": {"type": "STRING"}
        },
        "required": ["tool", "content"]
    }

    response = client.models.generate_content(
        model = "gemini-2.5-flash-lite",
        contents = full_prompt,
        config = GenerateContentConfig(
            response_mime_type="application/json", # type: ignore
            response_schema=response_schema, # type: ignore
            thinking_config=ThinkingConfig(thinking_budget=0) # type: ignore
        ),
    )
    ai_answer = str(response.text)
    print(ai_answer)
    return GeminiAnswer.model_validate_json(ai_answer)


async def handle_gemini_answer(yt: YouTubeSession, tool: str, content: str):
    if tool == "PLAY":
        await play_voice(YT_SEARCH_VOICE_LOCATION)
        await yt.find_and_a_play_song(content)
    elif tool == "ANSWER":
        await yt.stop_song()
        await play_voice(THINKING_VOICE_LOCATION)
        await text_to_speech(content)
    elif tool == "RESUME":
        await yt.resume_song()
    elif tool == "PAUSE":
        await yt.stop_song()
    elif tool == "WEATHER":
        await yt.stop_song()
        await play_voice(THINKING_VOICE_LOCATION)
        await say_weather(content)
    elif tool == "REBOOT":
        await yt.stop_song()
        await play_voice(REBOOT_VOICE_LOCATION)
        await asyncio.sleep(2)
        await asyncio.create_subprocess_shell('sudo reboot')
    elif tool == "POWEROFF":
        await yt.stop_song()
        await play_voice(POWEROFF_VOICE_LOCATION)
        await asyncio.sleep(2)
        await asyncio.create_subprocess_shell('sudo poweroff')


async def interactive_console(respeaker_index: int, yt: YouTubeSession):    
    pa = pyaudio.PyAudio()
    porcupine = pvporcupine.create(
        access_key=os.environ.get("PORCUPINE_KEY"),
        keyword_paths=['assets/Mamma-Mia_it_raspberry-pi_v3_0_0.ppn'],
        model_path='assets/porcupine_params_it.pv'
    )
    print("Stworzono instancję audio.")
    try:
        while True:
            if await listen_for_keyword(pa, respeaker_index, porcupine):
                if not check_network_connection():
                    await play_voice(LOST_NETWORK_VOICE_LOCATION)
                    break
                await play_voice(LISTENING_START_VOICE_LOCATION)
                while True:
                    retry_count = 0
                    await rec(pa, respeaker_index, porcupine.frame_length)
                    user_input = await speech_to_text()
                    if not isinstance(user_input, str):
                        if retry_count < RETRY_LIMIT:
                            await play_voice(NOT_UNDERSTAND_VOICE_LOCATION)
                            retry_count += 1
                            continue
                        else:
                            await play_voice(COMMUNICATION_ERROR_VOICE_LOCATION)
                            break
                    gemini_answer = ask_gemini(user_input)
                    if gemini_answer.tool in gemini_tools:
                        await handle_gemini_answer(yt, gemini_answer.tool, gemini_answer.content)
                        break
                    else:
                        if retry_count < RETRY_LIMIT:
                            await play_voice(NOT_UNDERSTAND_VOICE_LOCATION)
                            retry_count += 1
                            continue
                        else:
                            await play_voice(COMMUNICATION_ERROR_VOICE_LOCATION)
                            break
    finally:
        porcupine.delete()
        pa.terminate()
        print("Zamknięto instancję audio.")


def check_network_connection() -> bool:
    """Returns True if there is an active network connection"""
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
    """Returns True if connected with Wi-Fi successfully (or already connected)"""

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
        yt = YouTubeSession()
        await yt.open_the_search_page()
        respeaker_index: int = await get_respeaker_index()
        await play_voice(SETUP_VOICE_LOCATION)
        await interactive_console(respeaker_index, yt)
    else:
        await play_voice(FAILED_SETUP_VOICE_LOCATION)

if __name__ == "__main__":
    asyncio.run(main())
