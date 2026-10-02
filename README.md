# GeoAgentic Emergency Response Copilot

A full-stack emergency vehicle routing and dispatch decision-support control plane.

## Stack
- Frontend: React + TypeScript + Vite + Leaflet
- Backend: FastAPI + SQLAlchemy 2 + PostgreSQL
- Real-time: WebSocket telemetry stream
- Algorithms: A* graph search, Yen-style K-shortest route candidates, grid-based spatial indexing
- Architecture: API → services → algorithms → persistence, with GeoAgent orchestration isolated from deterministic analytics

## What is implemented
- Live/replay ambulance tracking
- Incident and closure monitoring
- Route deviation detection
- Evidence-based cause inference
- ETA prediction with uncertainty
- A* candidate route generation and K-route alternatives
- Route scoring using ETA, incident risk and uncertainty
- Backup ambulance recommendation
- Dispatcher copilot with human approval actions
- Audit trail for recommendations and actions
- WebSocket live updates
- PostgreSQL persistence
- Seed/demo scenario

## Important scope
This is a decision-support prototype, not an autonomous emergency vehicle controller. Demo data is synthetic unless connected to real feeds. Metrics in the presentation are evaluation targets, not claimed measured results.

## Run
1. Copy `.env.example` to `.env` and replace the database password for any shared environment.
2. `docker compose up --build`
3. Open `http://localhost:5173`.
4. Readiness: `http://localhost:8000/api/ready`. API docs are disabled in production by default; set `DOCS_ENABLED=true` only on a protected development network.

## Production security
- Put the frontend and API behind a TLS reverse proxy or managed load balancer. Do not expose PostgreSQL to the public internet.
- Set `ALLOWED_HOSTS` and `CORS_ORIGINS` to exact production hostnames; never use `*` with credentials.
- Set `API_KEY` for non-browser clients and protect it in a secret manager. Browser-exposed keys are identifiers, not secrets.
- Keep the database on a private network, use a strong password, encrypt backups, and restrict inbound traffic to the API/database ports.
- The API emits request IDs and security headers, validates action payloads, limits allowed methods/headers, and records immutable action/recommendation audit events.
- For internet-scale traffic, place rate limiting and WAF rules at the edge and run multiple API replicas behind the proxy; the in-process demo stream is intentionally not a distributed telemetry broker.

The seeded scenario is available immediately. The backend falls back to demo data for the UI if the database is empty.

## Complexity notes
- A*: O((V + E) log V) with a binary heap; memory O(V).
- K route candidates: approximately O(K · V log V) for the bounded demo implementation.
- Spatial grid lookup: expected O(1 + c) for a local cell neighborhood, where c is the number of objects in nearby cells.
- Route scoring: O(K) after candidate generation.
- Telemetry deviation check: O(1) for the latest vehicle state plus O(log V) for nearest-grid-cell lookup.

The design deliberately keeps expensive graph/GIS operations in deterministic services and uses the GeoAgent layer for orchestration, evidence fusion and explanation.
