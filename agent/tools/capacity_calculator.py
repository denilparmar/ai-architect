import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent.tools.formula_library import (
    ASSUMPTION_DEFAULTS,
    FORMULA_LIBRARY,
    SYSTEM_ASSUMPTIONS,
)
from llm.factory import get_small_llm
from observability.logger import get_logger

logger = get_logger(__name__)

SECONDS_PER_DAY = 86400


# Every calculator takes (dau, a) where `a` is the fully resolved assumptions dict from
# resolve_assumptions(), so it only reads generic keys and never needs to know the system.
def _peak_qps(dau, per_user_per_day, a):
    return dau * per_user_per_day / SECONDS_PER_DAY * a["peak_factor"]


def calc_peak_write_qps(dau, a):
    return {
        "formula": "DAU × writes/user/day ÷ 86,400 × peak_factor",
        "value": _peak_qps(dau, a["writes_per_user_per_day"], a),
        "unit": "qps",
    }


def calc_peak_read_qps(dau, a):
    return {
        "formula": "DAU × reads/user/day ÷ 86,400 × peak_factor",
        "value": _peak_qps(dau, a["reads_per_user_per_day"], a),
        "unit": "qps",
    }


def calc_concurrent_connections(dau, a):
    return {
        "formula": "DAU × concurrency_ratio",
        "value": dau * a["concurrency_ratio"],
        "unit": "connections",
    }


def calc_storage_growth_yearly(dau, a):
    item_gb = (
        a["avg_item_size_kb"] / 1024 + a["media_ratio"] * a["avg_media_mb"]
    ) / 1024
    return {
        "formula": "DAU × writes/user/day × (item KB + media_ratio × media MB) × 365",
        "value": dau * a["writes_per_user_per_day"] * item_gb * 365,
        "unit": "GB",
    }


def calc_hot_working_set(dau, a):
    return {
        "formula": "DAU × hot_items/user × avg_item_size",
        "value": dau * a["hot_items_per_user"] * a["avg_item_size_kb"] / 1024 / 1024,
        "unit": "GB",
    }


def calc_egress_bandwidth(dau, a):
    read_qps = _peak_qps(dau, a["reads_per_user_per_day"], a)
    return {
        "formula": "peak_read_qps × avg_response_size",
        "value": read_qps * a["avg_response_size_kb"] * 8 / 1024,
        "unit": "Mbps",
    }


def calc_concurrent_sessions(dau, a):
    return {
        "formula": "DAU × (active_hours/24) × peak_factor",
        "value": dau * (a["active_hours_per_user_per_day"] / 24) * a["peak_factor"],
        "unit": "sessions",
    }


def calc_network_throughput(dau, a):
    sessions = calc_concurrent_sessions(dau, a)["value"]
    return {
        "formula": "concurrent_sessions × Mbps/stream",
        "value": sessions * a["mbps_per_stream"],
        "unit": "Mbps",
    }


def calc_littles_law_concurrency(dau, a):
    write_qps = _peak_qps(dau, a["writes_per_user_per_day"], a)
    return {
        "formula": "peak_write_qps × avg_duration (Little's law)",
        "value": write_qps * a["avg_duration_minutes"] * 60,
        "unit": "concurrent trips",
    }


def calc_active_user_query_rate(dau, a):
    return {
        "formula": "DAU × concurrency_ratio × ops/active user/hour ÷ 3600",
        "value": dau
        * a["concurrency_ratio"]
        * a["ops_per_active_user_per_hour"]
        / 3600,
        "unit": "qps",
    }


def calc_fanout_load(dau, a):
    return {
        "formula": "writes/user/day × avg_followers",
        "value": a["writes_per_user_per_day"] * a["avg_followers"],
        "unit": "deliveries per user per day",
    }


def normalize_assumptions(raw_assumptions):
    # Keys are canonical by construction (RequirementSpec's enum); drop anything else loudly.
    unknown = set(raw_assumptions) - set(ASSUMPTION_DEFAULTS)
    if unknown:
        logger.warning(f"Dropping unknown assumptions: {sorted(unknown)}")
    return {k: v for k, v in raw_assumptions.items() if k in ASSUMPTION_DEFAULTS}


def resolve_assumptions(system_type: str, supplied: dict) -> dict:
    """Return every assumption key with a value: user-supplied, else the system's, else global."""
    profile = SYSTEM_ASSUMPTIONS.get(system_type, {})
    resolved = {}
    for key, default in ASSUMPTION_DEFAULTS.items():
        if key in supplied:
            resolved[key] = supplied[key]
            continue
        spec = profile.get(key, default)
        if isinstance(spec, str):
            spec = (spec, 1)
        if isinstance(spec, tuple):
            domain_key, factor = spec
            value = supplied.get(domain_key, ASSUMPTION_DEFAULTS[domain_key]) * factor
        else:
            value = spec
        resolved[key] = value
    return resolved


def calculate_capacity(
    requirement_spec: dict[str, Any],
    thread_id: str = "abc",
) -> list[dict[str, Any]]:
    """Calculate workload metrics from a requirement specification."""
    system_type = map_system(requirement_spec.get("system_type", "").lower())
    dau = requirement_spec.get("explicit_requirements", {}).get("daily_active_users", 0)
    supplied = normalize_assumptions(requirement_spec.get("assumptions", {}))
    results = []
    metrics = FORMULA_LIBRARY[system_type]
    assumptions = resolve_assumptions(system_type, supplied)
    for metric in metrics:
        calc = globals()[metric["calc"]](dau, assumptions)
        results.append(
            {
                "thread_id": thread_id,
                "metric": metric["name"],
                "value": calc["value"],
                "unit": calc["unit"],
                "computed_from": calc["formula"],
                "drives": metric["drives"],
            }
        )

    print("Capacity Calculation Results (JSON):")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return results


class _SystemMatch(BaseModel):
    system_type: Literal[tuple(FORMULA_LIBRARY)] = Field(
        description="The FORMULA_LIBRARY key that best matches the requested system."
    )


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


def map_system(req_system_type: str) -> str:
    """Resolve any system description to the closest FORMULA_LIBRARY key."""
    normalized = _normalize(req_system_type)
    for key in FORMULA_LIBRARY:
        if _normalize(key) == normalized:
            return key

    # Free-form input: ask the LLM to pick a key; the schema restricts it to valid keys.
    prompt = f"""You map a system description to the closest system type in a formula library.

System description:
{req_system_type}

Valid system types:
{list(FORMULA_LIBRARY)}

Pick the single semantically closest valid system type."""
    try:
        match = get_small_llm().with_structured_output(_SystemMatch).invoke(prompt)
    except Exception as e:
        raise ValueError(
            f"Could not map system type {req_system_type!r} to one of {list(FORMULA_LIBRARY)}"
        ) from e
    logger.info(f"Mapped system type {req_system_type!r} -> {match.system_type!r}")
    return match.system_type
