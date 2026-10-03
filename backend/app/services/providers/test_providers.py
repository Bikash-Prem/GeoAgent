import unittest
from unittest.mock import AsyncMock, patch

from app.services.providers.adapters import (FallbackFleetProvider, FallbackRoutingProvider, FallbackTrafficProvider, GoogleRoutesProvider,
                                             TraccarFleetProvider, normalize_tomtom_incidents)


def _client(json_payload, method="post"):
    response = AsyncMock()
    response.raise_for_status = lambda: None
    response.json = lambda: json_payload
    client = AsyncMock()
    getattr(client, method).return_value = response
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    return client


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_providers_are_available_without_credentials(self):
        routing = await FallbackRoutingProvider().routes((12.9, 77.5), (12.95, 77.6))
        self.assertEqual("fallback", routing.status.mode)
        self.assertTrue((await FallbackTrafficProvider().traffic(12.9, 77.5)).status.available)
        self.assertEqual("fallback", (await FallbackFleetProvider().vehicles()).status.mode)

    async def test_google_route_response_is_normalized(self):
        payload = {"routes": [{"distanceMeters": 2400, "duration": "120s", "staticDuration": "100s",
                               "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"}, "description": "Primary route"}]}
        with patch("httpx.AsyncClient", return_value=_client(payload)):
            result = await GoogleRoutesProvider("test-key").routes((37.0, -122.0), (37.1, -122.1))
        self.assertTrue(result.status.available)
        self.assertEqual(result.routes[0]["eta_min"], 2.0)
        self.assertEqual(result.routes[0]["distance_km"], 2.4)
        self.assertAlmostEqual(result.routes[0]["points"][0]["lat"], 38.5)

    async def test_traccar_positions_keep_device_id_and_convert_knots(self):
        payload = [{"deviceId": 12, "latitude": 12.97, "longitude": 77.6, "speed": 10, "course": 90, "fixTime": "2026-10-03T10:00:00Z"}]
        with patch("httpx.AsyncClient", return_value=_client(payload, "get")):
            obs = await TraccarFleetProvider("https://traccar.example").vehicles()
        self.assertEqual(obs.vehicles[0]["device_id"], "12")
        self.assertEqual(obs.vehicles[0]["speed_kmh"], 18.5)

    def test_tomtom_incidents_map_to_registry_kinds(self):
        payload = {"incidents": [
            {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[77.60, 12.97], [77.602, 12.971]]},
             "properties": {"id": "abc", "iconCategory": 8, "magnitudeOfDelay": 4, "events": [{"description": "Road closed"}]}},
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [77.59, 12.96]},
             "properties": {"id": "def", "iconCategory": 1, "magnitudeOfDelay": 2, "events": [{"description": "Accident"}]}},
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [77.5, 12.9]}, "properties": {"id": "x", "iconCategory": 2}},  # fog: ignored
        ]}
        rows = normalize_tomtom_incidents(payload)
        self.assertEqual([r["kind"] for r in rows], ["closure", "accident"])
        self.assertEqual(rows[0]["severity"], "high")
        self.assertTrue(80 <= rows[0]["radius_m"] <= 600)


if __name__ == "__main__":
    unittest.main()
