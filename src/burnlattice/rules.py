"""Prometheus rule-file parsing and deterministic YAML emission.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .attribution import ATTRIBUTION, MAX_INPUT_BYTES, TOOL_NAME, VERSION
from .model import Rule, SloContract
from .promql import parse_duration

_RULE_KEYS = frozenset(
    {"alert", "record", "expr", "for", "keep_firing_for", "labels", "annotations"}
)


class RulesError(ValueError):
    """Raised when a Prometheus rule file is malformed."""


def find_line(text: str, needle: str) -> int:
    """Return the first 1-based line containing a needle, or zero."""
    for index, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return index
    return 0


def _locate_rule(text: str, kind: str, name: str) -> int:
    for anchor in (f"{kind}: '{name}'", f'{kind}: "{name}"', f"{kind}: {name}"):
        line = find_line(text, anchor)
        if line:
            return line
    return 0


def read_rules(path: str | Path) -> tuple[str, str]:
    """Read a UTF-8 rule file with a bounded size and return text plus path."""
    source = Path(path)
    payload = source.read_bytes()
    if len(payload) > MAX_INPUT_BYTES:
        raise RulesError("rule file exceeds the maximum supported size")
    try:
        return payload.decode("utf-8"), str(source)
    except UnicodeDecodeError as exc:
        raise RulesError("rule file is not valid UTF-8") from exc


def _string_map(value: Any, field: str) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise RulesError(f"{field} must be a mapping")
    result: list[tuple[str, str]] = []
    for key in sorted(value):
        if not isinstance(key, str) or not isinstance(value[key], str):
            raise RulesError(f"{field} keys and values must be strings")
        result.append((key, value[key]))
    return tuple(result)


def parse_rules(text: str, source: str = "") -> tuple[Rule, ...]:
    """Parse and structurally validate a Prometheus rule file."""
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RulesError(f"invalid YAML: {exc}") from exc
    if document is None:
        return ()
    if not isinstance(document, dict) or not isinstance(document.get("groups"), list):
        raise RulesError("rule file must contain a 'groups' list")

    rules: list[Rule] = []
    for group_index, group in enumerate(document["groups"]):
        if not isinstance(group, dict):
            raise RulesError(f"groups[{group_index}] must be a mapping")
        group_name = group.get("name")
        if not isinstance(group_name, str) or not group_name:
            raise RulesError(f"groups[{group_index}].name must be a non-empty string")
        raw_rules = group.get("rules")
        if not isinstance(raw_rules, list):
            raise RulesError(f"group {group_name} must contain a 'rules' list")
        for rule_index, raw in enumerate(raw_rules):
            if not isinstance(raw, dict):
                raise RulesError(f"group {group_name} rules[{rule_index}] must be a mapping")
            extra = set(raw) - _RULE_KEYS
            if extra:
                raise RulesError(f"unsupported rule fields: {', '.join(sorted(extra))}")
            has_alert, has_record = "alert" in raw, "record" in raw
            if has_alert == has_record:
                raise RulesError("each rule must define exactly one of alert or record")
            kind = "alert" if has_alert else "record"
            name = raw[kind]
            if not isinstance(name, str) or not name:
                raise RulesError(f"rule {kind} name must be a non-empty string")
            expression = raw.get("expr")
            if not isinstance(expression, str) or not expression.strip():
                raise RulesError(f"rule {name} must have a non-empty expr")
            for_time = raw.get("for")
            if for_time is not None:
                if not isinstance(for_time, str):
                    raise RulesError(f"rule {name} 'for' must be a duration string")
                parse_duration(for_time)
            keep_firing = raw.get("keep_firing_for")
            if keep_firing is not None:
                if not isinstance(keep_firing, str):
                    raise RulesError(f"rule {name} 'keep_firing_for' must be a duration string")
                parse_duration(keep_firing)
            rules.append(
                Rule(
                    group=group_name,
                    kind=kind,
                    name=name,
                    expr=expression,
                    for_time=for_time,
                    labels=_string_map(raw.get("labels"), f"rule {name} labels"),
                    annotations=_string_map(
                        raw.get("annotations"), f"rule {name} annotations"
                    ),
                    line=_locate_rule(text, kind, name),
                    keep_firing_for=keep_firing,
                )
            )
    return tuple(rules)


def _quoted(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_rules(contract: SloContract, rules: tuple[Rule, ...]) -> str:
    """Render rules as stable, review-friendly Prometheus YAML."""
    lines = [
        f"# Generated by {TOOL_NAME} {VERSION}",
        f"# {ATTRIBUTION}",
        f"# Contract: {contract.service}/{contract.name}",
        "groups:",
    ]
    groups: dict[str, list[Rule]] = {}
    for rule in rules:
        groups.setdefault(rule.group, []).append(rule)
    for group_name in sorted(groups):
        lines.append(f"  - name: {_quoted(group_name)}")
        lines.append("    rules:")
        for rule in groups[group_name]:
            lines.append(f"      - {rule.kind}: {_quoted(rule.name)}")
            lines.append(f"        expr: {_quoted(rule.expr)}")
            if rule.for_time is not None:
                lines.append(f"        for: {rule.for_time}")
            if rule.keep_firing_for is not None:
                lines.append(f"        keep_firing_for: {rule.keep_firing_for}")
            for section, values in (("labels", rule.labels), ("annotations", rule.annotations)):
                if not values:
                    continue
                lines.append(f"        {section}:")
                for key, value in sorted(values):
                    lines.append(f"          {key}: {_quoted(value)}")
    return "\n".join(lines) + "\n"
