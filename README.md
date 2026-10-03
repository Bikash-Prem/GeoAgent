# GeoAgentic

## Emergency Decision Intelligence Platform

GeoAgentic is a local-first emergency decision intelligence control plane. It maintains a grounded situation state from fleet, telemetry and incident data; obtains real-road route candidates from a routing provider; evaluates ETA, route risk, uncertainty and fleet consequences; compares counterfactual actions; records the recommendation and evidence; and leaves the final action to a dispatcher.

> **Core question:** Given everything happening right now, what should we do next — and why?

This repository is intentionally human-in-the-loop. It does not claim autonomous emergency authority, trained medical models, validated accident detection, RL performance, or real-world response-time improvements.

## Current product flow

```text
REAL WORLD / LOCAL STATE
        │
        ├── Fleet / GPS / Traccar
        ├── Incident registry
        └── Traffic provider / telemetry
        │
        ▼
SITUATION ENGINE
        │  evidence + diagnosis + freshness
        ▼
ROUTING PROVIDER
        │  Google Routes (primary) / Mapbox / local fallback
        ▼
PREDICTION + ROUTE RISK
        │  ETA interval + incident proximity + delay probability
        ▼
COUNTERFACTUAL ACTION ENGINE
        │  continue / reroute / backup / combined
        ▼
POLICY ENGINE
        │  deterministic safety-first baseline
        ▼
DECISION TRACE
        │  evidence / provider / actions / model-policy versions
        ▼
DISPATCHER
        │  approve / reject
        ▼
OUTCOME + FEEDBACK
```

## Important routing decision

The production decision path **does not use the toy A→H A* graph**. Real-road routing is provider-backed.

### Google Routes API

Set:

```env
ROUTING_PROVIDER=google
GOOGLE_ROUTES_API_KEY=your_key
GOOGLE_ROUTING_PREFERENCE=TRAFFIC_AWARE
```

GeoAgentic calls Google Routes `ComputeRoutes` with traffic-aware driving routes and alternative routes. The returned distance, duration and encoded polyline are normalized into the internal `RoutingProvider` contract. The decision layer then evaluates those routes for emergency-specific risk and fleet consequences. Google documents up to three route results when alternatives are requested and requires a response field mask. See the official [Routes API documentation](https://developers.google.com/maps/documentation/routes/reference/rpc).

`TRAFFIC_AWARE_OPTIMAL` can be selected later when higher routing quality is worth its additional latency/cost trade-off. The default local configuration uses `TRAFFIC_AWARE`.

### Why the custom A* code still exists

`backend/app/algorithms/astar.py` is retained as a deterministic algorithmic/research component and test fixture. Its heuristic is now zero because the demo graph's edge weights are arbitrary operational costs, so a geographic-distance heuristic cannot be proven admissible. It is **not** the operational road-routing source.

## Product UI

The frontend is an operational control plane rather than a marketing landing page:

- **Command Center** — active emergency, live fleet, incidents, provider status and map.
- **Situation Room** — evidence, diagnosis, confidence and decision pipeline.
- **Decision Studio** — route alternatives, ETA, risk, uncertainty, reasoning and human approval.
- **What-If Lab** — deterministic counterfactual scenarios without mutating live state.
- **Fleet Intelligence** — fleet state and backup/coverage consequences.
- **Emergency Replay** — live local control-loop snapshots and replay controls.
- **Analytics** — recorded operational events and decision counts.
- **Decision & AI Audit** — persisted evidence, actions, provider status and human decisions.

The map uses real latitude/longitude coordinates. It does not project Bangalore data into another city or fabricate nearby vehicles/signals.

## Provider architecture

Providers are behind explicit contracts so the decision engine is independent of vendors:

```text
RoutingProvider
  ├── GoogleRoutesProvider
  ├── MapboxRoutingProvider
  └── FallbackRoutingProvider

TrafficProvider
  ├── TomTomTrafficProvider
  └── FallbackTrafficProvider

FleetProvider
  ├── TraccarFleetProvider
  └── FallbackFleetProvider
```

Provider failures are represented as structured availability/staleness status. A fallback is explicitly labelled as fallback and is not presented as live traffic or live routing.

## Fleet / Traccar

For live fleet positions:

```env
FLEET_PROVIDER=traccar
FLEET_API_URL=https://your-traccar-host
FLEET_API_USERNAME=...
FLEET_API_PASSWORD=...
```

The Traccar adapter reads `/api/positions` and normalizes device position, speed, course and status into the internal fleet contract.

## Decision trace

A generated decision records:

- situation snapshot
- evidence items and their sources
- routing provider observation
- route candidates
- ETA prediction metadata
- route risk and delay probability
- action evaluations
- fleet coverage impact
- selected policy/version
- recommendation and reasoning
- human approval/rejection
- outcome/feedback events

GET recommendation access is read-only. Decision generation happens through the explicit analysis endpoint, so a dashboard refresh does not silently create another decision record.

## Simulation

The What-If Lab supports deterministic synthetic counterfactuals:

- `accident_congestion`
- `road_closure`
- `traffic_spike`
- `competing_emergencies`

A simulation does not mutate the live fleet/incident database. It records the baseline decision and a scenario-specific counterfactual score. Synthetic simulation values are explicitly marked as synthetic.

## API

### Core

```text
GET  /api/health
GET  /api/ready
GET  /api/vehicles
GET  /api/incidents
GET  /api/recommendations/{vehicle_id}       # read-only latest decision
GET  /api/audit
```

### Decision intelligence

```text
GET  /api/v1/situations/{vehicle_id}
POST /api/v1/vehicles/{vehicle_id}/telemetry
POST /api/v1/routes/generate
POST /api/v1/actions/generate
POST /api/v1/actions/evaluate
POST /api/v1/decisions/analyze
GET  /api/v1/decisions/{decision_id}
GET  /api/v1/decisions/{decision_id}/trace
POST /api/v1/decisions/{decision_id}/approve
POST /api/v1/decisions/{decision_id}/reject
POST /api/v1/decisions/{decision_id}/outcome
GET  /api/v1/decisions/{decision_id}/feedback
```

### Simulation / live state

```text
GET  /api/v1/simulation/scenarios
POST /api/v1/simulation/run
GET  /api/v1/twin/snapshot
GET  /api/v1/twin/providers
POST /api/v1/twin/command
WS   /ws/twin
WS   /ws/telemetry
```

`/ws/telemetry` is now a read-only fleet stream. It does not generate random GPS points or write synthetic observations into the database.

## Local setup

Prerequisites:

- Python 3.12+ (3.13 is fine)
- Node.js 20+
- npm
- optional Docker Desktop

```powershell
Copy-Item .env.example .env
python -m pip install -r backend/requirements.txt
python -m pip install -r backend/requirements-dev.txt
Push-Location frontend
npm install
Pop-Location
```

For local SQLite development, leave `DATABASE_URL` empty or set:

```env
DATABASE_URL=sqlite:///./geoagentic.db
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ORIGINS=http://localhost:5173
```

Start the API:

```powershell
Push-Location backend
$env:PYTHONPATH='.'
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Pop-Location
```

Start the frontend in another terminal:

```powershell
Push-Location frontend
npm run dev
Pop-Location
```

Open `http://localhost:5173`.

Without provider credentials, the application remains runnable using explicit local fallbacks. For real-road route candidates, configure Google Routes or Mapbox. For real fleet telemetry, configure Traccar.

## Docker

`docker compose up --build` starts PostgreSQL, the API and the nginx-served frontend. The frontend is exposed at port `5173` and the API at `8000`.

Vite variables are supplied as Docker build arguments because they are frontend build-time configuration, not runtime nginx environment variables.

## Environment

```env
POSTGRES_DB=geoagentic
POSTGRES_USER=geoagentic
POSTGRES_PASSWORD=geoagentic
DATABASE_URL=
CORS_ORIGINS=http://localhost:5173
ALLOWED_HOSTS=localhost,127.0.0.1
API_KEY=
ENVIRONMENT=development
DOCS_ENABLED=true

ROUTING_PROVIDER=google
GOOGLE_ROUTES_API_KEY=
GOOGLE_ROUTING_PREFERENCE=TRAFFIC_AWARE
DESTINATION_LAT=12.9719
DESTINATION_LON=77.6072

MAPBOX_ACCESS_TOKEN=
TRAFFIC_PROVIDER=local
TOMTOM_API_KEY=
FLEET_PROVIDER=local
FLEET_API_URL=
FLEET_API_USERNAME=
FLEET_API_PASSWORD=
PROVIDER_TIMEOUT_SECONDS=5
TWIN_TICK_HZ=0.2
```

The seeded coordinates and incidents are **demo data**. They must not be represented as a live emergency feed.

## Testing

Backend tests can be run without external providers:

```powershell
Push-Location backend
$env:PYTHONPATH='.'
python -m pytest -q
Pop-Location
```

The suite covers:

- optimality of the deterministic A* fixture
- distinct K-route generation
- counterfactual action generation
- policy selection
- provider fallback behaviour
- Google Routes response normalization

Frontend type checking:

```powershell
Push-Location frontend
npx tsc --noEmit
Pop-Location
```

A production build requires a normal platform-specific `npm install`; the repository intentionally does not depend on the shipped Windows/Linux `node_modules` directory.

## ML / DL / RL status

Current decision path:

- transparent heuristic ETA baseline
- deterministic evidence fusion
- provider-backed route candidates
- incident-proximity route risk
- uncertainty interval
- deterministic counterfactual evaluation
- rule-based safety-first policy

There is **no fake trained ML/RL model** in the operational path. Trained ETA forecasting, causal traffic prediction, computer-vision road evidence, RL/optimization dispatch policies and calibration studies remain future research layers behind the existing service interfaces.

## Design principle

GeoAgentic is not trying to replace Google Maps, Traccar or a dispatcher.

It sits above those systems:

> **Observe → Diagnose → Predict → Generate Actions → Evaluate Counterfactuals → Recommend → Explain → Human Decision → Learn from Outcome**

That is the product boundary.


## Local Emergency Operations Features

The local control plane includes five operator-facing emergency features:

- **Smart Green Corridor:** route-linked signal-priority simulation with animated green corridor geometry and intersection status. The current local controller is explicitly synthetic; it does not claim to control physical traffic lights.
- **AI Voice Emergency Assistant:** browser-native `SpeechSynthesis` announcements with a 30-second message deduplication window and a header toggle.
- **Live Mumbai Map:** CARTO Dark Matter basemap, Mumbai boundary overlay, animated ambulance movement, fleet markers, incidents, hospitals, signal markers, route alternatives and emergency/corridor overlays.
- **Smart Hospital Alerts:** immediate dispatch alert plus an en-route alert workflow; hospital readiness exposes ICU, ER, oxygen and trauma status. Local hospital capacity is deterministic synthetic demo data.
- **AI Dispatch Engine:** nearest available ambulance + hospital selection, response estimate, survival-response model simulation and dispatch-confidence estimate. These local values are explicitly labelled as a deterministic decision-model simulation, not a trained clinical/neural model.

These features are intended for the local company-ready demonstration/control plane. Physical traffic-signal control, real hospital integration, and clinical survival prediction require authenticated external systems and validation before any real-world deployment.

## Mountain Air Rescue

The local control plane now includes a dedicated **Mountain Air Rescue Desk** for emergencies where altitude, terrain and constrained road access make a ground-only response insufficient.

The local simulation evaluates:

- Himalayan response regions: Himachal Pradesh, Uttarakhand and Ladakh
- air-ambulance availability, crew, fuel and range
- incident altitude and terrain risk
- wind, visibility and cloud-base conditions
- primary and alternate landing-zone feasibility
- trauma-hospital helipad and ICU readiness
- flight ETA and landing feasibility
- explicit operational constraints and human-review status

The interface provides a mountain situation map, flight path, landing zones, trauma destination and an **Execute AI Air Rescue** control. Aviation values are simulation data; this module does not control aircraft, air traffic or real helipads.

## Home page hero

The command-center home view uses the supplied ambulance image as the primary emergency-response visual and links the urban ground-response workflow directly to the Mountain Air Rescue Desk.
