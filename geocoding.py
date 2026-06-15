import logging

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "telegram-weather-bot/1.0"


async def reverse_geocode(lat: float, lon: float) -> str:
    """Convert coordinates to a human-readable location name.

    Returns 'City, Country' on success, or the raw coordinates as a
    formatted string if the lookup fails.
    """

    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "zoom": 18,
        "addressdetails": 1,
    }
    headers = {"User-Agent": USER_AGENT}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                NOMINATIM_URL, params=params, headers=headers
            )
            response.raise_for_status()
            data = response.json()

        address = data.get("address", {})

        # Most specific detail first
        detail = (
            address.get("neighbourhood")
            or address.get("suburb")
            or address.get("quarter")
            or address.get("road")
        )
        city = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
        )
        country = address.get("country", "")

        parts = [p for p in (detail, city, country) if p]
        return ", ".join(parts) or "Unknown"

    except Exception as e:
        logger.warning("Reverse geocoding failed: %s", e)
        return f"{lat:.2f}, {lon:.2f}"
