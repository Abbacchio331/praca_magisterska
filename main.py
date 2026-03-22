import asyncio
import pyaudio
import pvporcupine
from modules.large_variables import CORE_PROMPT, NAMED_PROMPTS
from modules.youtube import YouTubeSession
from modules.weather import say_weather
from modules.speech import get_respeaker_index, rec, speech_to_text, listen_for_keyword, play_voice, text_to_speech
from google import genai
from google.genai.types import GenerateContentConfig, ThinkingConfig
from dotenv import load_dotenv
from pydantic import BaseModel
import os

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
REBOOT_VOICE_LOCATION: str = SOUNDS_PATH + "reboot.wav"
RETRY_LIMIT: int = 2  # Ile razy prosić o powtórzenie, gdy nie zrozumiano polecenia
gemini_tools: list = ["PLAY", "ANSWER", "RESUME", "PAUSE", "WEATHER"]


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
                retry_count = 0
                while True:
                    await rec(pa, respeaker_index, porcupine.frame_length)
                    user_input = await speech_to_text()
                    if not isinstance(user_input, str):
                        if retry_count < RETRY_LIMIT:
                            await play_voice(NOT_UNDERSTAND_VOICE_LOCATION)
                            continue
                        else:
                            await play_voice(COMMUNICATION_ERROR_VOICE_LOCATION)
                            break
                    gemini_answer = ask_gemini(user_input)
                    if gemini_answer.tool in gemini_tools:
                        await handle_gemini_answer(yt, gemini_answer.tool, gemini_answer.content)
                        break
    finally:
        porcupine.delete()
        pa.terminate()
        print("Zamknięto instancję audio.")

async def main():
    yt = YouTubeSession()
    await yt.open_the_search_page()
    respeaker_index: int = await get_respeaker_index()
    await play_voice(SETUP_VOICE_LOCATION)
    await interactive_console(respeaker_index, yt)

if __name__ == "__main__":
    asyncio.run(main())
