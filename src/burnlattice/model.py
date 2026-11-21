"""Immutable domain model for SLO contracts, burn tiers and findings.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Severity(StrEnum):
    """Ordered finding severities used by every gate."""

    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"

    @property
    def rank(self) -> int:
        """Return the numeric rank used for threshold comparisons."""
        return {Severity.NOTE: 0, Severity.WARNING: 1, Severity.ERROR: 2}[self]


@dataclass(frozen=True, slots=True)
class Matcher:
    """A single PromQL label matcher."""

    label: str
    value: str
    operator: str = "="

    def render(self) -> str:
        """Render the matcher in PromQL selector syntax."""
        return f'{self.label}{self.operator}"{self.value}"'


@dataclass(frozen=True, slots=True)
class SliSpec:
    """Materialised good/total series pair for one service-level indicator."""

    kind: str
    good_metric: str
    good_matchers: tuple[Matcher, ...]
    total_metric: str
    total_matchers: tuple[Matcher, ...]
    threshold_ms: Decimal | None = None


@dataclass(frozen=True, slots=True)
class SloContract:
    """Validated, backend-neutral SLO contract."""

    service: str
    name: str
    objective: Decimal
    window_seconds: int
    sli: SliSpec
    labels: tuple[tuple[str, str], ...]
    tiers_by_channel: tuple[tuple[str, tuple[str, ...]], ...]
    severity_by_channel: tuple[tuple[str, str], ...]
    description: str = ""

    @property
    def labels_dict(self) -> dict[str, str]:
        """Return labels as an insertion-ordered mapping."""
        return dict(self.labels)

    @property
    def tiers_dict(self) -> dict[str, tuple[str, ...]]:
        """Return channel to burn-tier identifier mapping."""
        return dict(self.tiers_by_channel)

    @property
    def severity_dict(self) -> dict[str, str]:
        """Return channel to Prometheus severity mapping."""
        return dict(self.severity_by_channel)

    @property
    def error_budget(self) -> Decimal:
        """Return the allowed error ratio (for example 0.001 for 99.9%)."""
        return (Decimal(100) - self.objective) / Decimal(100)


@dataclass(frozen=True, slots=True)
class BurnTier:
    """One multi-window multi-burn-rate alert tier."""

    tier_id: str
    burn_rate: Decimal
    short: str
    long: str
    suffix: str


@dataclass(frozen=True, slots=True)
class BurnMath:
    """Derived error-budget arithmetic for one tier."""

    tier: BurnTier
    channel: str
    threshold: Decimal
    budget_pct_at_short: Decimal
    time_to_exhaust_seconds: Decimal
    confirmation_seconds: Decimal


@dataclass(frozen=True, slots=True)
class Rule:
    """A Prometheus alerting or recording rule parsed from YAML."""

    group: str
    kind: str
    name: str
    expr: str
    for_time: str | None = None
    labels: tuple[tuple[str, str], ...] = ()
    annotations: tuple[tuple[str, str], ...] = ()
    line: int = 0
    keep_firing_for: str | None = None

    @property
    def labels_dict(self) -> dict[str, str]:
        """Return rule labels as a mapping."""
        return dict(self.labels)

    @property
    def annotations_dict(self) -> dict[str, str]:
        """Return rule annotations as a mapping."""
        return dict(self.annotations)


@dataclass(frozen=True, slots=True)
class Finding:
    """A deterministic, reportable gate finding."""

    rule_id: str
    severity: Severity
    message: str
    path: str = ""
    line: int = 0
    detail: str = ""

    @property
    def sort_key(self) -> tuple[int, str, str, int, str, str]:
        """Return a stable ordering key for reports."""
        return (
            -self.severity.rank,
            self.rule_id,
            self.path,
            self.line,
            self.message,
            self.detail,
        )

    def to_dict(self) -> dict[str, object]:
        """Return the portable JSON representation."""
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "path": self.path,
            "line": self.line,
            "detail": self.detail,
        }
