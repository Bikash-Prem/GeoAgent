# System Design

## Request path
React dashboard → FastAPI API → service layer → deterministic analytics / GeoAgent orchestration → PostgreSQL.

## Responsibilities
- **React:** presentation, map rendering, dispatcher interaction, WebSocket state.
- **FastAPI:** HTTP/WebSocket transport and validation.
- **Services:** use-case orchestration and evidence fusion.
- **Algorithms:** A*, bounded K-route generation, spatial indexing. No LLM is required for correctness of routing.
- **PostgreSQL:** vehicles, incidents, telemetry and immutable audit events.
- **GeoAgent:** in a production deployment, this layer would select tools and translate structured evidence into natural-language explanations. The prototype keeps the route and safety calculations deterministic.

## Data model
`vehicles` → current operational state.
`incidents` → active hazards and road events.
`telemetry` → append-only vehicle positions.
`audit_events` → recommendation/action trace for review.

## DSA choices
1. **A*** with binary heap: efficient shortest path on sparse road graphs.
2. **K candidate routes:** bounded alternative generation avoids enumerating all simple paths.
3. **SpatialGrid:** indexes nearby incidents/objects without scanning the entire city dataset.
4. **Route scoring:** linear in the number of candidates after route generation.

## Production evolution
- PostGIS for spatial queries and road geometry.
- Redis Streams/Kafka for high-rate telemetry.
- TimescaleDB or partitioned telemetry tables for large historical data.
- Celery/Arq/background workers for model inference.
- OSM/OSRM/GraphHopper or a routing provider for city-scale road networks.
- Model registry + feature store for ETA/traffic models.
- OIDC/RBAC, secret manager, TLS, structured logs and OpenTelemetry.
