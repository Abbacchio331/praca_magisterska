import asyncio
from modules.speech import text_to_speech

content: str = "Mam problem z otworzeniem tej strony. Zresetuj mnie."
loc: str = "assets/sounds/blank_page.wav"

async def main():
    await text_to_speech(content, loc)

if __name__ == "__main__":
    asyncio.run(main())