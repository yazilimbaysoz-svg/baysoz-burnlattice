"""Adversarial, anti-stub and whole-repository consistency tests.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from burnlattice.analyzer import analyze_rules
from burnlattice.burnrate import TIERS, generate_rules, tier_math
from burnlattice.drift import budget_reconciliation, verify_drift
from burnlattice.model import Finding, Severity
from burnlattice.promql import PromQLError, canonical
from burnlattice.sarif import _DESCRIPTIONS
from burnlattice.spec import SpecError, contract_from_mapping, load_contract
from tests.helpers import PROJECT_ROOT, check, example

_FORBIDDEN_SOURCE_TOKENS = (
    "subprocess",
    "pickle",
    "eval(",
    "exec(",
    "socket",
    "requests.get",
    "urllib.request",
    "TODO",
    "FIXME",
    "NotImplementedError",
)
_SKIP_DIRS = {".git", ".venv", "dist", "build", "__pycache__", ".pytest_cache", ".ruff_cache"}


def _public_files() -> list[Path]:
    files: list[Path] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or _SKIP_DIRS & set(path.parts):
            continue
        if path.suffix in {".py", ".md", ".toml", ".yml", ".yaml", ".json"} or path.name in {
            "LICENSE",
            ".gitignore",
            ".semgrepignore",
        }:
            files.append(path)
    return sorted(files)


def test_every_public_file_attributes_baysöz_labs() -> None:
    files = _public_files()
    check(len(files) >= 20, "unexpectedly small public file set")
    for path in files:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(PROJECT_ROOT)
        check("baysozlabs@proton.me" in text, f"missing attribution in {relative}")


def test_source_contains_no_forbidden_capabilities_or_stubs() -> None:
    for path in sorted((PROJECT_ROOT / "src").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in _FORBIDDEN_SOURCE_TOKENS:
            check(token not in text, f"forbidden token {token!r} in {path.name}")


def test_every_emitted_finding_has_a_sarif_description() -> None:
    contract = load_contract(example("checkout-availability.json"))
    rules = generate_rules(contract)
    findings: tuple[Finding, ...] = (
        verify_drift(contract, rules, rules[1:])
        + budget_reconciliation(rules)
        + analyze_rules(rules)
    )
    check(len(findings) > 0, "adversarial input produced no findings")
    for finding in findings:
        check(finding.rule_id in _DESCRIPTIONS, f"undocumented finding {finding.rule_id}")


def test_generated_rules_are_not_stubbed() -> None:
    rules = generate_rules(load_contract(example("checkout-availability.json")))
    for rule in rules:
        check(rule.expr.count("sum(rate(") == 4, f"missing selectors in {rule.name}")
        check(rule.expr.count(" > ") == 2, f"missing thresholds in {rule.name}")
        check(" and " in rule.expr, f"missing confirmation window in {rule.name}")
        check(len(rule.annotations) >= 8, f"missing metadata in {rule.name}")


def test_whitespace_fuzz_does_not_change_canonical_form() -> None:
    expression = generate_rules(load_contract(example("checkout-availability.json")))[0].expr
    baseline = canonical(expression)
    for index in range(1, 101):
        mutated = expression.replace(" / ", " " * (index % 5 + 1) + "/" + " " * 2)
        check(canonical(mutated) == baseline, f"canonicalization unstable at {index}")


def test_objective_tightening_monotonically_reduces_threshold() -> None:
    contract = load_contract(example("checkout-availability.json"))
    thresholds: list[Decimal] = []
    for objective in (Decimal("99"), Decimal("99.9"), Decimal("99.99"), Decimal("99.999")):
        source = replace(contract, objective=objective)
        math = tier_math(source, TIERS["fast_6h_1d"], "page")
        check(math.budget_pct_at_short == Decimal(5), "budget accounting failed")
        thresholds.append(math.threshold)
    check(thresholds == sorted(thresholds, reverse=True), "thresholds are not monotonic")


def test_adversarial_matcher_payload_is_rejected() -> None:
    data = json.loads(example("checkout-availability.json").read_text(encoding="utf-8"))
    data["slo"]["sli"]["good"]["matchers"]["job"] = "ok\"} or rate(foo[1m])}"
    with pytest.raises(SpecError):
        contract_from_mapping(data)


def test_expression_bomb_is_rejected() -> None:
    with pytest.raises(PromQLError):
        canonical("(" * 5000 + "up")


def test_severity_ranks_are_total() -> None:
    check(
        [Severity.NOTE.rank, Severity.WARNING.rank, Severity.ERROR.rank] == [0, 1, 2],
        "severity ranks changed",
    )
