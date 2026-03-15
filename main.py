import asyncio
import pyaudio
import pvporcupine
from modules.youtube import YouTubeSession
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

NOT_UNDERSTAND_VOICE_LOCATION = "assets/sounds/not_understand.wav"
THINKING_VOICE_LOCATION = "assets/sounds/thinking.wav"
YT_SEARCH_VOICE_LOCATION = "assets/sounds/youtube_search.wav"
SETUP_VOICE_LOCATION = "assets/sounds/setup.wav"

gemini_tools = ["PLAY", "ANSWER", "RESUME", "PAUSE"]

class GeminiAnswer(BaseModel):
    tool: str
    content: str

async def ask_gemini(question: str, available_tools: list = gemini_tools):
    """
    Asks the Gemini AI a question and receives a structured response.

    Args:
        question (str): The user's question.
        available_tools (list): A list of available tools.

    Returns:
        GeminiAnswer: An instance of the GeminiAnswer class with the structured response.
    """
    system_prompt = """
    Jesteś inteligentnym asystentem stworzonym do przetwarzania próśb użytkownika i odpowiadania na nie w sposób ustrukturyzowany.
    Miej na uwadze, że twoja odpowiedź będzie przeczytana na głos przy użyciu TTS, więc nie używaj transkrypcji napisów w innych językach (grecki, koreański, rosyjski, ...) na alfabet łaciński.
    Ponadto liczby w twojej odpowiedzi powinny być zapisywane słownie. Mówiąc o sobie, używaj żeńskich zaimków. 
    Twoja odpowiedź musi zawsze odnościć się do poniższego schematu:
    {
        "tool": "string",
        "content": "string"
    }

    Oto narzędzia z których możesz korzystać:
    """
    if "PLAY" in available_tools:
        system_prompt += """
        1. **tool: 'PLAY'**
        * Użyj go kiedy użytkownik prosi o odtworzenie jakiejś piosenki.
        * 'content' zawsze powinien być tytułem piosenki o który prosi użytkownik.
        * Przykład: Użytkownik: "Odtwórz Bohemian Rhapsody" -> {"tool": "PLAY", "content": "Bohemian Rhapsody"}
        * Jeśli użytkownik nie sprecyzuje jakiej piosenki chce posłuchać wybierz dowolną.
        """
    if "ANSWER" in available_tools:
        system_prompt += """
        2. **tool: 'ANSWER'**
        * Użyj go, kiedy użytkownik zada ci pytanie, które wymaga bezpośredniej odpowiedzi.
        * 'content' zawsze powinien być odpowiedzią na zadane pytanie.
        * Jeśli używasz słów w języku obcym, podawaj TYLKO oryginalny zapis. Nie dodawaj wymowy ani transkrypcji w nawiasach.
        * Przykład: Użytkownik: "Jaka jest stolica Francji?" -> {"tool": "ANSWER", "content": "Paryż jest stolicą Francji."}
        * Twoja wypowiedź powinna mieć maksymalnie 3 zdania.
        """
    if "RESUME" in available_tools:
        system_prompt += """
        2. **tool: 'RESUME'**
        * Kiedy użytkownik poprosi cię o wznowienie oddtwarzania piosenki.
        * 'content' zawsze powinien być równy pustemu ciągowi tekstowemu.
        * Przykład: Użytkownik: "Wznów oddtwarzanie." -> {"tool": "RESUME", "content": ""}
        """
    if "PAUSE" in available_tools:
        system_prompt += """
        2. **tool: 'PAUSE'**
        * Kiedy użytkownik poprosi cię o zatrzymanie oddtwarzania piosenki.
        * 'content' zawsze powinien być równy pustemu ciągowi tekstowemu.
        * Przykład: Użytkownik: "Zatrzymaj oddtwarzanie." -> {"tool": "PAUSE", "content": ""}
        """
    full_prompt = system_prompt + "\nZawsze używaj odpowiedniego narzędzia w zależności od kontekstu.\nUżytkownik mówi: " + question
    
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
        await play_voice(THINKING_VOICE_LOCATION)
        await yt.stop_song()
        await text_to_speech(content)
    elif tool == "RESUME":
        await yt.resume_song()
    elif tool == "PAUSE":
        await yt.stop_song()


async def interactive_console(respeaker_index: int, yt: YouTubeSession):    
    pa = pyaudio.PyAudio()
    porcupine = pvporcupine.create(
        access_key=os.environ.get("PORCUPINE_KEY"),
        keyword_paths=['assets/Mamma-Mia_it_raspberry-pi_v3_0_0.ppn'],
        model_path='assets/porcupine_params_it.pv'
    )
    print("Created the audio instances")
    try:
        while True:
            if(await listen_for_keyword(pa, respeaker_index, porcupine)):
                while True:
                    await rec(pa, respeaker_index, porcupine.frame_length)  # ignore
                    user_input = await speech_to_text()
                    if not isinstance(user_input, str):
                        # await text_to_speech("Nie rozumiem co mówisz. Powtórz")
                        await play_voice(NOT_UNDERSTAND_VOICE_LOCATION)
                        continue
                    gemini_answer = await ask_gemini(user_input)
                    if gemini_answer.tool in gemini_tools:
                        await handle_gemini_answer(yt, gemini_answer.tool, gemini_answer.content)
                        break
    finally:
        porcupine.delete()
        pa.terminate()
        print("Terminated the audio instances")

async def main():
    yt = YouTubeSession()
    await yt.open_the_search_page()
    respeaker_index: int = await get_respeaker_index()
    await play_voice(SETUP_VOICE_LOCATION)
    await interactive_console(respeaker_index, yt)

if __name__ == "__main__":
    asyncio.run(main())
