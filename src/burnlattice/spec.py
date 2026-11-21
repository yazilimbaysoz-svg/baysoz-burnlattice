"""Strict validation and loading of backend-neutral SLO contracts.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .attribution import MAX_INPUT_BYTES
from .burnrate import TIERS
from .model import Matcher, SliSpec, SloContract
from .promql import parse_duration

_IDENT_RE = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")
_SLO_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_METRIC_RE = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]{0,127}$")
_LABEL_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
_WINDOW_RE = re.compile(r"^\d+(?:m|h|d|w)$")
_FORBIDDEN_VALUE_CHARS = frozenset({'"', "\n", "\r", "\x00", "{", "}", "#"})
_ALLOWED_SEVERITIES = frozenset({"critical", "warning", "info"})
CHANNELS = ("page", "ticket")


class SpecError(ValueError):
    """Raised when a contract is malformed or semantically invalid."""


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SpecError(f"{field} must be an object")
    return value


def _text(value: Any, field: str, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value:
        raise SpecError(f"{field} must be a non-empty string")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise SpecError(f"{field} has an invalid format: {value!r}")
    return value


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise SpecError(f"{field} must be a number")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise SpecError(f"{field} must be a valid decimal number") from exc
    if not result.is_finite():
        raise SpecError(f"{field} must be finite")
    return result


def _label_value(value: Any, field: str, allow_regex: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise SpecError(f"{field} must be a non-empty string of at most 256 characters")
    if any(char in _FORBIDDEN_VALUE_CHARS for char in value):
        raise SpecError(f"{field} contains a forbidden character")
    if not allow_regex and "\\" in value:
        raise SpecError(f"{field} contains an invalid escape")
    return value


def _matchers(raw: Any, field: str) -> tuple[Matcher, ...]:
    if raw is None:
        return ()
    mapping = _mapping(raw, field)
    result: list[Matcher] = []
    for label in sorted(mapping):
        _text(label, f"{field} label", _LABEL_RE)
        if label == "__name__":
            raise SpecError(f"{field} must not select on __name__")
        value = mapping[label]
        if not isinstance(value, str):
            raise SpecError(f"{field}.{label} must be a string")
        if value.startswith("!~"):
            operator, actual = "!~", value[2:]
        elif value.startswith("~"):
            operator, actual = "=~", value[1:]
        elif value.startswith("!"):
            operator, actual = "!=", value[1:]
        else:
            operator, actual = "=", value
        _label_value(actual, f"{field}.{label}", operator in {"=~", "!~"})
        result.append(Matcher(label=label, value=actual, operator=operator))
    if not result:
        raise SpecError(f"{field} must contain at least one matcher")
    return tuple(result)


def _labels(raw: Any) -> tuple[tuple[str, str], ...]:
    if raw is None:
        return ()
    mapping = _mapping(raw, "labels")
    if len(mapping) > 8:
        raise SpecError("labels must contain at most 8 entries")
    result: list[tuple[str, str]] = []
    for label in sorted(mapping):
        _text(label, "labels key", _LABEL_RE)
        if label == "__name__":
            raise SpecError("labels must not contain __name__")
        result.append((label, _label_value(mapping[label], f"labels.{label}")))
    return tuple(result)


def _sli(raw: Any, window_seconds: int) -> SliSpec:
    mapping = _mapping(raw, "slo.sli")
    kind = _text(mapping.get("type"), "slo.sli.type")
    matchers = _matchers(mapping.get("matchers"), "slo.sli.matchers")
    if kind == "ratio":
        good = _mapping(mapping.get("good"), "slo.sli.good")
        total = _mapping(mapping.get("total"), "slo.sli.total")
        good_metric = _text(good.get("metric"), "slo.sli.good.metric", _METRIC_RE)
        total_metric = _text(total.get("metric"), "slo.sli.total.metric", _METRIC_RE)
        if good_metric != total_metric:
            raise SpecError("ratio SLI good and total must use the same metric")
        if good.get("op", "rate") != "rate" or total.get("op", "rate") != "rate":
            raise SpecError("only the rate() operator is supported for ratio SLIs")
        good_matchers = _matchers(good.get("matchers"), "slo.sli.good.matchers")
        total_matchers = _matchers(total.get("matchers"), "slo.sli.total.matchers")
        good_pairs = {(m.label, m.value, m.operator) for m in good_matchers}
        total_pairs = {(m.label, m.value, m.operator) for m in total_matchers}
        if not total_pairs < good_pairs:
            raise SpecError("good selector must be strictly more restrictive than total")
        return SliSpec(
            kind=kind,
            good_metric=good_metric,
            good_matchers=good_matchers,
            total_metric=total_metric,
            total_matchers=total_matchers,
        )
    if kind == "latency":
        metric = _text(mapping.get("metric"), "slo.sli.metric", _METRIC_RE)
        if metric.endswith(("_bucket", "_count", "_sum")):
            raise SpecError("latency SLI metric must be the histogram base name")
        threshold = _decimal(mapping.get("threshold_ms"), "slo.sli.threshold_ms")
        if threshold <= 0:
            raise SpecError("slo.sli.threshold_ms must be positive")
        le = (threshold / Decimal(1000)).normalize()
        le_text = format(le, "f")
        good_matchers = matchers + (Matcher(label="le", value=le_text),)
        return SliSpec(
            kind=kind,
            good_metric=f"{metric}_bucket",
            good_matchers=good_matchers,
            total_metric=f"{metric}_count",
            total_matchers=matchers,
            threshold_ms=threshold,
        )
    raise SpecError("slo.sli.type must be 'ratio' or 'latency'")


def _alerting(raw: Any, window_seconds: int) -> tuple[
    tuple[tuple[str, tuple[str, ...]], ...], tuple[tuple[str, str], ...]
]:
    mapping = _mapping(raw, "slo.alerting")
    tiers: list[tuple[str, tuple[str, ...]]] = []
    severities: list[tuple[str, str]] = []
    used: set[str] = set()
    for channel in CHANNELS:
        config = _mapping(mapping.get(channel), f"slo.alerting.{channel}")
        severity = _text(config.get("severity"), f"slo.alerting.{channel}.severity")
        if severity not in _ALLOWED_SEVERITIES:
            raise SpecError(f"unsupported severity for {channel} channel: {severity}")
        raw_tiers = config.get("tiers")
        if not isinstance(raw_tiers, list) or not raw_tiers:
            raise SpecError(f"slo.alerting.{channel}.tiers must be a non-empty list")
        selected: list[str] = []
        for item in raw_tiers:
            tier_id = _text(item, f"slo.alerting.{channel}.tiers entry")
            if tier_id not in TIERS:
                raise SpecError(f"unknown burn tier: {tier_id}")
            if tier_id in used:
                raise SpecError(f"burn tier {tier_id} is assigned to more than one channel")
            if parse_duration(TIERS[tier_id].long) > window_seconds:
                raise SpecError(f"tier {tier_id} needs a window longer than the SLO window")
            used.add(tier_id)
            selected.append(tier_id)
        if channel == "page" and not any(TIERS[item].burn_rate >= 6 for item in selected):
            raise SpecError("page channel must include at least one fast burn tier (rate >= 6)")
        if channel == "ticket" and not any(TIERS[item].burn_rate <= 3 for item in selected):
            raise SpecError("ticket channel must include at least one slow burn tier (rate <= 3)")
        tiers.append((channel, tuple(selected)))
        severities.append((channel, severity))
    return tuple(tiers), tuple(severities)


def contract_from_mapping(data: Any) -> SloContract:
    """Validate a decoded contract mapping and build an immutable contract."""
    root = _mapping(data, "contract")
    if root.get("schema_version") != "1.0":
        raise SpecError("schema_version must be '1.0'")
    if "attribution" in root:
        attribution = _text(root["attribution"], "attribution")
        if "Baysöz Labs" not in attribution or "baysozlabs@proton.me" not in attribution:
            raise SpecError("attribution must credit Baysöz Labs <baysozlabs@proton.me>")

    service = _text(root.get("service"), "service", _IDENT_RE)
    slo = _mapping(root.get("slo"), "slo")
    name = _text(slo.get("name"), "slo.name", _SLO_NAME_RE)
    objective = _decimal(slo.get("objective"), "slo.objective")
    if not Decimal(0) < objective < Decimal(100):
        raise SpecError("slo.objective must be strictly between 0 and 100")
    if objective.as_tuple().exponent < -6:
        raise SpecError("slo.objective must not have more than 6 decimal places")

    window_text = _text(slo.get("window"), "slo.window", _WINDOW_RE)
    window_seconds = int(parse_duration(window_text))
    if window_seconds < 3600 or window_seconds > 365 * 86400:
        raise SpecError("slo.window must be between 1h and 365d")

    sli = _sli(slo.get("sli"), window_seconds)
    tiers, severities = _alerting(slo.get("alerting"), window_seconds)
    description = root.get("description", "")
    if not isinstance(description, str) or len(description) > 500:
        raise SpecError("description must be a string of at most 500 characters")

    return SloContract(
        service=service,
        name=name,
        objective=objective,
        window_seconds=window_seconds,
        sli=sli,
        labels=_labels(root.get("labels")),
        tiers_by_channel=tiers,
        severity_by_channel=severities,
        description=description,
    )


def load_contract(path: str | Path) -> SloContract:
    """Read and validate an SLO contract from a UTF-8 JSON file."""
    source = Path(path)
    payload = source.read_bytes()
    if len(payload) > MAX_INPUT_BYTES:
        raise SpecError("contract file exceeds the maximum supported size")
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpecError(f"contract is not valid UTF-8 JSON: {exc}") from exc
    return contract_from_mapping(data)
