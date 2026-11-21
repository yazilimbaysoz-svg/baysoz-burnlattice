"""SARIF and report determinism tests.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import json

import pytest

from burnlattice.model import Finding, Severity
from burnlattice.report import Report, sorted_findings
from burnlattice.sarif import to_sarif
from tests.helpers import check

_FINDING = Finding(
    rule_id="SLO_DRIFT_EXPRESSION",
    severity=Severity.ERROR,
    message="expression drifted",
    path="rules.yml",
    line=14,
    detail="expected x, found y",
)


def report() -> Report:
    """Build a single-finding report."""
    return Report(command="verify", source="rules.yml", findings=(_FINDING,))


def test_sarif_structure() -> None:
    document = to_sarif((_FINDING,), "rules.yml")
    check(document["version"] == "2.1.0", "wrong SARIF version")
    runs = document["runs"]
    check(isinstance(runs, list) and len(runs) == 1, "wrong SARIF runs")
    results = runs[0]["results"]
    check(results[0]["ruleId"] == "SLO_DRIFT_EXPRESSION", "rule id missing")
    check(results[0]["level"] == "error", "level missing")
    check("Baysöz Labs" in runs[0]["tool"]["driver"]["fullName"], "attribution missing")


def test_report_json_and_digest_are_stable() -> None:
    first, second = report(), report()
    check(first.to_json() == second.to_json(), "JSON output is not deterministic")
    check(first.digest() == second.digest(), "digest is not deterministic")
    check(len(first.digest()) == 64, "digest is not SHA-256 hex")


def test_report_renderers() -> None:
    check(json.loads(report().render("json"))["tool"] == "burnlattice", "JSON render failed")
    check(json.loads(report().render("sarif"))["version"] == "2.1.0", "SARIF render failed")
    check("Baysöz Labs" in report().render("text"), "text render lacks attribution")
    with pytest.raises(ValueError, match="unsupported"):
        report().render("xml")


def test_exit_code_policy() -> None:
    check(report().exit_code(Severity.ERROR) == 1, "error should fail error gate")
    check(report().exit_code(Severity.WARNING) == 1, "error should fail warning gate")
    clean = Report(command="audit", source="rules.yml", findings=())
    check(clean.exit_code(Severity.NOTE) == 0, "clean report should pass")


def test_unsorted_findings_are_rejected() -> None:
    low = replace_finding("RULE_SHORT_RATE_WINDOW", Severity.WARNING)
    high = replace_finding("SLO_DRIFT_MISSING_ALERT", Severity.ERROR)
    with pytest.raises(ValueError, match="sorted"):
        Report(command="verify", source="x", findings=(low, high))
    check(sorted_findings([low, high]) == (high, low), "sorting failed")


def replace_finding(rule_id: str, severity: Severity) -> Finding:
    """Create a finding with a selected identifier and severity."""
    return Finding(rule_id=rule_id, severity=severity, message=rule_id)
