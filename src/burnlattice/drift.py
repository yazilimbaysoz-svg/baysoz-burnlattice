"""Detection of silent drift between an SLO contract and deployed rules.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

from decimal import Decimal

from .model import Finding, Rule, Severity, SloContract
from .promql import PromQLError, canonical

_MACHINE_ANNOTATIONS = ("burn_rate", "error_threshold", "objective", "slo_window", "slo")


def _short(value: str, limit: int = 180) -> str:
    return value if len(value) <= limit else value[:limit] + "..."


def verify_drift(
    contract: SloContract,
    expected: tuple[Rule, ...],
    actual: tuple[Rule, ...],
    source: str = "",
) -> tuple[Finding, ...]:
    """Compare compiled expectations with the deployed Prometheus rules."""
    findings: list[Finding] = []
    actual_by_name: dict[str, Rule] = {}
    for rule in actual:
        if rule.name in actual_by_name:
            findings.append(
                Finding(
                    rule_id="SLO_DRIFT_DUPLICATE_ALERT",
                    severity=Severity.ERROR,
                    message=f"alert {rule.name} is defined more than once",
                    path=source,
                    line=rule.line,
                    detail=f"duplicate in group {rule.group}",
                )
            )
        actual_by_name[rule.name] = rule

    for wanted in expected:
        deployed = actual_by_name.get(wanted.name)
        if deployed is None:
            findings.append(
                Finding(
                    rule_id="SLO_DRIFT_MISSING_ALERT",
                    severity=Severity.ERROR,
                    message=f"contracted alert {wanted.name} is missing",
                    path=source,
                    detail=f"expected in group {wanted.group}",
                )
            )
            continue
        try:
            same_expression = canonical(deployed.expr) == canonical(wanted.expr)
        except PromQLError as exc:
            findings.append(
                Finding(
                    rule_id="SLO_DRIFT_INVALID_EXPRESSION",
                    severity=Severity.ERROR,
                    message=f"alert {wanted.name} has an unparseable expression",
                    path=source,
                    line=deployed.line,
                    detail=str(exc),
                )
            )
            same_expression = False
        if not same_expression:
            findings.append(
                Finding(
                    rule_id="SLO_DRIFT_EXPRESSION",
                    severity=Severity.ERROR,
                    message=f"alert {wanted.name} expression drifted from the contract",
                    path=source,
                    line=deployed.line,
                    detail=(
                        f"expected: {_short(wanted.expr)} | actual: {_short(deployed.expr)}"
                    ),
                )
            )

        if deployed.for_time != wanted.for_time:
            findings.append(
                Finding(
                    rule_id="SLO_DRIFT_FOR_DURATION",
                    severity=Severity.ERROR,
                    message=f"alert {wanted.name} has a changed 'for' duration",
                    path=source,
                    line=deployed.line,
                    detail=f"expected {wanted.for_time}, found {deployed.for_time}",
                )
            )
        if deployed.group != wanted.group:
            findings.append(
                Finding(
                    rule_id="SLO_DRIFT_GROUP",
                    severity=Severity.WARNING,
                    message=f"alert {wanted.name} moved to a different rule group",
                    path=source,
                    line=deployed.line,
                    detail=f"expected {wanted.group}, found {deployed.group}",
                )
            )

        expected_labels = wanted.labels_dict
        deployed_labels = deployed.labels_dict
        for key, value in expected_labels.items():
            if deployed_labels.get(key) != value:
                findings.append(
                    Finding(
                        rule_id="SLO_DRIFT_LABEL",
                        severity=Severity.ERROR,
                        message=f"alert {wanted.name} label {key} drifted",
                        path=source,
                        line=deployed.line,
                        detail=f"expected {value!r}, found {deployed_labels.get(key)!r}",
                    )
                )

        expected_annotations = wanted.annotations_dict
        deployed_annotations = deployed.annotations_dict
        for key in _MACHINE_ANNOTATIONS:
            if expected_annotations.get(key) != deployed_annotations.get(key):
                findings.append(
                    Finding(
                        rule_id="SLO_DRIFT_ANNOTATION",
                        severity=Severity.WARNING,
                        message=f"alert {wanted.name} annotation {key} drifted",
                        path=source,
                        line=deployed.line,
                        detail=(
                            f"expected {expected_annotations.get(key)!r}, "
                            f"found {deployed_annotations.get(key)!r}"
                        ),
                    )
                )

    prefix = contract.name.title().replace("_", "") + "Burn"
    for rule in actual:
        if rule.name.startswith(prefix) and rule.name not in {item.name for item in expected}:
            findings.append(
                Finding(
                    rule_id="SLO_DRIFT_UNEXPECTED_ALERT",
                    severity=Severity.WARNING,
                    message=f"unexpected SLO burn alert {rule.name}",
                    path=source,
                    line=rule.line,
                    detail="alert is not covered by the current contract",
                )
            )
    return tuple(findings)


def budget_reconciliation(actual: tuple[Rule, ...]) -> tuple[Finding, ...]:
    """Verify that annotated thresholds match their own objective and burn rate."""
    findings: list[Finding] = []
    for rule in actual:
        annotations = rule.annotations_dict
        objective_text = annotations.get("objective", "").rstrip("%")
        threshold_text = annotations.get("error_threshold")
        if not objective_text or threshold_text is None:
            continue
        try:
            objective = Decimal(objective_text)
            threshold = Decimal(threshold_text)
            burn = Decimal(annotations.get("burn_rate", ""))
        except (ArithmeticError, ValueError):
            continue
        annotated_ratio = (Decimal(100) - objective) / Decimal(100)
        expected_threshold = burn * annotated_ratio
        if threshold != expected_threshold:
            findings.append(
                Finding(
                    rule_id="SLO_BUDGET_THRESHOLD_MISMATCH",
                    severity=Severity.ERROR,
                    message=f"alert {rule.name} error threshold is arithmetically wrong",
                    line=rule.line,
                    detail=(
                        f"expected {expected_threshold}, annotated {threshold} for "
                        f"objective {objective}% and burn rate {burn}"
                    ),
                )
            )
    return tuple(findings)
