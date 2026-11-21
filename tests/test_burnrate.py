"""Burn-rate arithmetic and rule synthesis tests.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from burnlattice.burnrate import (
    TIERS,
    BurnMathError,
    explanation_rows,
    generate_rules,
    tier_math,
)
from burnlattice.model import Rule, Severity
from burnlattice.spec import load_contract
from tests.helpers import check, example


def contract():
    """Load the standard example contract."""
    return load_contract(example("checkout-availability.json"))


def test_four_tiers_are_compiled() -> None:
    rules = generate_rules(contract())
    check(len(rules) == 4, "expected four burn tiers")
    check(
        [rule.name for rule in rules]
        == [
            "CheckoutAvailabilityBurnFast1h6h",
            "CheckoutAvailabilityBurnFast6h1d",
            "CheckoutAvailabilityBurnSlow1d3d",
            "CheckoutAvailabilityBurnSlow3d30d",
        ],
        "rule names are not stable",
    )
    check([rule.for_time for rule in rules] == ["2m", "2m", "5m", "5m"], "for durations wrong")


def test_expression_contains_both_windows_and_exact_threshold() -> None:
    rule = generate_rules(contract())[0]
    check("0.0144" in rule.expr, "exact threshold missing")
    check("[1h]" in rule.expr and "[6h]" in rule.expr, "windows missing")
    check("status=~\"2..\"" in rule.expr, "matcher was not rendered")
    check(" and " in rule.expr, "multi-window conjunction missing")


def test_budget_math() -> None:
    source = contract()
    math = tier_math(source, TIERS["fast_1h_6h"], "page")
    check(math.threshold == Decimal("0.0144"), "threshold arithmetic failed")
    check(math.budget_pct_at_short == Decimal("2"), "budget consumption failed")
    check(math.time_to_exhaust_seconds == Decimal(180000), "exhaustion time failed")
    check(math.confirmation_seconds == Decimal(21600), "confirmation window failed")


def test_stricter_objective_lowers_threshold() -> None:
    strict = replace(contract(), objective=Decimal("99.99"))
    math = tier_math(strict, TIERS["fast_1h_6h"], "page")
    check(math.threshold == Decimal("0.00144"), "strict objective threshold failed")


def test_impossible_threshold_is_rejected() -> None:
    impossible = replace(contract(), objective=Decimal("99.999"))
    with pytest.raises(BurnMathError, match="impossible"):
        tier_math(impossible, replace(TIERS["slow_3d_30d"], burn_rate=Decimal(200000)), "page")


def test_explanation_rows_match_compiled_rules() -> None:
    source = contract()
    rows = explanation_rows(source)
    check(len(rows) == len(generate_rules(source)), "row count mismatch")
    for row in rows:
        check(row.threshold > 0, "non-positive threshold")
        check(row.budget_pct_at_short > 0, "non-positive budget consumption")


def test_rules_are_immutable_records() -> None:
    rule = generate_rules(contract())[0]
    check(isinstance(rule, Rule), "rule type is wrong")
    with pytest.raises(AttributeError):
        rule.name = "changed"


def test_rule_severities_follow_channel() -> None:
    severities = [rule.labels_dict["severity"] for rule in generate_rules(contract())]
    check(severities == ["critical", "critical", "warning", "warning"], "severity mismatch")
    check(Severity.ERROR.rank > Severity.WARNING.rank, "severity ordering failed")
