"""
KNMI integration via the KNMI Open Data Platform — NetCDF dataset.

Flow:
  Startup:
    Load station cache from disk (instant) → bot starts accepting messages →
    background task checks disk NC cache → downloads fresh if stale →
    extracts station metadata → writes caches to disk. Retries hourly.

  /start command:
    Reply immediately → background: ensure_latest_knmi_data()
      ├── observation stale (filename timestamp > 10 min)?
      │     └── Yes → download latest .nc, update cache
      └── No → do nothing

  Per weather request:
    1. find_nearest_station(lat, lon)  → wmo_id (e.g. "06260"), name, distance
    2. get_knmi_observation(wmo_id)  →
         a. In-memory Dataset present? → use it
         b. Disk NC file present?      → load it
         c. Neither                    → download (recovery path only)
         d. Read station row, return observation dict

Disk cache layout:
  data/
  ├── knmi_stations.json     Station coords (weekly refresh)
  ├── latest.nc              Most recent NetCDF file
  └── latest_nc_meta.json    {"filename": "...", "downloaded_at": "..."}

Dataset:
  10-minute-in-situ-meteorological-observations  version 1.0

Confirmed variable names (from ncdump inspection):
  ta   – Air Temperature 1 Min Mean          (°C)
  rh   – Relative Humidity 1 Min Mean        (%)
  ff   – Wind Speed at 10 m Mean with MD     (m/s → converted to km/h)
  dd   – Wind Direction Mean with MD         (degrees)
  n    – Total Cloud Cover                   (okta, 0–8)

Station IDs:
  WMO IDs stored directly (e.g. "06260", "78871"). No prefix mapping.

Authentication:
  Header:  Authorization: <KNMI_API_KEY>
"""

import asyncio
import json
import logging
import math
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from utils import cloud_description
import httpx
import xarray as xr
from knmi_api_key import get_anonymous_key

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

KNMI_OPEN_DATA_BASE = "https://api.dataplatform.knmi.nl/open-data/v1"
DATASET_NAME = "10-minute-in-situ-meteorological-observations"
DATASET_VERSION = "1.0"

_DATA_DIR = Path(os.getenv("KNMI_CACHE_PATH", "/data")).expanduser()
CACHE_PATH = _DATA_DIR / "knmi_stations.json"
NC_DISK_PATH = _DATA_DIR / "latest.nc"
NC_META_PATH = _DATA_DIR / "latest_nc_meta.json"

CACHE_MAX_AGE_DAYS = 7
MAX_STATION_DISTANCE_KM = 50
STATION_REFRESH_RETRY_SECONDS = 3600  # 1 hour
NC_TTL_SECONDS = 600  # 10 minutes — matches KNMI update interval


def _api_key() -> str:
    try:
        return get_anonymous_key()
    except Exception as e:
        logger.warning(
            "Could not refresh anonymous KNMI key: %s. "
            "Falling back to KNMI_API_KEY.",
            e,
        )

        key = os.getenv("KNMI_API_KEY", "")
        if not key:
            raise RuntimeError(
                "No anonymous key available and KNMI_API_KEY is not set."
            )

        return key

def _headers() -> dict:
    return {"Authorization": _api_key()}


# ---------------------------------------------------------------------------
# Station cache
# ---------------------------------------------------------------------------

def _load_cache() -> dict:
    """Load station cache from disk (fallback / seed)."""
    if not CACHE_PATH.exists():
        logger.warning("Station cache not found at %s", CACHE_PATH)
        return {"last_updated": None, "stations": {}}
    with CACHE_PATH.open() as f:
        return json.load(f)


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("w") as f:
        json.dump(cache, f, indent=2)
    logger.info("Station cache saved — %d stations", len(cache.get("stations", {})))


def _cache_is_stale(cache: dict) -> bool:
    last = cache.get("last_updated")
    if not last:
        return True
    age = datetime.now(timezone.utc) - datetime.fromisoformat(
        last.replace("Z", "+00:00")
    )
    return age > timedelta(days=CACHE_MAX_AGE_DAYS)


def _build_station_cache_from_ds(ds: xr.Dataset) -> dict:
    """Extract station metadata (wmo_id, name, lat, lon) from a Dataset."""
    stations = {}
    wmo_ids = list(ds.station.values)
    names = list(ds["stationname"].values)
    lats = list(ds["lat"].values)
    lons = list(ds["lon"].values)

    for i, wmo_id in enumerate(wmo_ids):
        stations[str(wmo_id)] = {
            "name": str(names[i]).strip(),
            "lat": float(lats[i]),
            "lon": float(lons[i]),
        }

    return {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "stations": stations,
    }


# Global in-memory station cache
_station_cache: dict = {}


def _cache_has_coords() -> bool:
    sample = next(iter(_station_cache.get("stations", {}).values()), {})
    return "lat" in sample and "lon" in sample


async def ensure_station_cache() -> None:
    """Load station cache from disk and schedule background refresh if stale.

    Returns immediately so the bot can start accepting messages right away.
    """
    global _station_cache
    _station_cache = _load_cache()

    if _cache_has_coords() and not _cache_is_stale(_station_cache):
        logger.info(
            "Station cache is fresh — %d stations",
            len(_station_cache["stations"]),
        )
        return

    asyncio.create_task(_refresh_station_cache_bg())


async def _refresh_station_cache_bg() -> None:
    """Background task: get a Dataset (disk or download), rebuild station cache.

    Retries hourly on failure.
    """
    global _station_cache
    while True:
        try:
            logger.info("Background: refreshing station cache…")
            ds = await _load_or_download_dataset()
            _station_cache = _build_station_cache_from_ds(ds)
            _save_cache(_station_cache)

            logger.info(
                "Background: station cache ready — %d stations",
                len(_station_cache["stations"]),
            )
            return

        except Exception as e:
            logger.error("Background: could not refresh station cache: %s", e)
            if _cache_has_coords():
                logger.warning(
                    "Using stale disk cache with %d stations — "
                    "retrying in %d seconds",
                    len(_station_cache["stations"]),
                    STATION_REFRESH_RETRY_SECONDS,
                )
            else:
                logger.error(
                    "Station cache has no coordinates — KNMI lookups will fail. "
                    "Retrying in %d seconds.",
                    STATION_REFRESH_RETRY_SECONDS,
                )
            await asyncio.sleep(STATION_REFRESH_RETRY_SECONDS)


# ---------------------------------------------------------------------------
# Nearest station (Haversine)
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearest_station(lat: float, lon: float) -> tuple[str, str, float]:
    """Return (wmo_id, station_name, distance_km).

    Raises ValueError if no station is within MAX_STATION_DISTANCE_KM
    or if the cache has no coordinates.
    """
    stations = _station_cache.get("stations", {})
    if not stations:
        raise ValueError("Station cache is empty")

    best_id, best_name, best_dist = None, None, float("inf")
    for wmo_id, meta in stations.items():
        if "lat" not in meta or "lon" not in meta:
            continue
        d = _haversine_km(lat, lon, meta["lat"], meta["lon"])
        if d < best_dist:
            best_id, best_name, best_dist = wmo_id, meta["name"], d

    if best_id is None:
        raise ValueError("Station cache has no entries with coordinates")

    if best_dist > MAX_STATION_DISTANCE_KM:
        raise ValueError(
            f"No KNMI station within {MAX_STATION_DISTANCE_KM} km "
            f"(nearest: {best_name} at {best_dist:.1f} km)"
        )

    return best_id, best_name, round(best_dist, 1)


# ---------------------------------------------------------------------------
# KNMI Open Data file fetch
# ---------------------------------------------------------------------------

async def _get_latest_filename() -> str:
    """Return the filename of the most recent .nc file in the dataset."""
    url = (
        f"{KNMI_OPEN_DATA_BASE}/datasets/{DATASET_NAME}"
        f"/versions/{DATASET_VERSION}/files"
    )
    params = {
        "maxKeys": 1,
        "orderBy": "created",
        "sorting": "desc",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=_headers(), params=params)
        r.raise_for_status()
        data = r.json()

    files = data.get("files", [])
    if not files:
        raise RuntimeError("No files found in KNMI dataset")

    filename = files[0].get("filename")
    logger.info("Latest KNMI file: %s", filename)
    return filename


async def _get_download_url(filename: str) -> str:
    """Get a temporary signed download URL for a specific .nc file."""
    url = (
        f"{KNMI_OPEN_DATA_BASE}/datasets/{DATASET_NAME}"
        f"/versions/{DATASET_VERSION}/files/{filename}/url"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=_headers())
        r.raise_for_status()
        data = r.json()

    download_url = data.get("temporaryDownloadUrl")
    if not download_url:
        raise RuntimeError(f"No temporaryDownloadUrl in response: {data}")
    return download_url


async def _download_nc(download_url: str) -> bytes:
    """Download the .nc file and return raw bytes."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(download_url)
        r.raise_for_status()
    return r.content


async def _fetch_nc_bytes() -> tuple[str, bytes]:
    """Full download pipeline: list → url → download. Returns (filename, bytes)."""
    filename = await _get_latest_filename()
    download_url = await _get_download_url(filename)
    nc_bytes = await _download_nc(download_url)
    return filename, nc_bytes


# ---------------------------------------------------------------------------
# NC file parsing
# ---------------------------------------------------------------------------

def _open_nc_file(path: Path) -> xr.Dataset:
    """Open an NC file from disk, load into memory, close file handle."""
    ds = xr.open_dataset(str(path))
    ds.load()
    ds.close()
    return ds


def _parse_nc_bytes(nc_bytes: bytes) -> xr.Dataset:
    """Write bytes to a temp file, parse, clean up. Returns in-memory Dataset."""
    with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as tmp:
        tmp.write(nc_bytes)
        tmp_path = tmp.name

    try:
        return _open_nc_file(Path(tmp_path))
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Disk cache for NC file
# ---------------------------------------------------------------------------

def _save_nc_to_disk(nc_bytes: bytes, filename: str) -> None:
    """Write NC file and metadata to disk."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    NC_DISK_PATH.write_bytes(nc_bytes)
    NC_META_PATH.write_text(json.dumps({
        "filename": filename,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }))
    logger.info("NC file saved to disk (%s, %d bytes)", filename, len(nc_bytes))


def _observation_time_from_filename(filename: str) -> datetime | None:
    """Parse the observation timestamp embedded in the NC filename.

    Example: KMDS__OPER_P___10M_OBS_L2_202606281020.nc → 2026-06-28 10:20 UTC
    Returns None if the filename doesn't match the expected pattern.
    """
    match = re.search(r"(\d{12})\.nc$", filename)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d%H%M").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _observation_is_stale() -> bool:
    """Return True if the cached observation data is older than NC_TTL_SECONDS.

    Uses the timestamp in the filename (= actual observation time), not
    downloaded_at. Falls back to True (stale) if the cache is missing or
    the filename cannot be parsed.
    """
    if not NC_META_PATH.exists() or not NC_DISK_PATH.exists():
        return True
    try:
        meta = json.loads(NC_META_PATH.read_text())
        filename = meta.get("filename", "")
        obs_time = _observation_time_from_filename(filename)
        if obs_time is None:
            logger.warning(
                "Could not parse observation time from filename %r — treating as stale",
                filename,
            )
            return True
        age = (datetime.now(timezone.utc) - obs_time).total_seconds()
        logger.debug("Observation age: %.0fs (filename: %s)", age, filename)
        return age > NC_TTL_SECONDS
    except Exception as e:
        logger.warning("Could not check observation staleness: %s — treating as stale", e)
        return True


def _load_ds_from_disk() -> xr.Dataset | None:
    """Load Dataset from disk NC file. Returns None if missing or corrupt."""
    if not NC_DISK_PATH.exists():
        return None
    try:
        return _open_nc_file(NC_DISK_PATH)
    except Exception as e:
        logger.warning("Could not load disk NC file: %s", e)
        return None

def _disk_cached_filename() -> str:
    """Return filename stored in latest_nc_meta.json."""
    try:
        if NC_META_PATH.exists():
            meta = json.loads(NC_META_PATH.read_text())
            return meta.get("filename", "unknown")
    except Exception:
        pass

    return "unknown"

# ---------------------------------------------------------------------------
# Dataset extraction
# ---------------------------------------------------------------------------

def _oktas_to_percent(oktas: float) -> int:
    return max(0, min(100, round((oktas / 8) * 100)))


def _degrees_to_compass(degrees: float) -> str:
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[int((degrees + 22.5) / 45) % 8]


def _extract_from_ds(ds: xr.Dataset, wmo_id: str) -> dict:
    """Extract weather for a station from an in-memory Dataset."""
    if wmo_id not in _station_index:
        raise ValueError(
            f"Station {wmo_id} not found in dataset. "
            f"Available: {list(_station_index.keys())[:5]}…"
        )

    idx = _station_index[wmo_id]

    def val(var: str) -> float | None:
        try:
            v = float(ds[var].values[idx][0])
            return None if math.isnan(v) else v
        except (KeyError, IndexError, TypeError):
            return None

    ta = val("ta")
    rh = val("rh")
    ff = val("ff")
    dd = val("dd")
    n  = val("n")

    try:
        ts = ds.time.values[0]
        tz_name = os.getenv("TZ", "Europe/Amsterdam")
        dt_utc = datetime.fromisoformat(str(ts).split(".")[0]).replace(tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone(ZoneInfo(tz_name))
        observed_at = dt_local.strftime("%H:%M")
    except Exception:
        observed_at = "—"

    wind_kmh = round(ff * 3.6, 1) if ff is not None else None
    cloud_pct = _oktas_to_percent(n) if n is not None else None

    return {
        "temperature": round(ta, 1) if ta is not None else None,
        "humidity": round(rh) if rh is not None else None,
        "wind_speed_kmh": wind_kmh,
        "wind_direction": _degrees_to_compass(dd) if dd is not None else None,
        "wind_direction_deg": round(dd) if dd is not None else None,
        "cloud_cover_pct": cloud_pct,
        "cloud_description": cloud_description(cloud_pct) if cloud_pct is not None else None,
        "observed_at": observed_at,
    }


# ---------------------------------------------------------------------------
# Dataset cache (in-memory)
# ---------------------------------------------------------------------------

_ds_cache: dict = {
    "filename": None,
    "dataset": None,
}
_station_index: dict[str, int] = {}
_ds_lock = asyncio.Lock()
_nc_refresh_running: bool = False


def _build_station_index(ds: xr.Dataset) -> dict[str, int]:
    """Build {wmo_id: array_index} lookup from a Dataset."""
    return {str(wmo_id): i for i, wmo_id in enumerate(ds.station.values)}


def _populate_memory_cache(ds: xr.Dataset, filename: str) -> None:
    """Update in-memory dataset cache and station index."""
    _ds_cache["filename"] = filename
    _ds_cache["dataset"] = ds
    _station_index.clear()
    _station_index.update(_build_station_index(ds))


async def _load_or_download_dataset() -> xr.Dataset:
    """Return a Dataset from disk if present, otherwise download from KNMI.

    This is the recovery/bootstrap path — not the normal read path.
    Normal reads go through _get_cached_dataset().
    """
    ds = _load_ds_from_disk()
    if ds is not None:
        cached_filename = _disk_cached_filename()
        logger.info("Loaded dataset from disk (%s)", cached_filename)
        _populate_memory_cache(ds, cached_filename)
        return ds

    filename, nc_bytes = await _fetch_nc_bytes()
    ds = _parse_nc_bytes(nc_bytes)
    _save_nc_to_disk(nc_bytes, filename)
    _populate_memory_cache(ds, filename)
    logger.info("Dataset downloaded and cached (%s)", filename)
    return ds


def _get_cached_dataset() -> xr.Dataset | None:
    """Return the in-memory Dataset if present, otherwise load from disk.

    Returns None if neither is available. Never downloads.
    """
    if _ds_cache["dataset"] is not None:
        return _ds_cache["dataset"]

    ds = _load_ds_from_disk()
    if ds is not None:
        cached_filename = _disk_cached_filename()
        _populate_memory_cache(ds, cached_filename)
        return ds

    return None


# ---------------------------------------------------------------------------
# NC observation freshness + background refresh (called from /start)
# ---------------------------------------------------------------------------

async def ensure_latest_knmi_data() -> None:
    """Check whether the cached observations are stale and refresh if needed.

    Safe to call from /start (or anywhere). Returns immediately.
    A background task does the actual download so the caller is never blocked.
    Only one refresh runs at a time.
    """
    global _nc_refresh_running

    if _nc_refresh_running:
        logger.debug("NC refresh already in progress — skipping")
        return

    if not _observation_is_stale():
        logger.debug(
            "Observations are fresh (%s) — no refresh needed",
            _disk_cached_filename(),
        )
        return

    _nc_refresh_running = True
    asyncio.create_task(_refresh_nc_bg())


async def _refresh_nc_bg() -> None:
    """Background task: download the latest .nc file and update caches."""
    global _nc_refresh_running
    try:
        logger.info("Background: refreshing NC observations…")
        filename, nc_bytes = await _fetch_nc_bytes()
        ds = _parse_nc_bytes(nc_bytes)
        _save_nc_to_disk(nc_bytes, filename)
        _populate_memory_cache(ds, filename)
        logger.info("Background: NC observations refreshed (%s)", filename)
    except Exception as e:
        logger.error("Background: NC refresh failed: %s", e)
    finally:
        _nc_refresh_running = False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def get_knmi_observation(wmo_id: str) -> dict:
    """Get latest observation for a station.

    Reads from the in-memory or disk cache. If neither is available
    (first run, cache wiped), downloads once as a recovery path.
    Never checks staleness — that is the responsibility of ensure_latest_knmi_data().
    """
    ds = _get_cached_dataset()

    if ds is None:
        logger.warning("No cached dataset — downloading as recovery path")
        async with _ds_lock:
            ds = _get_cached_dataset()
            if ds is None:
                ds = await _load_or_download_dataset()

    return _extract_from_ds(ds, wmo_id)
