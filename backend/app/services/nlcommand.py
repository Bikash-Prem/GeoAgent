"""Natural-language dispatcher commands ("Show the best alternative route for AMB-07").

Design: intent detection is deterministic (a dispatcher command must never depend on an LLM's mood). The answer is
composed ONLY from the engine's structured decision. An LLM is optional and may only re-phrase that text; its output
is rejected if it contains any number that is not in the facts. Approving / dispatching is never done by chat.
Pure Python: no DB / web imports.
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass

INTENTS = (  # first match wins, order matters
    ("approve", r"\b(approve|confirm|execute|send it|do it|go ahead)\b"),
    ("hospital", r"\b(hospitals?|icu|beds?|trauma cent(er|re)|capacity)\b"),
    ("backup", r"\b(backup|back-up|second (unit|ambulance)|another (unit|ambulance)|nearest (unit|ambulance)|deploy|dispatch)\b"),
    ("explain", r"\b(why|explain|reason|cause|evidence|what happened|what's happening)\b"),
    ("compare", r"\b(compare|options|alternatives|all routes)\b"),
    ("best_route", r"\b(route|reroute|re-route|alternative|detour|fastest|best way|avoid)\b"),
    ("status", r"\b(status|eta|where|delay|situation|update|how long)\b"),
)
VEHICLE_RE = re.compile(r"\bAMB[-\s]?(\d{1,3})\b", re.I)


@dataclass
class ParsedCommand:
    intent: str
    vehicle_id: str | None
    text: str


def parse_command(text: str) -> ParsedCommand:
    clean = " ".join(text.strip().split())
    m = VEHICLE_RE.search(clean)
    vehicle = f"AMB-{int(m.group(1)):02d}" if m else None
    low = clean.lower()
    intent = next((name for name, pattern in INTENTS if re.search(pattern, low)), "unknown")
    return ParsedCommand(intent, vehicle, clean)


def _fmt_route(r: dict) -> str:
    return f"{r['name']}: {r['eta_min']:.1f} min ({r['eta_lower']:.1f}-{r['eta_upper']:.1f}), {r['risk']} risk"


def needs_analysis(parsed: ParsedCommand) -> bool:
    """Chat never executes anything, and nonsense input should not create a persisted decision."""
    return parsed.intent not in ("approve", "unknown", "hospital")


def compose(parsed: ParsedCommand, rec: dict | None) -> dict:
    """rec = GeoAgentEngine.recommendation(...) output (None for approve/unknown). Returns answer text + the facts used."""
    if parsed.intent == "approve":
        return {"answer": "I can't approve or dispatch from chat. Review the recommendation in the decision panel and press Approve - the dispatcher always makes the final call.",
                "facts": {}, "tools": [], "highlight_route_id": None}
    if parsed.intent == "unknown" or rec is None:
        return {"answer": "I can show the best route, explain the cause, compare options, or check a backup unit. Try: \"Show the best alternative route for AMB-07\".",
                "facts": {}, "tools": [], "highlight_route_id": None}
    decision = rec["decision"]
    routes = rec["routes"]
    ra = decision["recommended_action"]
    by_id = {r["id"]: r for r in routes}
    chosen, current = by_id.get(ra.get("route_id")), routes[0]
    tools = ["get_situation", "generate_routes", "evaluate_actions", "apply_policy"]
    facts: dict = {"vehicle": rec["vehicle_id"], "recommended_action": ra["action"], "cause": rec["cause"],
                   "cause_confidence_pct": round(rec["confidence"] * 100), "current_route": current and _fmt_route(current),
                   "recommended_route": chosen and _fmt_route(chosen), "reasoning": decision["reasoning"]}
    if parsed.intent in ("best_route", "status"):
        if ra["action"] == "continue":
            text = f"{rec['vehicle_id']}: stay on the current route. {_fmt_route(current)}. {decision['reasoning']}"
        else:
            saved = current["eta_min"] - chosen["eta_min"]
            text = f"{rec['vehicle_id']}: recommended {chosen['name']} - {_fmt_route(chosen)}, {saved:.1f} min faster than {current['name'].lower()} ({current['eta_min']:.1f} min). {chosen['explanation']}"
            if ra["action"].endswith("_and_dispatch") and rec.get("backup_vehicle_id"):
                text += f" Also dispatch {rec['backup_vehicle_id']} (ETA {rec['backup_eta_min']:.1f} min) - the best route still exceeds the response target."
    elif parsed.intent == "explain":
        ev = "; ".join(rec["evidence"][:3]) or "no incident evidence"
        text = f"Likely cause: {rec['cause']} ({round(rec['confidence'] * 100)}% confidence). Evidence: {ev}. {decision['reasoning']}"
        tools = ["get_situation", "get_incidents", "apply_policy"]
    elif parsed.intent == "compare":
        text = "Options for " + rec["vehicle_id"] + ": " + " | ".join(_fmt_route(r) for r in routes) + f". Policy pick: {chosen['name'] if chosen else ra['action']}."
        facts["all_routes"] = [_fmt_route(r) for r in routes]
    else:  # backup
        if rec.get("backup_vehicle_id"):
            hedge = ra["action"].endswith("_and_dispatch")
            text = f"Nearest available backup is {rec['backup_vehicle_id']}, ETA {rec['backup_eta_min']:.1f} min. " + ("The policy recommends dispatching it because the best route may miss the response target." if hedge else "The policy does not recommend spending it now: the best route is expected to meet the response target, and dispatching reduces regional coverage.")
        else:
            text = "No backup unit is currently available."
        facts["backup"] = {"vehicle": rec.get("backup_vehicle_id"), "eta_min": rec.get("backup_eta_min")}
        tools = ["get_available_ambulances", "get_fleet_coverage", "apply_policy"]
    return {"answer": text, "facts": facts, "tools": tools, "highlight_route_id": ra.get("route_id")}


_NUM = re.compile(r"\d+(?:\.\d+)?")


def numbers_grounded(text: str, facts: dict) -> bool:
    allowed = {round(float(x), 1) for x in _NUM.findall(json.dumps(facts))}
    allowed |= {float(round(v)) for v in allowed}
    return all(round(float(x), 1) in allowed or float(round(float(x))) in allowed for x in _NUM.findall(text))


LLM_SYSTEM = ("You are GeoAgent, an assistant for emergency dispatchers. Rewrite the given deterministic answer as 2-3 short, clear sentences. "
              "Use ONLY the facts provided. Do not add numbers, places, causes or advice that are not in the facts. Never imply that an action was taken.")


def llm_rephrase(answer: str, facts: dict, api_key: str, model: str, timeout: float = 6.0) -> str | None:
    """Optional. Returns None on any problem (no key, network, bad output) so the caller falls back to `answer`."""
    if not api_key:
        return None
    body = json.dumps({"model": model, "max_tokens": 300, "system": LLM_SYSTEM,
                       "messages": [{"role": "user", "content": json.dumps({"answer": answer, "facts": facts})}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST",
                                 headers={"content-type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    except Exception:
        return None
    return text or None


def respond(parsed: ParsedCommand, rec: dict | None, use_llm: bool = False, api_key: str = "", model: str = "", _llm=llm_rephrase) -> dict:
    out = compose(parsed, rec)
    mode = "deterministic"
    if use_llm and api_key and out["facts"]:
        phrased = _llm(out["answer"], out["facts"], api_key, model)
        # verified HERE (not inside the LLM call) so no rephraser can bypass the check
        if phrased and numbers_grounded(phrased, {"answer": out["answer"], "facts": out["facts"]}):
            out["answer"], mode = phrased, "llm-rephrased (numbers verified)"
    return {"intent": parsed.intent, "vehicle_id": rec["vehicle_id"] if rec else parsed.vehicle_id, "answer": out["answer"], "mode": mode, "tools_used": out["tools"],
            "decision_id": rec.get("decision_id") if rec else None, "highlight_route_id": out["highlight_route_id"],
            "grounded_on": [e["evidence_id"] for e in rec["decision"]["evidence"]] if rec else [], "requires_human_approval": True}


def hospital_answer(hospitals: list[dict]) -> dict:
    """Answer hospital-capacity questions from the hospital desk state (no decision is created)."""
    ready = [h for h in hospitals if h["status"] != "DIVERT"]
    ready.sort(key=lambda h: h["icu"])
    if not ready:
        text = "Every hospital in the network is on divert. Escalate to the medical officer."
    else:
        parts = [f"{h['name']} {h['status'].lower()} (ICU {round(h['icu'] * 100)}% in use)" for h in ready[:3]]
        text = "Hospital capacity: " + "; ".join(parts) + ". Divert: " + (", ".join(h["name"] for h in hospitals if h["status"] == "DIVERT") or "none") + "."
    return {"intent": "hospital", "vehicle_id": None, "answer": text, "mode": "deterministic", "tools_used": ["get_hospital_capacity"],
            "decision_id": None, "highlight_route_id": None, "grounded_on": [h["id"] for h in hospitals], "requires_human_approval": True}
