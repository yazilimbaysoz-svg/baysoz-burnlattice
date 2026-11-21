"""PromQL lexer and duration tests.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.helpers import check

from burnlattice.promql import (
    PromQLError,
    canonical,
    durations,
    format_duration,
    parse_duration,
    selector_has_regex_wildcard,
    tokenize,
    validate,
)

_EXPRESSION = (
    '(sum(rate(http_requests_total{job="checkout-api",status=~"2.."}[1h])) / '
    'sum(rate(http_requests_total{job="checkout-api"}[1h])) > 0.0144) and '
    '(sum(rate(http_requests_total{job="checkout-api",status=~"2.."}[6h])) / '
    'sum(rate(http_requests_total{job="checkout-api"}[6h])) > 0.0144)'
)


def test_tokens_are_produced() -> None:
    tokens = tokenize(_EXPRESSION)
    validate(tokens)
    check(len(tokens) > 40, "expected a rich token stream")


def test_canonical_ignores_whitespace_and_number_spelling() -> None:
    other = _EXPRESSION.replace(" > 0.0144", "    >  0.01440").replace(") and (", ")and(")
    check(canonical(other) == canonical(_EXPRESSION), "canonicalization is unstable")


def test_durations_are_extracted() -> None:
    check(durations(_EXPRESSION) == ("1h", "1h", "6h", "6h"), "wrong durations")


def test_duration_conversion() -> None:
    check(parse_duration("30d") == Decimal(2592000), "30d conversion failed")
    check(parse_duration("500ms") == Decimal("0.5"), "milliseconds failed")
    check(format_duration(86400) == "1d", "day formatting failed")
    check(format_duration(7200) == "2h", "hour formatting failed")


@pytest.mark.parametrize(
    "expression",
    [
        "sum(rate(foo[5m])",
        'sum(rate(foo{job="x"}[5m])) # comment',
        'sum(rate(foo[5m] offset 1h))',
        'sum(rate(foo[5m])) @ 1234',
        "sum(rate(foo[5m])) $",
        "sum(rate(foo[]))",
        "sum(rate(foo[5m])) }",
    ],
)
def test_unsafe_expressions_are_rejected(expression: str) -> None:
    with pytest.raises(PromQLError):
        canonical(expression)


def test_wildcard_regex_is_detected() -> None:
    check(selector_has_regex_wildcard('sum(rate(foo{job=~".*"}[5m]))'), "wildcard missed")
    check(not selector_has_regex_wildcard('sum(rate(foo{job="api"}[5m]))'), "false positive")


def test_oversized_expression_is_rejected() -> None:
    with pytest.raises(PromQLError, match="maximum supported length"):
        tokenize("up" * 12000)
