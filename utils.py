DIRECTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def degrees_to_compass(degrees: float) -> str:
    """Convert wind direction in degrees to an 8-point compass label."""
    index = int((degrees + 22.5) / 45) % 8
    return DIRECTIONS[index]


def format_time(iso_time: str) -> str:
    """Extract HH:MM from an ISO-8601 datetime string."""
    if "T" in iso_time:
        return iso_time.split("T")[1][:5]
    return iso_time


def format_weather_message(
    location: str,
    openmeteo: dict,
    knmi: dict | None = None,
    station_name: str | None = None,
    station_distance_km: float | None = None,
) -> str:
    """Build the Telegram reply message combining Open-Meteo and KNMI data."""

    # Open-Meteo block (always present)
    compass = degrees_to_compass(openmeteo["wind_direction"])
    sunrise = format_time(openmeteo["sunrise"])
    sunset = format_time(openmeteo["sunset"])

    lines = [
        f"📍 {location}",
        "",
        "━━━ Open-Meteo ━━━",
        f"🌡 Temperature:  {openmeteo['temperature']}°C",
        f"💧 Humidity:     {openmeteo['humidity']}%",
        f"💨 Wind:         {compass} at {openmeteo['wind_speed']} km/h",
        f"🌅 Sunrise:      {sunrise}",
        f"🌇 Sunset:       {sunset}",
    ]

    # KNMI block (only if available)
    if knmi:
        knmi_compass = knmi.get("wind_direction", "—")
        temp = f"{knmi['temperature']}°C" if knmi.get("temperature") is not None else "—"
        humidity = f"{knmi['humidity']}%" if knmi.get("humidity") is not None else "—"
        wind = f"{knmi_compass} at {knmi['wind_speed_kmh']} km/h" if knmi.get("wind_speed_kmh") is not None else "—"
        cloud = (
            f"{knmi['cloud_cover_pct']}% ({knmi['cloud_description']})"
            if knmi.get("cloud_cover_pct") is not None
            else "—"
        )
        station_line = station_name or "—"
        if station_distance_km is not None:
            station_line += f" ({station_distance_km} km)"

        lines += [
            "",
            "━━━ KNMI Station ━━━",
            f"🌡 Temperature:  {temp}",
            f"💧 Humidity:     {humidity}",
            f"💨 Wind:         {wind}",
            f"☁️ Cloud cover:  {cloud}",
            f"📡 Station:      {station_line}",
            f"🕒 Updated:      {knmi['observed_at']}",
        ]

    return "\n".join(lines)
