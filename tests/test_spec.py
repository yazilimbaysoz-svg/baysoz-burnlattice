"""Contract validation tests.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import copy
import json
from decimal import Decimal

import pytest

from burnlattice.spec import SpecError, contract_from_mapping, load_contract
from tests.helpers import check, example


def loaded() -> dict[str, object]:
    """Return a fresh copy of the example contract mapping."""
    data = json.loads(example("checkout-availability.json").read_text(encoding="utf-8"))
    return data


def test_example_contract_loads() -> None:
    contract = load_contract(example("checkout-availability.json"))
    check(contract.service == "checkout-api", "service was not parsed")
    check(contract.name == "checkout_availability", "SLO name was not parsed")
    check(contract.objective == Decimal("99.9"), "objective lost decimal precision")
    check(contract.window_seconds == 30 * 86400, "window was not converted")
    check(contract.error_budget == Decimal("0.001"), "error budget is wrong")
    check(contract.tiers_dict["page"] == ("fast_1h_6h", "fast_6h_1d"), "page tiers wrong")
    check(contract.labels_dict["team"] == "payments", "labels were not parsed")


def test_latency_contract_derives_le_bucket() -> None:
    data = loaded()
    slo = data["slo"]
    sli = slo["sli"]
    sli.clear()
    sli.update(
        {
            "type": "latency",
            "metric": "http_request_duration_seconds",
            "threshold_ms": 300,
            "matchers": {"job": "checkout-api"},
        }
    )
    contract = contract_from_mapping(data)
    check(contract.sli.good_metric == "http_request_duration_seconds_bucket", "bucket missing")
    check(contract.sli.total_metric == "http_request_duration_seconds_count", "count missing")
    check(contract.sli.good_matchers[-1].value == "0.3", "le boundary is wrong")
    check(contract.sli.threshold_ms == Decimal(300), "threshold was not parsed")


def test_objective_bounds_are_enforced() -> None:
    data = loaded()
    data["slo"]["objective"] = 100
    with pytest.raises(SpecError):
        contract_from_mapping(data)


def test_ratio_metrics_must_match() -> None:
    data = loaded()
    data["slo"]["sli"]["total"]["metric"] = "other_requests_total"
    with pytest.raises(SpecError, match="same metric"):
        contract_from_mapping(data)


def test_good_selector_must_be_stricter() -> None:
    data = loaded()
    data["slo"]["sli"]["good"]["matchers"] = {"job": "checkout-api"}
    with pytest.raises(SpecError, match="strictly more restrictive"):
        contract_from_mapping(data)


def test_total_selector_must_be_subset() -> None:
    data = loaded()
    data["slo"]["sli"]["total"]["matchers"] = {"job": "~.*"}
    with pytest.raises(SpecError, match="strictly more restrictive"):
        contract_from_mapping(data)


def test_matcher_injection_is_rejected() -> None:
    data = loaded()
    data["slo"]["sli"]["good"]["matchers"]["job"] = 'app"} or up{'
    with pytest.raises(SpecError, match="forbidden character"):
        contract_from_mapping(data)


def test_unknown_tier_is_rejected() -> None:
    data = loaded()
    data["slo"]["alerting"]["page"]["tiers"] = ["instant_magic"]
    with pytest.raises(SpecError, match="unknown burn tier"):
        contract_from_mapping(data)


def test_tier_cannot_exceed_window() -> None:
    data = loaded()
    data["slo"]["window"] = "1d"
    with pytest.raises(SpecError, match="longer than the SLO window"):
        contract_from_mapping(data)


def test_page_requires_fast_tier() -> None:
    data = loaded()
    data["slo"]["alerting"]["page"]["tiers"] = ["slow_1d_3d"]
    data["slo"]["alerting"]["ticket"]["tiers"] = ["slow_3d_30d"]
    with pytest.raises(SpecError, match="fast burn tier"):
        contract_from_mapping(data)


def test_tiers_cannot_be_reused() -> None:
    data = loaded()
    data["slo"]["alerting"]["ticket"]["tiers"] = ["fast_1h_6h", "slow_1d_3d"]
    with pytest.raises(SpecError, match="more than one channel"):
        contract_from_mapping(data)


def test_attribution_must_be_exact() -> None:
    data = loaded()
    data["attribution"] = "Someone Else"
    with pytest.raises(SpecError, match="Baysöz Labs"):
        contract_from_mapping(data)


def test_input_mapping_is_not_mutated() -> None:
    data = loaded()
    snapshot = copy.deepcopy(data)
    contract_from_mapping(data)
    check(data == snapshot, "validation mutated caller-owned data")
