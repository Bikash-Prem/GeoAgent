from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    mode: str
    available: bool
    stale: bool = False
    message: str | None = None
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class RouteObservation:
    provider: str
    routes: list[dict[str, Any]]
    status: ProviderStatus


@dataclass(frozen=True)
class TrafficObservation:
    provider: str
    traffic: dict[str, Any]
    status: ProviderStatus


@dataclass(frozen=True)
class FleetObservation:
    provider: str
    vehicles: list[dict[str, Any]]
    status: ProviderStatus


class RoutingProvider(Protocol):
    async def routes(self, origin: tuple[float, float], destination: tuple[float, float]) -> RouteObservation: ...


class TrafficProvider(Protocol):
    async def traffic(self, latitude: float, longitude: float) -> TrafficObservation: ...


class FleetProvider(Protocol):
    async def vehicles(self) -> FleetObservation: ...