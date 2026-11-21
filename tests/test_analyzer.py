"""Rule hazard analysis tests.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

from dataclasses import replace

from burnlattice.analyzer import analyze_rules
from burnlattice.burnrate import generate_rules
from burnlattice.model import Finding
from burnlattice.spec import load_contract
from tests.helpers import check, example

_RULES = generate_rules(load_contract(example("checkout-availability.json")))


def ids(findings: tuple[Finding, ...]) -> set[str]:
    """Collect rule identifiers from findings."""
    return {item.rule_id for item in findings}


def test_generated_rules_are_clean() -> None:
    check(analyze_rules(_RULES) == (), "compiler emitted hazardous rules")


def test_match_all_regex_is_flagged() -> None:
    rule = replace(_RULES[0], expr=_RULES[0].expr.replace('status=~"2.."', 'status=~".*"'))
    check("RULE_UNBOUNDED_REGEX" in ids(analyze_rules((rule,))), "wildcard not flagged")


def test_short_rate_window_is_flagged() -> None:
    rule = replace(_RULES[0], expr=_RULES[0].expr.replace("[1h]", "[10s]"))
    check("RULE_SHORT_RATE_WINDOW" in ids(analyze_rules((rule,))), "short window not flagged")


def test_time_modifier_is_flagged() -> None:
    rule = replace(_RULES[0], expr=_RULES[0].expr.replace("[1h]", "[1h] offset 5m"))
    check("RULE_TIME_MODIFIER" in ids(analyze_rules((rule,))), "offset not flagged")


def test_invalid_expression_is_flagged() -> None:
    rule = replace(_RULES[0], expr="sum(rate(foo[5m])")
    check("RULE_INVALID_EXPRESSION" in ids(analyze_rules((rule,))), "syntax error not flagged")


def test_duplicate_alert_is_flagged() -> None:
    check("RULE_DUPLICATE_ALERT" in ids(analyze_rules((_RULES[0], _RULES[0]))), "duplicate missed")


def test_missing_severity_is_flagged() -> None:
    rule = replace(_RULES[0], labels=(("service", "checkout-api"),))
    check("RULE_MISSING_SEVERITY" in ids(analyze_rules((rule,))), "severity check missed")


def test_unscoped_selector_is_flagged() -> None:
    rule = replace(
        _RULES[0],
        expr="sum(rate(http_requests_total[5m])) / sum(rate(http_requests_count[5m])) > 0.01",
    )
    check("RULE_UNSCOPED_SELECTOR" in ids(analyze_rules((rule,))), "scope check missed")


def test_keep_firing_without_for_is_flagged() -> None:
    rule = replace(_RULES[0], for_time=None, keep_firing_for="5m")
    found = ids(analyze_rules((rule,)))
    check("RULE_KEEP_FIRING_WITHOUT_FOR" in found, "keep_firing check missed")


def test_combined_hazards_are_reported_together() -> None:
    rule = replace(
        _RULES[0],
        expr=(
            'sum(rate(http_requests_total{status=~".*"}[10s] offset 5m))'
        ),
    )
    found = ids(analyze_rules((rule,)))
    expected = {
        "RULE_TIME_MODIFIER",
        "RULE_UNBOUNDED_REGEX",
        "RULE_SHORT_RATE_WINDOW",
        "RULE_UNSCOPED_SELECTOR",
    }
    check(expected <= found, f"combined hazards missed: {expected - found}")
    check("RULE_INVALID_EXPRESSION" not in found, "time modifier caused a duplicate finding")
