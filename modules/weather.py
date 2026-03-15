import python_weather

en_to_pl_weather_kind = lambda kind: kinds_dict[str(kind).upper()]
pl_weather = lambda weather: f"{weather.temperature}°C, {en_to_pl_weather_kind(weather.kind)}"
kinds_dict: dict = {
    "SUNNY": "słonecznie",
    "PARTLY_CLOUDY": "częściowe zachmurzenie",
    "CLOUDY": "pochmurnie",
    "VERY_CLOUDY": "duże zachmurzenie",
    "FOG": "mgła",
    "LIGHT_SHOWERS": "słabe przelotne opady deszczu",
    "LIGHT_SLEET_SHOWERS": "słabe przelotne opady deszczu ze śniegiem",
    "LIGHT_SLEET": "słaby deszcz ze śniegiem",
    "THUNDERY_SHOWERS": "przelotne opady z burzą",
    "LIGHT_SNOW": "słabe opady śniegu",
    "HEAVY_SNOW": "obfite opady śniegu",
    "LIGHT_RAIN": "słaby deszcz",
    "HEAVY_SHOWERS": "intensywne przelotne opady deszczu",
    "HEAVY_RAIN": "intensywne opady deszczu",
    "LIGHT_SNOW_SHOWERS": "słabe przelotne opady śniegu",
    "HEAVY_SNOW_SHOWERS": "intensywne przelotne opady śniegu",
    "THUNDERY_HEAVY_RAIN": "intensywny deszcz z burzą",
    "THUNDERY_SNOW_SHOWERS": "przelotne opady śniegu z burzą"
}

async def get_weather(city) -> str:
    try:
        async with python_weather.Client(unit=python_weather.METRIC) as client:
            weather: python_weather.Forecast = await client.get(city)
            return pl_weather(weather)
    except python_weather.errors.RequestError as error:
        return f"Error {error}"
