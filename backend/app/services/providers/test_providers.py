import unittest

from app.services.providers.adapters import FallbackFleetProvider, FallbackRoutingProvider, FallbackTrafficProvider


class ProviderFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_providers_are_available_without_credentials(self):
        routing = await FallbackRoutingProvider().routes((12.9, 77.5), (12.95, 77.6))
        traffic = await FallbackTrafficProvider().traffic(12.9, 77.5)
        fleet = await FallbackFleetProvider().vehicles()
        self.assertEqual("fallback", routing.status.mode)
        self.assertTrue(traffic.status.available)
        self.assertEqual("fallback", fleet.status.mode)


if __name__ == "__main__":
    unittest.main()
class GoogleRoutesAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_google_route_response_is_normalized(self):
        from unittest.mock import AsyncMock, patch
        from app.services.providers.adapters import GoogleRoutesProvider

        response = AsyncMock()
        response.raise_for_status = lambda: None
        response.json = lambda: {
            "routes": [{
                "distanceMeters": 2400,
                "duration": "120s",
                "staticDuration": "100s",
                "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
                "description": "Primary route",
            }]
        }

        client = AsyncMock()
        client.post.return_value = response
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False
        with patch("httpx.AsyncClient", return_value=client):
            result = await GoogleRoutesProvider("test-key").routes((37.0, -122.0), (37.1, -122.1))

        self.assertTrue(result.status.available)
        self.assertEqual(result.provider, "google")
        self.assertEqual(result.routes[0]["eta_min"], 2.0)
        self.assertEqual(result.routes[0]["distance_km"], 2.4)
        self.assertTrue(result.routes[0]["points"])
