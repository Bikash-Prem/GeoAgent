from __future__ import annotations

from datetime import datetime, timezone
from math import hypot

# Deterministic mountain-rescue fixtures for the local product environment.
# These are explicitly simulation data: no real aviation dispatch or air-traffic control is performed.

REGIONS = {
    "himachal": {
        "name": "Himachal Pradesh",
        "incident": {"id": "MTN-HIM-01", "name": "Manali–Rohtang rescue", "lat": 32.3205, "lon": 77.2040, "altitude_m": 3_120, "severity": "critical", "details": "Vehicle rollover on a high-altitude mountain road; ground access constrained."},
        "landing_zones": [
            {"id": "LZ-HIM-01", "name": "Solang Valley LZ", "lat": 32.3157, "lon": 77.1553, "altitude_m": 2_560, "surface": "prepared", "status": "AVAILABLE", "capacity": "medium"},
            {"id": "LZ-HIM-02", "name": "Marhi Ridge LZ", "lat": 32.3330, "lon": 77.2105, "altitude_m": 3_330, "surface": "mountain clearing", "status": "CONDITIONAL", "capacity": "small"},
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
    {"id": "AIR-01", "name": "Mountain Rescue 01", "base": "Bhuntar (Kullu)", "base_lat": 31.8763, "base_lon": 77.1544, "crew": "2 pilots + flight medic", "range_km": 420, "fuel_pct": 72, "cruise_kmh": 180, "service_ceiling_m": 6_000, "available": True},
    {"id": "AIR-02", "name": "Mountain Rescue 02", "base": "Jolly Grant (Dehradun)", "base_lat": 30.1897, "base_lon": 78.1803, "crew": "2 pilots + critical-care medic", "range_km": 510, "fuel_pct": 64, "cruise_kmh": 190, "service_ceiling_m": 6_100, "available": True},
    {"id": "AIR-03", "name": "High Altitude Rescue 03", "base": "Leh", "base_lat": 34.1359, "base_lon": 77.5465, "crew": "2 pilots + altitude medic", "range_km": 380, "fuel_pct": 81, "cruise_kmh": 170, "service_ceiling_m": 7_000, "available": True},
]
STARTUP_MIN = 6.0          # crew brief, engine start, lift-off
LIMITS = {"wind_kmh": 45, "visibility_km": 3.0, "cloud_clearance_m": 300}


def _distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    return hypot((a[0] - b[0]) * 111.0, (a[1] - b[1]) * 101.0)


def _feasibility(zone: dict, weather: dict, unit: dict) -> tuple[float, list[str], list[str]]:
    """Deterministic landing feasibility 0..1 plus the checks that passed / failed (operator-readable)."""
    ok, fail, score = [], [], 0.95
    if weather["wind_kmh"] > LIMITS["wind_kmh"]:
        fail.append(f"Wind {weather['wind_kmh']} km/h above the {LIMITS['wind_kmh']} km/h limit"); score -= 0.45
    else:
        ok.append(f"Wind {weather['wind_kmh']} km/h within limit"); score -= max(0, weather["wind_kmh"] - 20) / 100
    if weather["visibility_km"] < LIMITS["visibility_km"]:
        fail.append(f"Visibility {weather['visibility_km']} km below {LIMITS['visibility_km']} km"); score -= 0.4
    else:
        ok.append(f"Visibility {weather['visibility_km']} km")
    clearance = weather["cloud_base_m"] - zone["altitude_m"]
    if clearance < LIMITS["cloud_clearance_m"]:
        fail.append(f"Cloud base only {clearance:,} m above the landing zone"); score -= 0.35
    else:
        ok.append(f"Cloud base {clearance:,} m above the landing zone")
    if zone["altitude_m"] > unit["service_ceiling_m"] - 500:
        fail.append(f"Landing zone at {zone['altitude_m']:,} m is near the aircraft ceiling"); score -= 0.3
    score -= max(0, zone["altitude_m"] - 3000) / 1000 * 0.06   # thinner air, less power margin
    if zone["status"] != "AVAILABLE":
        score -= 0.12
    return round(max(0.05, min(0.97, score)), 3), ok, fail


def build_air_rescue_plan(region: str = "himachal", weather_override: dict | None = None) -> dict:
    key = region.lower().strip()
    if key not in REGIONS:
        key = "himachal"
    data = REGIONS[key]
    incident, hospital = data["incident"], data["hospital"]
    weather = {**data["weather"], **{k: v for k, v in (weather_override or {}).items() if v is not None}}
    weather["status"] = "FLYABLE" if weather["wind_kmh"] <= 30 and weather["visibility_km"] >= 5 else "CONDITIONAL" if weather["wind_kmh"] <= LIMITS["wind_kmh"] and weather["visibility_km"] >= LIMITS["visibility_km"] else "NO-FLY"
    inc_pos = (incident["lat"], incident["lon"])
    hosp_pos = (hospital["lat"], hospital["lon"])

    options = []
    for unit in (u for u in AIR_AMBULANCES if u["available"]):
        base = (unit["base_lat"], unit["base_lon"])
        for zone in data["landing_zones"]:
            lz = (zone["lat"], zone["lon"])
            leg_out = _distance_km(base, lz)
            leg_med = _distance_km(lz, hosp_pos)
            mission_km = leg_out + leg_med + _distance_km(hosp_pos, base)
            usable_km = unit["range_km"] * unit["fuel_pct"] / 100 * 0.8  # 20% reserve
            feas, ok, fail = _feasibility(zone, weather, unit)
            if mission_km > usable_km:
                fail.append(f"Mission {mission_km:.0f} km exceeds usable range {usable_km:.0f} km (20% reserve)"); feas = min(feas, 0.1)
            else:
                ok.append(f"Fuel: {mission_km:.0f} km mission within {usable_km:.0f} km usable")
            ground_km = _distance_km(lz, inc_pos)
            eta = STARTUP_MIN + leg_out / unit["cruise_kmh"] * 60 + ground_km * 4  # 4 min/km rescue-team approach from the LZ
            options.append({"unit": unit, "zone": zone, "eta": round(eta, 1), "feas": feas, "ok": ok, "fail": fail,
                            "to_hospital_min": round(leg_med / unit["cruise_kmh"] * 60, 1), "mission_km": round(mission_km, 1),
                            "score": eta + (1 - feas) * 60})
    options.sort(key=lambda o: o["score"])
    best = options[0]
    alt_zone = next((z for z in data["landing_zones"] if z["id"] != best["zone"]["id"]), best["zone"])
    feasible = best["feas"] >= 0.55 and not best["fail"]
    return {
        "region": key, "region_name": data["name"], "incident": incident,
        "air_ambulance": {k: v for k, v in best["unit"].items()},
        "selected_landing_zone": best["zone"], "alternate_landing_zone": alt_zone, "hospital": hospital, "weather": weather,
        "terrain_risk": data["terrain_risk"], "flight_eta_min": best["eta"], "to_hospital_min": best["to_hospital_min"],
        "mission_km": best["mission_km"], "landing_feasibility": best["feas"], "oxygen_required": incident["altitude_m"] >= 3000,
        "ground_access": "CONSTRAINED",
        "decision": "AIR AMBULANCE RECOMMENDED" if feasible else "AIR RESPONSE REQUIRES HUMAN REVIEW",
        "checks_passed": best["ok"], "checks_failed": best["fail"],
        "constraints": best["ok"] + best["fail"],
        "options": [{"unit_id": o["unit"]["id"], "unit": o["unit"]["name"], "landing_zone": o["zone"]["name"], "eta_min": o["eta"], "feasibility": o["feas"], "blocked": bool(o["fail"])} for o in options],
        "flight_path": [{"lat": best["unit"]["base_lat"], "lon": best["unit"]["base_lon"]}, {"lat": best["zone"]["lat"], "lon": best["zone"]["lon"]}, {"lat": hospital["lat"], "lon": hospital["lon"]}],
        "generated_at": datetime.now(timezone.utc).isoformat(), "synthetic": True,
        "simulation_note": "Decision simulation on demo fixtures; it does not control aircraft or air traffic.",
    }
