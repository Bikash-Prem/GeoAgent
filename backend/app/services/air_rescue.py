from __future__ import annotations

from datetime import datetime, timezone
from math import hypot

# Deterministic mountain-rescue fixtures for the local product environment.
# These are explicitly simulation data: no real aviation dispatch or air-traffic control is performed.

REGIONS = {
    "himachal": {
        "name": "Himachal Pradesh",
        "incident": {"id": "MTN-HIM-01", "name": "Manali–Rohtang rescue", "lat": 32.2432, "lon": 77.1892, "altitude_m": 3_080, "severity": "critical", "details": "Vehicle rollover on a high-altitude mountain road; ground access constrained."},
        "landing_zones": [
            {"id": "LZ-HIM-01", "name": "Solang Valley LZ", "lat": 32.3157, "lon": 77.1553, "altitude_m": 2_560, "surface": "prepared", "status": "AVAILABLE", "capacity": "medium"},
            {"id": "LZ-HIM-02", "name": "Marhi Ridge LZ", "lat": 32.3721, "lon": 77.2472, "altitude_m": 3_330, "surface": "mountain clearing", "status": "CONDITIONAL", "capacity": "small"},
        ],
        "hospital": {"id": "AIR-HOSP-HIM", "name": "Regional Trauma Centre · Kullu", "lat": 31.9574, "lon": 77.1095, "helipad": "AVAILABLE", "trauma": "READY", "icu": 0.41},
        "weather": {"wind_kmh": 24, "visibility_km": 7.8, "cloud_base_m": 4_200, "temperature_c": 5, "status": "FLYABLE"},
        "terrain_risk": "HIGH",
    },
    "uttarakhand": {
        "name": "Uttarakhand",
        "incident": {"id": "MTN-UK-01", "name": "Kedarnath mountain rescue", "lat": 30.7352, "lon": 79.0669, "altitude_m": 3_580, "severity": "critical", "details": "Stranded casualty above a road-accessible corridor; helicopter extraction is being evaluated."},
        "landing_zones": [
            {"id": "LZ-UK-01", "name": "Guptkashi LZ", "lat": 30.5208, "lon": 79.0807, "altitude_m": 1_319, "surface": "prepared", "status": "AVAILABLE", "capacity": "medium"},
            {"id": "LZ-UK-02", "name": "Kedarnath Upper LZ", "lat": 30.7356, "lon": 79.0669, "altitude_m": 3_583, "surface": "restricted clearing", "status": "CONDITIONAL", "capacity": "small"},
        ],
        "hospital": {"id": "AIR-HOSP-UK", "name": "Regional Trauma Centre · Dehradun", "lat": 30.3165, "lon": 78.0322, "helipad": "AVAILABLE", "trauma": "READY", "icu": 0.47},
        "weather": {"wind_kmh": 31, "visibility_km": 5.1, "cloud_base_m": 4_050, "temperature_c": 3, "status": "CONDITIONAL"},
        "terrain_risk": "VERY HIGH",
    },
    "ladakh": {
        "name": "Ladakh",
        "incident": {"id": "MTN-LAD-01", "name": "Leh–Khardung La rescue", "lat": 34.2782, "lon": 77.5966, "altitude_m": 5_180, "severity": "critical", "details": "High-altitude casualty with no practical road response window; oxygen support is required."},
        "landing_zones": [
            {"id": "LZ-LAD-01", "name": "Leh Forward LZ", "lat": 34.1526, "lon": 77.5770, "altitude_m": 3_500, "surface": "prepared", "status": "AVAILABLE", "capacity": "medium"},
            {"id": "LZ-LAD-02", "name": "Khardung La Ridge", "lat": 34.2782, "lon": 77.5966, "altitude_m": 5_180, "surface": "high-altitude clearing", "status": "CONDITIONAL", "capacity": "small"},
        ],
        "hospital": {"id": "AIR-HOSP-LAD", "name": "SNM Hospital · Leh", "lat": 34.1526, "lon": 77.5770, "helipad": "AVAILABLE", "trauma": "LIMITED", "icu": 0.58},
        "weather": {"wind_kmh": 18, "visibility_km": 9.6, "cloud_base_m": 6_200, "temperature_c": -4, "status": "FLYABLE"},
        "terrain_risk": "EXTREME",
    },
}

AIR_AMBULANCES = [
    {"id": "AIR-01", "name": "Mountain Rescue 01", "base": "Kullu", "crew": "2 pilots + flight medic", "range_km": 420, "fuel_pct": 72, "available": True},
    {"id": "AIR-02", "name": "Mountain Rescue 02", "base": "Dehradun", "crew": "2 pilots + critical-care medic", "range_km": 510, "fuel_pct": 64, "available": True},
]


def _distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    return hypot((a[0] - b[0]) * 111.0, (a[1] - b[1]) * 101.0)


def build_air_rescue_plan(region: str = "himachal") -> dict:
    key = region.lower().strip()
    if key not in REGIONS:
        key = "himachal"
    data = REGIONS[key]
    incident = data["incident"]
    lz = data["landing_zones"]
    hospital = data["hospital"]
    weather = data["weather"]

    # Deterministic dispatch scoring: feasibility first, then distance/fuel.
    unit = next((x for x in AIR_AMBULANCES if x["available"]), AIR_AMBULANCES[0])
    target_lz = next((x for x in lz if x["status"] == "AVAILABLE"), lz[0])
    distance = _distance_km((incident["lat"], incident["lon"]), (target_lz["lat"], target_lz["lon"]))
    flight_eta = round(max(4.0, distance / 145.0 * 60.0 + 2.5), 1)
    altitude_penalty = max(0, incident["altitude_m"] - 3000) / 1000
    weather_penalty = max(0, weather["wind_kmh"] - 20) / 25
    feasibility = max(0.42, min(0.96, 0.91 - altitude_penalty * 0.08 - weather_penalty * 0.10))
    oxygen_required = incident["altitude_m"] >= 3000

    return {
        "region": key,
        "region_name": data["name"],
        "incident": incident,
        "air_ambulance": unit,
        "selected_landing_zone": target_lz,
        "alternate_landing_zone": lz[1],
        "hospital": hospital,
        "weather": weather,
        "terrain_risk": data["terrain_risk"],
        "flight_eta_min": flight_eta,
        "landing_feasibility": round(feasibility, 3),
        "oxygen_required": oxygen_required,
        "ground_access": "CONSTRAINED",
        "decision": "AIR AMBULANCE RECOMMENDED" if feasibility >= 0.55 else "AIR RESPONSE REQUIRES HUMAN REVIEW",
        "constraints": [
            f"Altitude {incident['altitude_m']:,} m",
            f"Wind {weather['wind_kmh']} km/h",
            f"Visibility {weather['visibility_km']} km",
            "High-terrain navigation required",
            "Landing zone must be visually confirmed before touchdown",
        ],
        "flight_path": [
            {"lat": target_lz["lat"], "lon": target_lz["lon"]},
            {"lat": incident["lat"], "lon": incident["lon"]},
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "synthetic": True,
        "simulation_note": "Local air-rescue decision simulation; not an aviation control system.",
    }
