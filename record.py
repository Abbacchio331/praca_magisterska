import asyncio
from modules.speech import text_to_speech

content: str = "Wyłączam system."
loc: str = "assets/sounds/poweroff.wav"

async def main():
    await text_to_speech(content, loc)

if __name__ == "__main__":
    asyncio.run(main())