from pydantic import BaseModel
from typing import Union
from functools import cache
from google.genai.types import GenerateContentConfig, ThinkingConfig
from modules.large_variables import CORE_PROMPT, NAMED_PROMPTS
from modules.speech import play_voice
from google import genai
import os

SOUNDS_PATH: str = "assets/sounds/"
HIGH_DEMAND_ERROR_VOICE_LOCATION: str = SOUNDS_PATH + "high_demand_error.wav"

class GeminiAnswer(BaseModel):
    tool: str
    content: str


@cache
def get_gemini_client() -> genai.Client:
    """Zwraca instancję klienta Gemini, inicjalizując go, tylko podczas pierwszego wywołania."""
    print("Inicjalizacja klienta Gemini...")
    return genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

def gemini_simple_question(question: str, ai_model: str):
    client: genai.Client = get_gemini_client()
    config_kwargs = {}
    if "gemini" in ai_model.lower():
        config_kwargs["thinking_config"] = ThinkingConfig(thinking_budget=0)
        
    config = GenerateContentConfig(**config_kwargs)
    response = client.models.generate_content(
        model=ai_model,
        contents=question,
        config=config,
    )
    return str(response.text).strip()

def ask_gemini(question: str, tool_selection: bool = True, ai_model: str = "gemini-3.1-flash-lite-preview") -> Union[GeminiAnswer, str]:
    """
    Zadaje pytanie Gemini AI.

    Args:
        question (str): Pytanie od użytkownika.
        tool_selection (bool): True (zwraca GeminiAnswer z użyciem narzędzi), False (zwraca czysty tekst).
    """
    
    try:
        if not tool_selection:
            return gemini_simple_question(question, ai_model)
        client = get_gemini_client()
        system_prompt: str = CORE_PROMPT
        for prompt_text in NAMED_PROMPTS.values():
            system_prompt += prompt_text

        full_prompt = (f"{system_prompt}\nZawsze używaj odpowiedniego narzędzia "
                    f"w zależności od kontekstu.\nUżytkownik mówi: {question}")

        config_kwargs = {}
        if "gemini" in ai_model.lower():
            config_kwargs["thinking_config"] = ThinkingConfig(thinking_budget=0)
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = {
            "type": "OBJECT",
            "properties": {
                "tool": {"type": "STRING"},
                "content": {"type": "STRING"}
            },
            "required": ["tool", "content"]
        }
        config = GenerateContentConfig(**config_kwargs)

        response = client.models.generate_content(
            model=ai_model,
            contents=full_prompt,
            config=config,
        )

        raw_text = response.text
        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        
        try:
            return GeminiAnswer.model_validate_json(clean_json)
        except Exception as e:
            print(f"Błąd parsowania JSON: {e}")
            print(f"Otrzymany tekst: {raw_text}")
            raise e
    except genai.errors.ServerError as e:
        if "503" in str(e) or "UNAVAILABLE" in str(e):
            if ai_model == "gemma-4-31b-it":
                print(f"Błąd 503: Obsługiwane modele Gemini są przeciążone.")
                play_voice(HIGH_DEMAND_ERROR_VOICE_LOCATION)
                return GeminiAnswer(tool="ERROR", content="")
            else:
                print("Próba połączenia się z gemma-4-31b-it ze względu na przeciążenie modelu...")
                return ask_gemini(question, tool_selection, ai_model="gemma-4-31b-it")
        raise e
    except Exception as e:
        print(f"Napotkano nieznany błąd: {e}")
        return GeminiAnswer(tool="ERROR", content="")
