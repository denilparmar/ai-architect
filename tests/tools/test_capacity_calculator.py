import logging
import re
from pathlib import Path

import pytest

from agent.tools import capacity_calculator as cc
from agent.tools.formula_library import (
    ASSUMPTION_DEFAULTS,
    FORMULA_LIBRARY,
    SYSTEM_ASSUMPTIONS,
)

DAU = 1_000_000
SOURCE = Path(cc.__file__).read_text(encoding="utf-8")


def qps(per_day, peak):
    return DAU * per_day / 86400 * peak


def storage(per_day, item_kb, media_ratio=0, media_mb=2):
    return DAU * per_day * (item_kb / 1024 + media_ratio * media_mb) / 1024 * 365


def egress(per_day, peak, response_kb):
    return qps(per_day, peak) * response_kb * 8 / 1024


# Expected value of every metric per system with empty assumptions, written out as the
# formula so it can be checked by hand.
EXPECTED = {
    "messaging / chat apps": {
        "peak_write_qps": qps(40, 4),
        "peak_read_qps": qps(120, 4),
        "concurrent_connections": DAU * 0.1,
        "storage_growth_per_year": storage(40, 1),
        "hot_working_set": DAU * 120 * 1 / 1024 / 1024,
        "egress_bandwidth": egress(120, 4, 1),
    },
    "social networks": {
        "feed_updates_qps": qps(5, 3),
        "fanout_load": 5 * 200,
        "peak_read_qps": qps(50, 3),
        "concurrent_connections": DAU * 0.03,
        "storage_growth_per_year": storage(5, 2, 0.2),
        "hot_working_set": DAU * 200 * 2 / 1024 / 1024,
        "egress_bandwidth": egress(50, 3, 100),
    },
    "video streaming platforms": {
        "peak_concurrent_streams": DAU * (2 / 24) * 4,
        "network_throughput": DAU * (2 / 24) * 4 * 3,
    },
    "e-commerce platforms": {
        "orders_per_second": qps(2, 3),
        "peak_read_qps": qps(30, 3),
        "storage_growth_per_year": storage(2, 5),
        "egress_bandwidth": egress(30, 3, 150),
    },
    "ticket booking systems": {
        "peak_booking_qps": qps(1, 3),
        "peak_read_qps": qps(10, 3),
        "storage_growth_per_year": storage(1, 2),
    },
    "food delivery apps": {
        "orders_per_second": qps(2, 3),
        "peak_read_qps": qps(20, 3),
        "driver_concurrency": qps(2, 3) * 30 * 60,
    },
    "ride-hailing / mobility apps": {
        "rides_per_second": qps(2, 3),
        "peak_read_qps": qps(20, 3),
        "driver_concurrency": qps(2, 3) * 20 * 60,
    },
    "analytics / data warehouse systems": {
        "query_throughput": DAU * 0.1 * 2 / 3600,
    },
    "banking / fintech systems": {
        "transactions_per_second": qps(10, 3),
        "peak_read_qps": qps(20, 3),
        "storage_growth_per_year": storage(10, 2),
    },
    "education / learning platforms": {
        "concurrent_students": DAU * (2 / 24) * 3,
    },
    "search engines / indexing systems": {
        "search_qps": qps(10, 3),
        "egress_bandwidth": egress(10, 3, 50),
    },
    "content delivery networks (cdn)": {
        "edge_requests_per_second": qps(100, 3),
        "egress_bandwidth": egress(100, 3, 200),
    },
}


def run(monkeypatch, system_type, assumptions=None):
    # map_system is an LLM call; with a canonical system_type it should echo the key.
    monkeypatch.setattr(cc, "map_system", lambda s: s)
    spec = {
        "system_type": system_type,
        "explicit_requirements": {"daily_active_users": DAU},
        "assumptions": assumptions or {},
    }
    return {r["metric"]: r for r in cc.calculate_capacity(spec, "t1")}


def test_expected_table_covers_every_metric_of_every_system():
    assert set(EXPECTED) == set(FORMULA_LIBRARY)
    for system, metrics in FORMULA_LIBRARY.items():
        assert set(EXPECTED[system]) == {m["name"] for m in metrics}


@pytest.mark.parametrize("system_type", list(FORMULA_LIBRARY))
def test_every_metric_uses_system_defaults(monkeypatch, system_type):
    rows = run(monkeypatch, system_type)
    for name, expected in EXPECTED[system_type].items():
        assert rows[name]["requirement"] == pytest.approx(expected), name


@pytest.mark.parametrize("system_type", list(FORMULA_LIBRARY))
def test_rows_carry_sizing_table_fields(monkeypatch, system_type):
    rows = run(monkeypatch, system_type)
    for metric in FORMULA_LIBRARY[system_type]:
        row = rows[metric["name"]]
        assert row["thread_id"] == "t1"
        assert row["drives"] == metric["drives"] and row["drives"]
        assert row["computed_from"] and row["unit"]


def test_peak_write_qps_matches_article(monkeypatch):
    # 1M DAU × 40 msgs ÷ 86,400 × 4 ≈ 1,852 writes/sec
    rows = run(monkeypatch, "messaging / chat apps")
    assert rows["peak_write_qps"]["requirement"] == pytest.approx(1851.85, abs=0.01)


def test_domain_assumption_flows_through_shared_calculators(monkeypatch):
    rows = run(monkeypatch, "messaging / chat apps", {"messages_per_user_per_day": 80})
    assert rows["peak_write_qps"]["requirement"] == pytest.approx(qps(80, 4))
    assert rows["peak_read_qps"]["requirement"] == pytest.approx(qps(240, 4))
    assert rows["hot_working_set"]["requirement"] == pytest.approx(
        DAU * 240 / 1024 / 1024
    )


def test_generic_assumption_overrides_system_default(monkeypatch):
    rows = run(
        monkeypatch,
        "social networks",
        {"concurrency_ratio": 0.05, "reads_per_user_per_day": 100},
    )
    assert rows["concurrent_connections"]["requirement"] == pytest.approx(DAU * 0.05)
    assert rows["peak_read_qps"]["requirement"] == pytest.approx(qps(100, 3))


def test_same_calculator_differs_by_system():
    messaging = cc.resolve_assumptions("messaging / chat apps", {})
    social = cc.resolve_assumptions("social networks", {})
    assert cc.calc_concurrent_connections(DAU, messaging)["value"] == DAU * 0.1
    assert cc.calc_concurrent_connections(DAU, social)["value"] == DAU * 0.03


def test_unknown_system_falls_back_to_global_defaults():
    resolved = cc.resolve_assumptions("something else", {})
    assert resolved == ASSUMPTION_DEFAULTS


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ride-hailing / mobility apps", "ride-hailing / mobility apps"),
        ("  RIDE-HAILING / MOBILITY APPS  ", "ride-hailing / mobility apps"),
    ],
)
def test_map_system_exact_match_skips_llm(monkeypatch, value, expected):
    def fail():
        raise AssertionError("LLM must not be called for an exact match")

    monkeypatch.setattr(cc, "get_small_llm", fail)
    assert cc.map_system(value) == expected


class _StubLLM:
    def __init__(self, key):
        self.key = key
        self.schema = None
        self.prompt = None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, prompt):
        self.prompt = prompt
        return self.schema(system_type=self.key)


def test_map_system_uses_llm_for_free_form_input(monkeypatch):
    llm = _StubLLM("ride-hailing / mobility apps")
    monkeypatch.setattr(cc, "get_small_llm", lambda: llm)

    assert cc.map_system("Uber-like cab booking app") == "ride-hailing / mobility apps"
    assert "Uber-like cab booking app" in llm.prompt


def test_map_system_schema_rejects_keys_outside_formula_library():
    with pytest.raises(ValueError):
        cc._SystemMatch(system_type="not a real system")


def test_map_system_wraps_llm_failures(monkeypatch):
    class Broken:
        def with_structured_output(self, schema):
            raise RuntimeError("boom")

    monkeypatch.setattr(cc, "get_small_llm", lambda: Broken())
    with pytest.raises(ValueError, match="Could not map system type"):
        cc.map_system("something unmappable")


def test_normalize_keeps_all_canonical_keys():
    raw = {key: default + 1 for key, default in ASSUMPTION_DEFAULTS.items()}
    assert cc.normalize_assumptions(raw) == raw


def test_normalize_drops_unknown_keys_with_warning(caplog):
    with caplog.at_level(logging.WARNING):
        result = cc.normalize_assumptions({"msgs_per_day": 60, "avg_followers": 300})
    assert result == {"avg_followers": 300}
    assert "msgs_per_day" in caplog.text


def test_calculators_read_only_known_keys():
    read_keys = set(re.findall(r'\ba\["([a-z_]+)"\]', SOURCE))
    assert read_keys <= set(ASSUMPTION_DEFAULTS)


def test_system_assumption_profiles_reference_known_keys():
    assert set(SYSTEM_ASSUMPTIONS) == set(FORMULA_LIBRARY)
    for profile in SYSTEM_ASSUMPTIONS.values():
        for key, spec in profile.items():
            assert key in ASSUMPTION_DEFAULTS
            if isinstance(spec, str):
                assert spec in ASSUMPTION_DEFAULTS
            elif isinstance(spec, tuple):
                assert spec[0] in ASSUMPTION_DEFAULTS


def test_every_metric_calculator_resolves_to_a_function():
    for metrics in FORMULA_LIBRARY.values():
        for metric in metrics:
            assert callable(getattr(cc, metric["calc"], None)), metric["calc"]
