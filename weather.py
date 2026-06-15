import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

_cache: dict[tuple[float, float], tuple[float, dict]] = {}
CACHE_TTL = 300  # seconds


async def get_weather(lat: float, lon: float) -> dict:
    """Fetch current weather from Open-Meteo. Results are cached for 5 minutes."""

    cache_key = (round(lat, 3), round(lon, 3))
    now = time.monotonic()

    if cache_key in _cache:
        cached_at, cached_data = _cache[cache_key]
        if now - cached_at < CACHE_TTL:
            logger.info("Cache hit for %s", cache_key)
            return cached_data

    timezone = os.getenv("TZ", "Europe/Amsterdam")

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join([
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "wind_speed_10m",
            "wind_direction_10m",
            "cloud_cover",
        ]),
        "wind_speed_unit": "kmh",
        "daily": "sunrise,sunset",
        "timezone": timezone,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(OPEN_METEO_URL, params=params)
        response.raise_for_status()
        data = response.json()

    result = {
        "temperature": data["current"]["temperature_2m"],
        "feels_like": data["current"]["apparent_temperature"],
        "humidity": data["current"]["relative_humidity_2m"],
        "wind_speed": data["current"]["wind_speed_10m"],
        "wind_direction": data["current"]["wind_direction_10m"],
        "sunrise": data["daily"]["sunrise"][0],
        "sunset": data["daily"]["sunset"][0],
        "cloud_cover": data["current"]["cloud_cover"],
    }

    _cache[cache_key] = (now, result)
    logger.info("Fetched weather for %s", cache_key)

    return result
