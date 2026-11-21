"""SARIF 2.1.0 serialization with stable, CI-friendly identifiers.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

from .attribution import ATTRIBUTION, VERSION
from .model import Finding, Severity

_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
_LEVELS = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.NOTE: "note",
}
_DESCRIPTIONS = {
    "SLO_DRIFT_MISSING_ALERT": "A contracted burn-rate alert is absent",
    "SLO_DRIFT_EXPRESSION": "Alert expression differs from the compiled contract",
    "SLO_DRIFT_INVALID_EXPRESSION": "Alert expression is not parseable PromQL",
    "SLO_DRIFT_FOR_DURATION": "Alert for-duration differs from the contract",
    "SLO_DRIFT_GROUP": "Alert moved to a different rule group",
    "SLO_DRIFT_LABEL": "Alert label differs from the contract",
    "SLO_DRIFT_ANNOTATION": "Machine-readable annotation differs from the contract",
    "SLO_DRIFT_DUPLICATE_ALERT": "An alert name is defined more than once",
    "SLO_DRIFT_UNEXPECTED_ALERT": "An uncontracted SLO burn alert is present",
    "SLO_BUDGET_THRESHOLD_MISMATCH": "Annotated burn threshold violates error-budget math",
    "RULE_DUPLICATE_ALERT": "An alert name is defined more than once",
    "RULE_MISSING_SEVERITY": "An alert has no severity label",
    "RULE_KEEP_FIRING_WITHOUT_FOR": "keep_firing_for is set without for",
    "RULE_TIME_MODIFIER": "offset or @ modifier breaks window alignment",
    "RULE_INVALID_EXPRESSION": "PromQL expression failed lexical validation",
    "RULE_UNBOUNDED_REGEX": "A match-all regex selector inflates cardinality",
    "RULE_SHORT_RATE_WINDOW": "A rate window is shorter than five minutes",
    "RULE_UNSCOPED_SELECTOR": "A selector has no job or namespace scope",
}


def to_sarif(findings: tuple[Finding, ...], source: str = "") -> dict[str, object]:
    """Build a deterministic SARIF document from gate findings."""
    rule_ids = sorted({finding.rule_id for finding in findings})
    rules = [
        {
            "id": rule_id,
            "name": rule_id,
            "shortDescription": {
                "text": _DESCRIPTIONS.get(rule_id, "BurnLattice production gate finding")
            },
        }
        for rule_id in rule_ids
    ]
    results: list[dict[str, object]] = []
    for finding in findings:
        text = finding.message
        if finding.detail:
            text = f"{text} - {finding.detail}"
        results.append(
            {
                "ruleId": finding.rule_id,
                "level": _LEVELS[finding.severity],
                "message": {"text": text},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": finding.path or source or "<input>"
                            },
                            "region": {"startLine": max(finding.line, 1)},
                        }
                    }
                ],
            }
        )
    return {
        "version": "2.1.0",
        "$schema": _SCHEMA,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "BurnLattice",
                        "version": VERSION,
                        "fullName": f"BurnLattice {VERSION} - {ATTRIBUTION}",
                        "informationUri": "https://github.com",
                        "rules": rules,
                    }
                },
                "results": results,
                "properties": {"attribution": ATTRIBUTION},
            }
        ],
    }
