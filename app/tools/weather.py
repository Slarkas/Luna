"""Luna's weather client using Open-Meteo API.

Retrieves current weather for a city using:
- Open-Meteo Geocoding API to resolve city name to coordinates
- Open-Meteo Forecast API to get current weather data

Uses only Python standard library (urllib, json).
Handles errors gracefully (unknown cities, network failures, timeouts,
invalid API responses). Uses a finite request timeout.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

# Open-Meteo API endpoints
GEOCODING_API_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_API_URL = "https://api.open-meteo.com/v1/forecast"

# Default timeout for HTTP requests (seconds)
DEFAULT_TIMEOUT = 10


class WeatherError(Exception):
    """Base class for weather client errors."""


class CityNotFoundError(WeatherError):
    """Raised when a city cannot be found in the geocoding API."""


class WeatherClient:
    """Client for fetching weather data from Open-Meteo."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    def _urlopen(self, request, timeout: int | None = None):
        """urllib.request.urlopen with timeout handling.

        Returns the response body as bytes, or raises WeatherError on failure.
        """
        timeout = timeout or self.timeout
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise WeatherError(
                f"HTTP error {e.code}: {body[:200]}"
            ) from e
        except urllib.error.URLError as e:
            raise WeatherError(f"Network error: {e.reason}") from e
        except TimeoutError as e:
            raise WeatherError(f"Request timed out after {timeout}s") from e

    def _get_json(self, url: str, timeout: int | None = None) -> dict:
        """Fetch and parse JSON from a URL.

        Returns the parsed JSON dict, or raises WeatherError on failure.
        """
        req = urllib.request.Request(url, method="GET")
        resp = self._urlopen(req, timeout=timeout)
        try:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
        except json.JSONDecodeError as e:
            raise WeatherError(f"Invalid JSON response from {url}") from e

    def _resolve_city(self, city: str) -> tuple[float, float, str]:
        """Resolve a city name to latitude, longitude, and country using
        the Open-Meteo Geocoding API.

        Returns (latitude, longitude, country_code).

        Raises CityNotFoundError if the city is not found.
        """
        params = f"?name={urllib.parse.quote(city)}&count=1&language=en&format=json"
        url = f"{GEOCODING_API_URL}{params}"
        data = self._get_json(url)

        if not data.get("results"):
            raise CityNotFoundError(f"City '{city}' not found")

        result = data["results"][0]
        lat = float(result["latitude"])
        lon = float(result["longitude"])
        country = result.get("country", "")

        return lat, lon, country

    def get_weather(self, city: str) -> dict:
        """Get current weather for a city.

        Returns a dict with the following keys:
            - city: the requested city name
            - country: ISO 3166-1 alpha-2 country code
            - units: "metric" (Celsius, m/s) or "imperial" (Fahrenheit, mph)
            - temperature: current temperature
            - apparent_temperature: "feels like" temperature
            - humidity: relative humidity %
            - wind_speed: wind speed
            - weather_code: Open-Meteo weather condition code
            - observation_time: timestamp of the observation

        Raises WeatherError on network or API failures.
        Raises CityNotFoundError if the city cannot be resolved.
        """
        # Step 1: Resolve city to coordinates and country
        lat, lon, country = self._resolve_city(city)

        # Step 2: Fetch current weather from Open-Meteo Forecast API
        params = (
            f"?latitude={lat}&longitude={lon}"
            f"&current_weather=true"
            f"&timezone=auto"
            f"&relativehumidity_2m=true"
            f"&apparent_temperature=true"
        )
        url = f"{FORECAST_API_URL}{params}"
        data = self._get_json(url)

        # Step 3: Extract current weather data
        current = data.get("current_weather", {})
        if not current:
            raise WeatherError("No current_weather data in API response")

        temperature = current.get("temperature")
        weather_code = current.get("weathercode")
        wind_speed = current.get("windspeed")
        observation_time = current.get("time")
        humidity = current.get("relativehumidity_2m")
        apparent_temperature = current.get("apparent_temperature")

        # Use metric units by default
        units = "metric"

        return {
            "city": city,
            "country": country,
            "units": units,
            "temperature": temperature,
            "apparent_temperature": apparent_temperature,
            "humidity": humidity,
            "wind_speed": wind_speed,
            "weather_code": weather_code,
            "observation_time": observation_time,
        }