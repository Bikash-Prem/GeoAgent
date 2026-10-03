# GeoAgentic Architecture

```text
                       REAL-WORLD / LOCAL STATE
             ┌──────────────┬───────────────┬──────────────┐
             │              │               │              │
          Fleet/GPS      Incidents       Traffic        Telemetry
             │              │               │              │
             └──────────────┴───────┬───────┴──────────────┘
                                    ▼
                         ┌───────────────────┐
                         │  SITUATION ENGINE  │
                         │ evidence / cause   │
                         │ freshness / fleet  │
                         └─────────┬─────────┘
                                   ▼
                         ┌───────────────────┐
                         │ ROUTING PROVIDER  │
                         │ Google / Mapbox /  │
                         │ explicit fallback  │
                         └─────────┬─────────┘
                                   ▼
                         ┌───────────────────┐
                         │ PREDICTION + RISK │
                         │ ETA / interval    │
                         │ incident proximity│
                         │ delay probability  │
                         └─────────┬─────────┘
                                   ▼
                         ┌───────────────────┐
                         │ COUNTERFACTUAL    │
                         │ continue          │
                         │ reroute           │
                         │ backup            │
                         │ combined          │
                         └─────────┬─────────┘
                                   ▼
                         ┌───────────────────┐
                         │ POLICY ENGINE     │
                         │ deterministic     │
                         │ safety-first      │
                         └─────────┬─────────┘
                                   ▼
                         ┌───────────────────┐
                         │ DECISION TRACE    │
                         │ evidence/provider │
                         │ actions/policy    │
                         └─────────┬─────────┘
                                   ▼
                           HUMAN DISPATCHER
                             │          │
                         approve      reject
                             │          │
                             └────┬─────┘
                                  ▼
                           OUTCOME / FEEDBACK
```

## Routing boundary

Google Routes is the primary production routing provider when `ROUTING_PROVIDER=google` and `GOOGLE_ROUTES_API_KEY` is configured. The adapter requests traffic-aware driving routes and alternatives and normalizes them to `RouteObservation`.

The decision engine never assumes that the routing provider is the decision-maker. Provider output becomes evidence for GeoAgentic's emergency-specific evaluation.

The custom A* implementation remains a deterministic algorithm fixture only. It is not used for the real-road decision path.

## Provider contracts

`backend/app/services/providers/contracts.py` defines:

- `RoutingProvider`
- `TrafficProvider`
- `FleetProvider`
- `ProviderStatus`
- normalized observations

Adapters live in `backend/app/services/providers/adapters.py`.

## Decision persistence

An explicit `POST /api/v1/decisions/analyze` creates a decision record and associated situation/evidence/action/prediction/trace rows. GET recommendation access is read-only.

The TwinLoop uses `analyze_async(..., persist=False)` so its periodic snapshots do not create an unbounded stream of decision records.

## Human control

Approval and rejection are explicit API operations. The system records the actor, selected action and comment as a trace event. Outcome recording is separate from approval so predicted vs actual values can be evaluated later.

## Simulation

Simulation operates on a synthetic counterfactual copy and does not mutate live fleet/incident state. Scenario values are labelled synthetic.

## Frontend

The React frontend is organized around the operational story:

1. Command Center — what is happening?
2. Situation Room — why is it happening?
3. Decision Studio — what can we do?
4. What-If Lab — what happens if we do it?
5. Fleet Intelligence — what happens to resources?
6. Emergency Replay — how does the situation evolve?
7. Analytics — did it work?
8. Audit — why was the decision made?
