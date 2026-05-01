import asyncio
from modules.speech import text_to_speech

content: str = "Mogę odtworzyć piosenkę z YouTube Music, wznowić jej odtwarzanie, odpowiedzieć na Twoje pytania, podać Ci dane pogodowe oraz zrestartować i wyłączyć urządzenie. Jeśli chcesz zatrzymać odtwarzanie piosenki, po prostu zapytaj mnie o cokolwiek, a piosenka zostanie zatrzymana."
loc: str = "assets/sounds/help.wav"

async def main():
    await text_to_speech(content, loc)

if __name__ == "__main__":
    asyncio.run(main())