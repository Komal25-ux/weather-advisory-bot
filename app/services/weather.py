import logging
from datetime import datetime, timezone as dt_timezone
from typing import Optional, Dict, Any, List
import httpx

from app.config import settings
from app.schemas.weather import WeatherFacts

logger = logging.getLogger("weather-advisory-bot.services.weather")


class WeatherFetchError(Exception):
    """Raised when weather API calls fail, time out, or return HTTP errors."""
    pass


class WeatherDataValidationError(Exception):
    """Raised when weather API returns malformed or unparseable JSON payloads."""
    pass


def _extract_window_indices(
    time_strings: List[str],
    time_reference: str
) -> List[int]:
    """
    Deterministically identifies the hourly indices in the forecast corresponding
    to the requested time reference (e.g. morning, afternoon, evening, tomorrow).
    """
    cleaned_ref = time_reference.strip().lower()
    if not time_strings:
        return []

    # Identify base dates from the payload
    # Open-Meteo time format: "2026-09-06T14:00"
    today_date = time_strings[0].split("T")[0]
    dates = sorted(list(dict.fromkeys(t.split("T")[0] for t in time_strings)))
    tomorrow_date = dates[1] if len(dates) > 1 else today_date

    target_date = today_date
    start_hour, end_hour = 0, 23

    if "tomorrow" in cleaned_ref:
        target_date = tomorrow_date
        if "morning" in cleaned_ref:
            start_hour, end_hour = 6, 11
        elif "afternoon" in cleaned_ref:
            start_hour, end_hour = 12, 17
        elif "evening" in cleaned_ref or "night" in cleaned_ref:
            start_hour, end_hour = 18, 22
        else:
            start_hour, end_hour = 8, 20
    elif "morning" in cleaned_ref:
        start_hour, end_hour = 6, 11
    elif "afternoon" in cleaned_ref:
        start_hour, end_hour = 12, 17
    elif "evening" in cleaned_ref or "night" in cleaned_ref:
        start_hour, end_hour = 18, 22
    elif "now" in cleaned_ref or "current" in cleaned_ref:
        return [0]  # First available hour or current block

    matching_indices: List[int] = []
    for idx, t_str in enumerate(time_strings):
        try:
            d_part, h_part = t_str.split("T")
            hour = int(h_part.split(":")[0])
            if d_part == target_date and start_hour <= hour <= end_hour:
                matching_indices.append(idx)
        except (ValueError, IndexError):
            continue

    return matching_indices


def _aggregate_hourly_window(
    hourly: Dict[str, Any],
    indices: List[int],
    target_period: str
) -> WeatherFacts:
    """
    Aggregates weather metrics over a specific hourly time window.
    Conservative for outdoor safety: takes peak risk (max wind, max precip prob, max UV).
    """
    def _slice_metric(key: str) -> List[float]:
        series = hourly.get(key, [])
        vals = []
        for i in indices:
            if i < len(series) and series[i] is not None:
                vals.append(float(series[i]))
        return vals

    temps = _slice_metric("temperature_2m")
    humidities = _slice_metric("relative_humidity_2m")
    precips = _slice_metric("precipitation")
    precip_probs = _slice_metric("precipitation_probability")
    winds = _slice_metric("wind_speed_10m")
    gusts = _slice_metric("wind_gusts_10m")
    uvs = _slice_metric("uv_index")
    clouds = _slice_metric("cloud_cover")
    visibilities = _slice_metric("visibility")
    is_day_list = _slice_metric("is_day")

    # Safe aggregations without fabrication
    avg_temp = round(sum(temps) / len(temps), 1) if temps else None
    avg_humidity = int(round(sum(humidities) / len(humidities))) if humidities else None
    tot_precip = round(sum(precips), 1) if precips else 0.0
    max_precip_prob = int(round(max(precip_probs))) if precip_probs else None
    max_wind = round(max(winds), 1) if winds else None
    max_gust = round(max(gusts), 1) if gusts else None
    max_uv = round(max(uvs), 1) if uvs else None
    avg_cloud = int(round(sum(clouds) / len(clouds))) if clouds else None
    min_vis_m = min(visibilities) if visibilities else None
    vis_km = round(min_vis_m / 1000.0, 1) if min_vis_m is not None else None
    is_daytime = bool(max(is_day_list) > 0.5) if is_day_list else True

    return WeatherFacts(
        temperature_c=avg_temp,
        relative_humidity_pct=avg_humidity,
        precipitation_mm=tot_precip,
        precipitation_probability=max_precip_prob,
        wind_speed_kmh=max_wind,
        wind_gusts_kmh=max_gust,
        uv_index=max_uv,
        cloud_cover_pct=avg_cloud,
        visibility_km=vis_km,
        target_period=target_period,
        is_daytime=is_daytime,
        retrieved_at=datetime.now(dt_timezone.utc).isoformat()
    )


async def fetch_weather_facts(
    latitude: float,
    longitude: float,
    time_reference: str = "today",
    timezone: str = "auto",
    client: Optional[httpx.AsyncClient] = None
) -> WeatherFacts:
    """
    Retrieves live weather data from Open-Meteo Forecast API and normalizes
    it into trusted WeatherFacts for deterministic policy evaluation.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone or "auto",
        "wind_speed_unit": "kmh",
        "current": (
            "temperature_2m,relative_humidity_2m,precipitation,weather_code,"
            "cloud_cover,wind_speed_10m,wind_gusts_10m,uv_index,is_day"
        ),
        "hourly": (
            "temperature_2m,relative_humidity_2m,precipitation,precipitation_probability,"
            "wind_speed_10m,wind_gusts_10m,uv_index,cloud_cover,weather_code,visibility,is_day"
        )
    }

    url = settings.FORECAST_BASE_URL
    timeout = settings.OPEN_METEO_TIMEOUT_SECONDS
    max_retries = 1

    close_client_when_done = False
    if client is None:
        client = httpx.AsyncClient(timeout=timeout)
        close_client_when_done = True

    try:
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = await client.get(url, params=params)
                if response.status_code >= 500:
                    response.raise_for_status()

                if response.status_code != 200:
                    raise WeatherFetchError(
                        f"Open-Meteo API error: HTTP {response.status_code} - {response.text}"
                    )

                data = response.json()
                if not isinstance(data, dict):
                    raise WeatherDataValidationError("Malformed weather payload: root is not an object")

                current = data.get("current", {})
                hourly = data.get("hourly", {})

                # Check if specific time window (evening, afternoon, morning, tomorrow) requested
                cleaned_ref = time_reference.strip().lower()
                time_strings = hourly.get("time", [])

                needs_hourly_window = any(
                    k in cleaned_ref for k in ["evening", "night", "afternoon", "morning", "tomorrow"]
                )

                if needs_hourly_window and time_strings:
                    indices = _extract_window_indices(time_strings, cleaned_ref)
                    if indices:
                        logger.info(
                            f"Aggregated {len(indices)} hourly intervals for '{cleaned_ref}' at ({latitude}, {longitude})"
                        )
                        return _aggregate_hourly_window(hourly, indices, target_period=cleaned_ref)

                # Default: Use current observations + closest hourly precipitation probability
                precip_probs = hourly.get("precipitation_probability", [])
                curr_prob = int(precip_probs[0]) if precip_probs and precip_probs[0] is not None else None

                vis_list = hourly.get("visibility", [])
                curr_vis_m = vis_list[0] if vis_list and vis_list[0] is not None else None
                curr_vis_km = round(curr_vis_m / 1000.0, 1) if curr_vis_m is not None else None

                temp = current.get("temperature_2m")
                wind = current.get("wind_speed_10m")
                gusts = current.get("wind_gusts_10m")
                precip = current.get("precipitation", 0.0)
                uv = current.get("uv_index")
                humidity = current.get("relative_humidity_2m")
                clouds = current.get("cloud_cover")
                w_code = current.get("weather_code")
                is_day = bool(current.get("is_day", 1) == 1)

                facts = WeatherFacts(
                    temperature_c=float(temp) if temp is not None else None,
                    relative_humidity_pct=int(humidity) if humidity is not None else None,
                    precipitation_mm=float(precip) if precip is not None else 0.0,
                    precipitation_probability=curr_prob,
                    wind_speed_kmh=float(wind) if wind is not None else None,
                    wind_gusts_kmh=float(gusts) if gusts is not None else None,
                    uv_index=float(uv) if uv is not None else None,
                    cloud_cover_pct=int(clouds) if clouds is not None else None,
                    weather_code=int(w_code) if w_code is not None else None,
                    visibility_km=curr_vis_km,
                    target_period="current" if cleaned_ref in ["now", "current"] else cleaned_ref,
                    is_daytime=is_day,
                    retrieved_at=datetime.now(dt_timezone.utc).isoformat()
                )
                return facts

            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(
                        f"Weather call for ({latitude}, {longitude}) failed (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying..."
                    )
                    continue
                else:
                    raise WeatherFetchError(
                        f"Weather API unavailable after {max_retries + 1} attempts: {e}"
                    ) from e

        raise WeatherFetchError(f"Weather fetch failed: {last_error}")

    finally:
        if close_client_when_done:
            await client.aclose()
