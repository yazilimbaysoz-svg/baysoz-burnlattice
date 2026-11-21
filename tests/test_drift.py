"""Drift detection and budget reconciliation tests.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

from dataclasses import replace

from burnlattice.analyzer import analyze_rules
from burnlattice.burnrate import generate_rules
from burnlattice.drift import budget_reconciliation, verify_drift
from burnlattice.model import Finding, Severity
from burnlattice.spec import load_contract
from tests.helpers import check, example

_CONTRACT = load_contract(example("checkout-availability.json"))
_EXPECTED = generate_rules(_CONTRACT)


def ids(findings: tuple[Finding, ...]) -> set[str]:
    """Collect rule identifiers from findings."""
    return {item.rule_id for item in findings}


def test_clean_rules_have_no_drift() -> None:
    check(verify_drift(_CONTRACT, _EXPECTED, _EXPECTED, "rules.yml") == (), "false positive drift")
    check(budget_reconciliation(_EXPECTED) == (), "wrong budget reconciliation on clean rules")
    check(analyze_rules(_EXPECTED) == (), "generated rules are not production-clean")


def test_whitespace_only_changes_are_not_drift() -> None:
    changed = replace(_EXPECTED[0], expr=_EXPECTED[0].expr.replace(") and (", ")   and   ("))
    actual = (changed,) + _EXPECTED[1:]
    check(verify_drift(_CONTRACT, _EXPECTED, actual) == (), "whitespace caused false drift")


def test_window_change_is_detected() -> None:
    changed = replace(_EXPECTED[0], expr=_EXPECTED[0].expr.replace("[1h]", "[5m]"))
    findings = verify_drift(_CONTRACT, _EXPECTED, (changed,) + _EXPECTED[1:])
    check("SLO_DRIFT_EXPRESSION" in ids(findings), "window drift was not detected")


def test_missing_alert_is_detected() -> None:
    findings = verify_drift(_CONTRACT, _EXPECTED, _EXPECTED[1:])
    check("SLO_DRIFT_MISSING_ALERT" in ids(findings), "missing alert was not detected")


def test_label_and_for_drift_are_detected() -> None:
    changed = replace(_EXPECTED[0], for_time="10s", labels=(("severity", "info"),))
    findings = verify_drift(_CONTRACT, _EXPECTED, (changed,) + _EXPECTED[1:])
    found = ids(findings)
    check("SLO_DRIFT_LABEL" in found, "label drift was not detected")
    check("SLO_DRIFT_FOR_DURATION" in found, "for drift was not detected")


def test_annotation_drift_is_a_warning() -> None:
    annotations = tuple(
        (key, "tampered" if key == "slo_window" else value)
        for key, value in _EXPECTED[0].annotations
    )
    changed = replace(_EXPECTED[0], annotations=annotations)
    findings = verify_drift(_CONTRACT, _EXPECTED, (changed,) + _EXPECTED[1:])
    check("SLO_DRIFT_ANNOTATION" in ids(findings), "annotation drift was not detected")
    check(all(item.severity == Severity.WARNING for item in findings), "wrong severity")


def test_duplicate_alert_is_detected() -> None:
    findings = verify_drift(_CONTRACT, _EXPECTED, _EXPECTED + (_EXPECTED[0],))
    check("SLO_DRIFT_DUPLICATE_ALERT" in ids(findings), "duplicate was not detected")


def test_unexpected_slo_alert_is_detected() -> None:
    extra = replace(_EXPECTED[0], name="CheckoutAvailabilityBurnUnexpected")
    findings = verify_drift(_CONTRACT, _EXPECTED, _EXPECTED + (extra,))
    check("SLO_DRIFT_UNEXPECTED_ALERT" in ids(findings), "extra SLO alert was not detected")


def test_budget_reconciliation_detects_tampered_threshold() -> None:
    annotations = tuple(
        (key, "0.99" if key == "error_threshold" else value)
        for key, value in _EXPECTED[0].annotations
    )
    changed = replace(_EXPECTED[0], annotations=annotations)
    findings = budget_reconciliation((changed,))
    check("SLO_BUDGET_THRESHOLD_MISMATCH" in ids(findings), "bad threshold was not detected")
