"""Static production-hazard analysis for Prometheus rule files.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

from decimal import Decimal

from .model import Finding, Rule, Severity
from .promql import (
    PromQLError,
    Token,
    format_duration,
    parse_duration,
    selector_has_regex_wildcard,
    tokenize,
    validate,
)

_MIN_RATE_WINDOW_SECONDS = Decimal(300)


def _short(value: str, limit: int = 180) -> str:
    return value if len(value) <= limit else value[:limit] + "..."


def _rate_windows(tokens: tuple[Token, ...]) -> list[Decimal]:
    windows: list[Decimal] = []
    for index, token in enumerate(tokens):
        if token.value != "rate":
            continue
        for following in tokens[index + 1 :]:
            if following.kind == "duration":
                windows.append(parse_duration(following.value))
                break
            if following.value == ")":
                break
    return windows


def analyze_rules(rules: tuple[Rule, ...]) -> tuple[Finding, ...]:
    """Return hazard findings for a parsed Prometheus rule file."""
    findings: list[Finding] = []
    seen_names: dict[str, Rule] = {}

    for rule in rules:
        location = rule.name
        if rule.kind == "alert":
            if rule.name in seen_names:
                findings.append(
                    Finding(
                        rule_id="RULE_DUPLICATE_ALERT",
                        severity=Severity.ERROR,
                        message=f"alert {rule.name} is defined more than once",
                        line=rule.line,
                        detail=f"also defined in group {seen_names[rule.name].group}",
                    )
                )
            else:
                seen_names[rule.name] = rule
            if "severity" not in rule.labels_dict:
                findings.append(
                    Finding(
                        rule_id="RULE_MISSING_SEVERITY",
                        severity=Severity.WARNING,
                        message=f"alert {rule.name} has no severity label",
                        line=rule.line,
                    )
                )
            if rule.keep_firing_for is not None and rule.for_time is None:
                findings.append(
                    Finding(
                        rule_id="RULE_KEEP_FIRING_WITHOUT_FOR",
                        severity=Severity.WARNING,
                        message=f"alert {rule.name} sets keep_firing_for without for",
                        line=rule.line,
                    )
                )

        tokens = tokenize(rule.expr)
        has_modifier = any(
            token.kind == "ident" and token.value in {"offset", "@"} for token in tokens
        )
        if has_modifier:
            findings.append(
                Finding(
                    rule_id="RULE_TIME_MODIFIER",
                    severity=Severity.ERROR,
                    message=f"rule {location} uses a time modifier",
                    line=rule.line,
                    detail="offset and @ break alignment between burn windows",
                )
            )
        try:
            validate(tokens, allow_time_modifiers=has_modifier)
        except PromQLError as exc:
            findings.append(
                Finding(
                    rule_id="RULE_INVALID_EXPRESSION",
                    severity=Severity.ERROR,
                    message=f"rule {location} has an invalid expression",
                    line=rule.line,
                    detail=str(exc),
                )
            )
            continue

        if selector_has_regex_wildcard(rule.expr, allow_time_modifiers=has_modifier):
            findings.append(
                Finding(
                    rule_id="RULE_UNBOUNDED_REGEX",
                    severity=Severity.WARNING,
                    message=f"rule {location} uses a match-all regex selector",
                    line=rule.line,
                    detail="match-all matchers inflate series selection and cardinality",
                )
            )

        for seconds in _rate_windows(tokens):
            if seconds < _MIN_RATE_WINDOW_SECONDS:
                findings.append(
                    Finding(
                        rule_id="RULE_SHORT_RATE_WINDOW",
                        severity=Severity.WARNING,
                        message=f"rule {location} rate window is below 5m",
                        line=rule.line,
                        detail=f"window {format_duration(seconds)} is noise-sensitive",
                    )
                )
        if any(token.value == "rate" for token in tokens):
            label_names = {token.value for token in tokens if token.kind == "ident"}
            if not {"job", "namespace"} & label_names:
                findings.append(
                    Finding(
                        rule_id="RULE_UNSCOPED_SELECTOR",
                        severity=Severity.WARNING,
                        message=f"rule {location} selects series without job/namespace scope",
                        line=rule.line,
                    )
                )
    return tuple(findings)
