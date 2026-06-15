DIRECTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def degrees_to_compass(degrees: float) -> str:
    index = int((degrees + 22.5) / 45) % 8
    return DIRECTIONS[index]


def kmh_to_beaufort(speed: float) -> int:
    limits = [
        1, 6, 12, 20, 29, 39,
        50, 62, 75, 89, 103, 118
    ]

    for bft, limit in enumerate(limits):
        if speed < limit:
            return bft

    return 12


def format_time(iso_time: str) -> str:
    if "T" in iso_time:
        return iso_time.split("T")[1][:5]
    return iso_time

def cloud_description(cloud_cover: int) -> str:
    if cloud_cover <= 5:
        return "Clear"

    if cloud_cover <= 25:
        return "Mostly clear"

    if cloud_cover <= 50:
        return "Partly cloudy"

    if cloud_cover <= 75:
        return "Mostly cloudy"

    return "Overcast"

def format_weather_message(location: str, data: dict) -> str:
    compass = degrees_to_compass(data["wind_direction"])
    beaufort = kmh_to_beaufort(data["wind_speed"])

    sunrise = format_time(data["sunrise"])
    sunset = format_time(data["sunset"])

    cloud_desc = cloud_description(data["cloud_cover"])

    return (
        f"📍 {location}\n"
        f"\n"
        f"🌡 Temperature: {data['temperature']}°C\n"
        f"🥶 Feels Like: {data['feels_like']}°C\n"
        f"\n"
        f"💧 Humidity: {data['humidity']}%\n"
        f"\n"
        f"💨 Wind: {compass}\n"
        f"💨 Speed: Bft {beaufort} ({data['wind_speed']} km/h)\n"
        f"\n"
        f"🌅 Sunrise: {sunrise}\n"
        f"🌇 Sunset: {sunset}\n"
        f"☁️ Cloud Cover: {data['cloud_cover']}% ({cloud_desc})\n"
    )