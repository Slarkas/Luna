import json
import urllib
import unittest
from unittest.mock import patch

from app.tools.weather import WeatherClient, WeatherError, CityNotFoundError


class _MockResponse:
    """Minimal stand-in for urllib.response.HTTPResponse."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body


class _TransportStub:
    """Stand-in for urllib.request.urlopen that replays canned bodies."""

    def __init__(self, *bodies: bytes, error: BaseException | None = None) -> None:
        self._bodies = list(bodies)
        self._error = error
        self.calls: list = []

    def __call__(self, request, **kwargs):
        self.calls.append((request, kwargs))
        if self._error:
            raise self._error
        return _ResponseStub(self._bodies.pop(0) if self._bodies else b"")


class _ResponseStub:
    """Minimal stand-in for the file-like object urlopen returns."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body


class WeatherClientTest(unittest.TestCase):
    """Tests for ``WeatherClient``."""

    def setUp(self) -> None:
        self.client = WeatherClient(timeout=5)

    def test_get_weather_unknown_city(self) -> None:
        """Raise CityNotFoundError when the city is not found."""

        geocoding_body = json.dumps(
            {"results": [], "status": "no_results"}
        ).encode("utf-8")

        with patch(
            "app.tools.weather.urllib.request.urlopen",
            side_effect=_TransportStub(geocoding_body),
        ):
            with self.assertRaises(CityNotFoundError):
                self.client.get_weather("NowhereCity")

    def test_get_weather_kaunas_success(self) -> None:
        """Retrieve current weather for Kaunas, Lithuania."""

        geocoding_body = json.dumps(
            {
                "results": [
                    {
                        "name": "Kaunas",
                        "latitude": 54.90,
                        "longitude": 23.90,
                        "country": "LT",
                    }
                ],
                "count": 1,
                "status": "ok",
            }
        ).encode("utf-8")

        forecast_body = json.dumps(
            {
                "latitude": 54.9,
                "longitude": 23.9,
                "generationtime_ms": 0.123,
                "utc_offset_seconds": 3600,
                "timezone": "BST",
                "timezone_abbreviation": "BST",
                "current_weather": {
                    "temperature": 18.5,
                    "windspeed": 3.6,
                    "winddirection": 210,
                    "weathercode": 3,
                    "time": "2024-06-15T14:00",
                    "relativehumidity_2m": 65,
                    "apparent_temperature": 17.2,
                },
            }
        ).encode("utf-8")

        with patch(
            "app.tools.weather.urllib.request.urlopen",
            side_effect=_TransportStub(geocoding_body, forecast_body),
        ):
            result = self.client.get_weather("Kaunas")

        self.assertEqual(result["city"], "Kaunas")
        self.assertEqual(result["country"], "LT")
        self.assertEqual(result["units"], "metric")
        self.assertEqual(result["temperature"], 18.5)
        self.assertEqual(result["weather_code"], 3)
        self.assertEqual(result["wind_speed"], 3.6)
        self.assertEqual(result["observation_time"], "2024-06-15T14:00")
        self.assertEqual(result["apparent_temperature"], 17.2)
        self.assertEqual(result["humidity"], 65)

    def test_get_weather_network_error(self) -> None:
        """Raise WeatherError on network failure."""

        with patch(
            "app.tools.weather.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            with self.assertRaises(WeatherError):
                self.client.get_weather("Kaunas")

    def test_get_weather_timeout(self) -> None:
        """Raise WeatherError on request timeout."""

        class _TimeoutError(TimeoutError):
            pass

        with patch(
            "app.tools.weather.urllib.request.urlopen",
            side_effect=_TimeoutError("timed out"),
        ):
            with self.assertRaises(WeatherError):
                self.client.get_weather("Kaunas")

    def test_get_weather_http_error(self) -> None:
        """Raise WeatherError on HTTP 404 / bad response."""

        geocoding_body = b'{"error": "not found"}'

        with patch(
            "app.tools.weather.urllib.request.urlopen",
            side_effect=_TransportStub(geocoding_body),
        ):
            with self.assertRaises(WeatherError):
                self.client.get_weather("Kaunas")

    def test_get_weather_invalid_json(self) -> None:
        """Raise WeatherError when API returns non-JSON response."""

        with patch(
            "app.tools.weather.urllib.request.urlopen",
            side_effect=_TransportStub(b"Not valid json{"),
        ):
            with self.assertRaises(WeatherError):
                self.client.get_weather("Kaunas")

    def test_get_weather_no_current_weather_key(self) -> None:
        """Raise WeatherError when current_weather key is missing."""

        geocoding_body = json.dumps(
            {"results": [{"name": "Kaunas", "latitude": 54.9, "longitude": 23.9, "country": "LT"}]}
        ).encode("utf-8")

        forecast_body = json.dumps({"latitude": 54.9, "longitude": 23.9}).encode("utf-8")

        with patch(
            "app.tools.weather.urllib.request.urlopen",
            side_effect=_TransportStub(geocoding_body, forecast_body),
        ):
            with self.assertRaises(WeatherError):
                self.client.get_weather("Kaunas")

    def test_get_weather_empty_results(self) -> None:
        """Raise CityNotFoundError when geocoding returns no results."""

        geocoding_body = json.dumps({"results": [], "status": "ok"}).encode("utf-8")

        with patch(
            "app.tools.weather.urllib.request.urlopen",
            side_effect=_TransportStub(geocoding_body),
        ):
            with self.assertRaises(CityNotFoundError):
                self.client.get_weather("InventedCity12345")

    def test_get_weather_main_and_unit(self) -> None:
        """Verify the full structure of the returned weather dict."""

        geocoding_body = json.dumps(
            {
                "results": [
                    {
                        "name": "London",
                        "latitude": 51.5,
                        "longitude": -0.12,
                        "country": "GB",
                    }
                ],
                "count": 1,
                "status": "ok",
            }
        ).encode("utf-8")

        forecast_body = json.dumps(
            {
                "latitude": 51.5,
                "longitude": -0.1,
                "generationtime_ms": 0.1,
                "utc_offset_seconds": 0,
                "timezone": "UTC",
                "current_weather": {
                    "temperature": 22.0,
                    "windspeed": 5.0,
                    "winddirection": 180,
                    "weathercode": 0,
                    "time": "2024-07-20T12:00",
                    "relativehumidity_2m": 55,
                    "apparent_temperature": 23.5,
                },
            }
        ).encode("utf-8")

        with patch(
            "app.tools.weather.urllib.request.urlopen",
            side_effect=_TransportStub(geocoding_body, forecast_body),
        ):
            result = self.client.get_weather("London")

        expected_keys = {
            "city",
            "country",
            "units",
            "temperature",
            "apparent_temperature",
            "humidity",
            "wind_speed",
            "weather_code",
            "observation_time",
        }
        self.assertEqual(set(result.keys()), expected_keys)
        self.assertEqual(result["city"], "London")
        self.assertEqual(result["country"], "GB")
        self.assertEqual(result["units"], "metric")
        self.assertEqual(result["temperature"], 22.0)
        self.assertEqual(result["weather_code"], 0)
        self.assertEqual(result["wind_speed"], 5.0)
        self.assertEqual(result["observation_time"], "2024-07-20T12:00")
        self.assertEqual(result["apparent_temperature"], 23.5)
        self.assertEqual(result["humidity"], 55)

    def tearDown(self) -> None:
        pass


if __name__ == "__main__":
    unittest.main()