import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

URL = "https://developer.dataplatform.knmi.nl/open-data-api"

_DATA_DIR = Path(os.getenv("KNMI_CACHE_PATH", "/data")).expanduser()
CACHE = _DATA_DIR / "anonymous_key.json"


def _refresh_key() -> dict:
    logger.info("Fetching anonymous KNMI key from %s", URL)
    response = httpx.get(URL, timeout=30)
    response.raise_for_status()
    html = response.text

    expiry = re.search(
        r"available till the (\d+)(?:st|nd|rd|th) of (\w+) (\d{4})",
        html,
        re.I,
    )
    if not expiry:
        raise RuntimeError("Could not find expiry date on KNMI page.")

    day, month, year = expiry.groups()
    expires = datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date()

    key = re.search(
        r"The following key is available till.*?<pre><code>\s*([A-Za-z0-9+/=]+)\s*</code></pre>",
        html,
        re.S,
    )
    
    if not key:
        raise RuntimeError("Could not find anonymous key on KNMI page.")

    data = {
        "key": key.group(1).strip(),
        "expires": expires.isoformat(),
    }

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, indent=2))
    logger.info("Anonymous KNMI key cached — expires %s", expires.isoformat())
    return data


def get_anonymous_key() -> str:
    if CACHE.exists():
        try:
            data = json.loads(CACHE.read_text())
            if datetime.now(timezone.utc).date() < datetime.fromisoformat(data["expires"]).date():
                logger.debug("Using cached anonymous KNMI key (expires %s)", data["expires"])
                return data["key"]
            logger.info("Cached anonymous KNMI key has expired — refreshing")
        except Exception as e:
            logger.warning("Could not read anonymous key cache: %s — refreshing", e)

    return _refresh_key()["key"]


if __name__ == "__main__":
    print(get_anonymous_key())
