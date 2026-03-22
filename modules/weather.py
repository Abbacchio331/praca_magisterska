import python_weather
from python_weather import Kind
import datetime
import json
from regex import findall
from modules.speech import play_voice, text_to_speech

SOUNDS_PATH: str = "assets/sounds/"
PROCESSING_ERROR_VOICE_LOCATION: str = SOUNDS_PATH + "processing_error.wav"

en_to_pl_weather_kind = lambda kind: kinds_dict[str(kind).upper()]
kinds_dict: dict = {
    "SUNNY": "Słonecznie.",
    "PARTLY CLOUDY": "Częściowe zachmurzenie.",
    "CLOUDY": "Pochmurnie.",
    "VERY CLOUDY": "Duże zachmurzenie.",
    "FOG": "Mgła.",
    "LIGHT SHOWERS": "Słabe przelotne opady deszczu.",
    "LIGHT SLEET SHOWERS": "Słabe przelotne opady deszczu ze śniegiem.",
    "LIGHT SLEET": "Słaby deszcz ze śniegiem.",
    "THUNDERY SHOWERS": "Przelotne opady z burzą.",
    "LIGHT SNOW": "Słabe opady śniegu.",
    "HEAVY SNOW": "Obfite opady śniegu.",
    "LIGHT RAIN": "Słaby deszcz.",
    "HEAVY SHOWERS": "Intensywne przelotne opady deszczu.",
    "HEAVY RAIN": "Intensywne opady deszczu.",
    "LIGHT SNOW SHOWERS": "Słabe przelotne opady śniegu.",
    "HEAVY SNOW SHOWERS": "Intensywne przelotne opady śniegu.",
    "THUNDERY HEAVY RAIN": "Intensywny deszcz z burzą.",
    "THUNDERY SNOW SHOWERS": "Przelotne opady śniegu z burzą."
}

def validate_date(date: str) -> datetime.date | None:
    if findall(r"\A\s*\d{4}-\d{2}-\d{2}\s*\Z", date):
        return datetime.date(*[int(d) for d in date.strip().split("-")])
    return None

def pl_weather(temp, kind: Kind | None = None) -> str:
    return f"{temp} stopni Celsjusza. {en_to_pl_weather_kind(kind)}" \
        if kind else f"{temp} stopni Celsjusza"

async def get_weather(city: str, date: str) -> str | None:
    date: datetime.date | None = validate_date(date)
    if date is None:
        print("Incorrect date format")
        return None
    try:
        async with python_weather.Client(unit=python_weather.METRIC) as client:
            weather: python_weather.Forecast = await client.get(city)
            for daily_forecast in weather:
                if daily_forecast.date == date:
                    return pl_weather(daily_forecast.temperature) if not date == datetime.date.today() else pl_weather(weather.temperature, weather.kind)
            print("Date not found")
            return None
    except python_weather.errors.RequestError as error:
        print(str(error))
        return None


def parse_ai_weather_response(ai_string: str) -> tuple:
    try:
        parsed_dict = json.loads(ai_string)
        city = parsed_dict.get("city")
        date = parsed_dict.get("date")

        if not city or not date:
            print("AI zapomniało podać miasto!")
            return None, None

        return city, date

    except json.JSONDecodeError as e:
        print(f"AI wygenerowało uszkodzony JSON. Szczegóły: {e}")
        print(f"Otrzymany tekst: {ai_string}")
        return None, None


async def say_weather(content: str):
    city, date = parse_ai_weather_response(content)
    if not city or not date:
        await play_voice(PROCESSING_ERROR_VOICE_LOCATION)
    else:
        weather: str = await get_weather(city, date)
        if weather is not None:
            await text_to_speech(weather)
        else:
            await play_voice(PROCESSING_ERROR_VOICE_LOCATION)