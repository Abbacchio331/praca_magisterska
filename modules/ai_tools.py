from pydantic import BaseModel
from typing import Union
from functools import cache
from google.genai.types import GenerateContentConfig, ThinkingConfig
from modules.large_variables import CORE_PROMPT, NAMED_PROMPTS
from google import genai
import os


class GeminiAnswer(BaseModel):
    tool: str
    content: str


@cache
def get_gemini_client() -> genai.Client:
    """Zwraca instancję klienta Gemini, inicjalizując go, tylko podczas pierwszego wywołania."""
    print("Inicjalizacja klienta Gemini...")
    return genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


def ask_gemini(question: str, tool_selection: bool = True) -> Union[GeminiAnswer, str]:
    """
    Zadaje pytanie Gemini AI.

    Args:
        question (str): Pytanie od użytkownika.
        tool_selection (bool): True (zwraca GeminiAnswer z użyciem narzędzi), False (zwraca czysty tekst).
    """
    client = get_gemini_client()
    if not tool_selection:
        config = GenerateContentConfig(
            thinking_config=ThinkingConfig(thinking_budget=0)  # type: ignore
        )
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=question,
            config=config,
        )
        return str(response.text).strip()

    # Złożony tryb z narzędziami (tool_selection = True)
    system_prompt: str = CORE_PROMPT
    for prompt_text in NAMED_PROMPTS.values():
        system_prompt += prompt_text

    full_prompt = (f"{system_prompt}\nZawsze używaj odpowiedniego narzędzia "
                   f"w zależności od kontekstu.\nUżytkownik mówi: {question}")

    response_schema = {
        "type": "OBJECT",
        "properties": {
            "tool": {"type": "STRING"},
            "content": {"type": "STRING"}
        },
        "required": ["tool", "content"]
    }

    config = GenerateContentConfig(
        response_mime_type="application/json",  # type: ignore
        response_schema=response_schema,  # type: ignore
        thinking_config=ThinkingConfig(thinking_budget=0)  # type: ignore
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=full_prompt,
        config=config,
    )

    return GeminiAnswer.model_validate_json(str(response.text))
