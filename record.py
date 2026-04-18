import asyncio
from modules.speech import text_to_speech

content: str = "Przekroczyłeś darmowy dzienny limit korzystania z modułu głosowego. Odezwij się do mnie jutro."
loc: str = "assets/sounds/exceeded_tts_rate_limit.wav"

async def main():
    await text_to_speech(content, loc)

if __name__ == "__main__":
    asyncio.run(main())