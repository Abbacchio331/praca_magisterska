import asyncio
from modules.speech import text_to_speech

content: str = "Zatrzymałam oddtwarzanie piosenki."
loc: str = "assets/sounds/stopped_song.wav"

async def main():
    await text_to_speech(content, loc)

if __name__ == "__main__":
    asyncio.run(main())