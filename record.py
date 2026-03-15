import asyncio
from modules.speech import text_to_speech

content: str = "Cześć. Możesz mnie zawołać mówiąc: mamma mija. Po krótkiej chwili możesz zadać pytanie lub poprosić o odtworzenie piosenki."
loc: str = "assets/sounds/setup.wav"

async def main():
    await text_to_speech(content, loc)

if __name__ == "__main__":
    asyncio.run(main())