"""Multi-window multi-burn-rate arithmetic and Prometheus rule synthesis.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

from decimal import Decimal

from .attribution import ATTRIBUTION
from .model import BurnMath, BurnTier, Matcher, Rule, SloContract
from .promql import format_duration, parse_duration

TIERS: dict[str, BurnTier] = {
    "fast_1h_6h": BurnTier("fast_1h_6h", Decimal("14.4"), "1h", "6h", "Fast1h6h"),
    "fast_6h_1d": BurnTier("fast_6h_1d", Decimal("6"), "6h", "1d", "Fast6h1d"),
    "slow_1d_3d": BurnTier("slow_1d_3d", Decimal("3"), "1d", "3d", "Slow1d3d"),
    "slow_3d_30d": BurnTier("slow_3d_30d", Decimal("1"), "3d", "30d", "Slow3d30d"),
}


class BurnMathError(ValueError):
    """Raised when burn-rate arithmetic is not meaningful for a contract."""


def tier_math(contract: SloContract, tier: BurnTier, channel: str) -> BurnMath:
    """Derive the decision threshold and budget accounting for one tier."""
    if tier.burn_rate <= 0:
        raise BurnMathError("burn rate must be positive")
    short = parse_duration(tier.short)
    confirmation = parse_duration(tier.long)
    if not short < confirmation:
        raise BurnMathError(f"tier {tier.tier_id} short window must be shorter than long")
    if confirmation > contract.window_seconds:
        raise BurnMathError(f"tier {tier.tier_id} exceeds the SLO window")
    threshold = tier.burn_rate * contract.error_budget
    if threshold <= 0 or threshold > 1:
        raise BurnMathError(f"tier {tier.tier_id} produces an impossible error threshold")
    consumed = tier.burn_rate * (short / Decimal(contract.window_seconds)) * Decimal(100)
    return BurnMath(
        tier=tier,
        channel=channel,
        threshold=threshold,
        budget_pct_at_short=consumed,
        time_to_exhaust_seconds=Decimal(contract.window_seconds) / tier.burn_rate,
        confirmation_seconds=confirmation,
    )


def _selector(metric: str, matchers: tuple[Matcher, ...]) -> str:
    if not matchers:
        return metric
    body = ",".join(matcher.render() for matcher in matchers)
    return f"{metric}{{{body}}}"


def _rate_term(metric: str, matchers: tuple[Matcher, ...], window: str) -> str:
    return f"sum(rate({_selector(metric, matchers)}[{window}]))"


def _expression(contract: SloContract, math: BurnMath, window: str) -> str:
    sli = contract.sli
    threshold = format(math.threshold.normalize(), "f")
    good = _rate_term(sli.good_metric, sli.good_matchers, window)
    total = _rate_term(sli.total_metric, sli.total_matchers, window)
    return f"({good} / {total} > {threshold})"


def generate_rules(contract: SloContract) -> tuple[Rule, ...]:
    """Compile every contracted burn tier into a deterministic alert rule."""
    severity_by_channel = contract.severity_dict
    rules: list[Rule] = []
    for channel, tier_ids in contract.tiers_by_channel:
        for tier_id in tier_ids:
            tier = TIERS[tier_id]
            math = tier_math(contract, tier, channel)
            expression = (
                f"{_expression(contract, math, tier.short)} and "
                f"{_expression(contract, math, tier.long)}"
            )
            name = f"{contract.name.title().replace('_', '')}Burn{tier.suffix}"
            threshold = format(math.threshold.normalize(), "f")
            labels: tuple[tuple[str, str], ...] = (
                (("severity", severity_by_channel[channel]),)
                + contract.labels
                + (
                    ("service", contract.service),
                    ("slo", contract.name),
                    ("channel", channel),
                    ("burn_rate", format(tier.burn_rate.normalize(), "f")),
                )
            )
            annotations: tuple[tuple[str, str], ...] = (
                ("attribution", ATTRIBUTION),
                ("slo", f"{contract.service}/{contract.name}"),
                ("objective", f"{contract.objective}%"),
                ("slo_window", format_duration(contract.window_seconds)),
                ("burn_rate", format(tier.burn_rate.normalize(), "f")),
                ("error_threshold", threshold),
                (
                    "summary",
                    f"SLO {contract.name} burning at {tier.burn_rate}x over "
                    f"{tier.short}/{tier.long}",
                ),
                (
                    "description",
                    f"Error ratio exceeded {threshold} across {tier.short} and "
                    f"{tier.long}; {math.budget_pct_at_short.quantize(Decimal('0.01'))}% "
                    f"of the {format_duration(contract.window_seconds)} error budget "
                    "consumed at detection",
                ),
            )
            rules.append(
                Rule(
                    group=f"slo-{contract.service}",
                    kind="alert",
                    name=name,
                    expr=expression,
                    for_time="2m" if channel == "page" else "5m",
                    labels=tuple(sorted(labels)),
                    annotations=tuple(sorted(annotations)),
                )
            )
    return tuple(rules)


def explanation_rows(contract: SloContract) -> tuple[BurnMath, ...]:
    """Return derived burn arithmetic in compilation order."""
    rows: list[BurnMath] = []
    for channel, tier_ids in contract.tiers_by_channel:
        for tier_id in tier_ids:
            rows.append(tier_math(contract, TIERS[tier_id], channel))
    return tuple(rows)
