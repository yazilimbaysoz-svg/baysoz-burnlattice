"""A strict, dependency-free PromQL lexical analyser for SLO expressions.

The analyser deliberately supports the Prometheus expression subset that is
valid inside burn-rate alerts. It rejects time modifiers that would silently
misalign the two confirmation windows.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .attribution import MAX_EXPRESSION_CHARS

_UNIT_SECONDS = {
    "ms": Decimal("0.001"),
    "s": Decimal(1),
    "m": Decimal(60),
    "h": Decimal(3600),
    "d": Decimal(86400),
    "w": Decimal(604800),
}

_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)(ms|s|m|h|d|w)$")

_TOKEN_RE = re.compile(
    r"""
      (?P<ws>\s+)
    | (?P<duration>\d+(?:\.\d+)?(?:ms|s|m|h|d|w)\b)
    | (?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)
    | (?P<string>"(?:[^"\\\n]|\\.)*")
    | (?P<op>=~|!~|==|!=|>=|<=|=|>|<|\+|-|\*|/|\^|%)
    | (?P<punct>[(){}\[\],:])
    | (?P<ident>[a-zA-Z_][a-zA-Z0-9_]*)
    """,
    re.VERBOSE,
)

_PAIRS = {"(": ")", "{": "}", "[": "]"}
_FORBIDDEN_MODIFIERS = frozenset({"offset", "@"})


class PromQLError(ValueError):
    """Raised when an expression violates the supported safe subset."""


@dataclass(frozen=True, slots=True)
class Token:
    """One lexical token with its source offset."""

    kind: str
    value: str
    pos: int


def parse_duration(text: str) -> Decimal:
    """Convert a Prometheus duration literal into seconds."""
    match = _DURATION_RE.fullmatch(text)
    if match is None:
        raise PromQLError(f"invalid Prometheus duration: {text!r}")
    try:
        amount = Decimal(match.group(1))
    except InvalidOperation as exc:
        raise PromQLError(f"invalid duration magnitude: {text!r}") from exc
    return amount * _UNIT_SECONDS[match.group(2)]


def format_duration(seconds: Decimal | int) -> str:
    """Render seconds as a compact human-readable duration."""
    value = Decimal(seconds)
    for unit, divisor in (("d", Decimal(86400)), ("h", Decimal(3600)), ("m", Decimal(60))):
        if value >= divisor and value % divisor == 0:
            return f"{value // divisor}{unit}"
    return f"{value}s"


def tokenize(expression: str) -> tuple[Token, ...]:
    """Tokenize an expression, rejecting unsupported characters outright."""
    if not isinstance(expression, str):
        raise PromQLError("expression must be a string")
    if not expression.strip():
        raise PromQLError("expression must not be empty")
    if len(expression) > MAX_EXPRESSION_CHARS:
        raise PromQLError("expression exceeds the maximum supported length")
    if "#" in expression:
        raise PromQLError(" PromQL comments are not allowed in SLO rules".strip())

    tokens: list[Token] = []
    position = 0
    while position < len(expression):
        match = _TOKEN_RE.match(expression, position)
        if match is None:
            raise PromQLError(f"unsupported character at offset {position}")
        if match.start() != position:
            raise PromQLError(f"lexical gap at offset {position}")
        position = match.end()
        if match.lastgroup == "ws":
            continue
        kind = str(match.lastgroup)
        tokens.append(Token(kind=kind, value=match.group(), pos=match.start()))
    return tuple(tokens)


def validate(
    tokens: tuple[Token, ...], *, allow_time_modifiers: bool = False
) -> None:
    """Validate bracket structure, range selectors and time modifiers."""
    stack: list[str] = []
    for index, token in enumerate(tokens):
        if token.value in _PAIRS:
            stack.append(_PAIRS[token.value])
        elif token.value in {"}", ")", "]"}:
            if not stack or stack.pop() != token.value:
                raise PromQLError(f"unbalanced {token.value!r} at offset {token.pos}")
        if (
            not allow_time_modifiers
            and token.kind == "ident"
            and token.value in _FORBIDDEN_MODIFIERS
        ):
            raise PromQLError(f"time modifier {token.value!r} breaks window alignment")
        if token.value == "[":
            if index + 2 >= len(tokens):
                raise PromQLError("incomplete range selector")
            if tokens[index + 1].kind != "duration" or tokens[index + 2].value != "]":
                raise PromQLError("range selector requires exactly one duration literal")
    if stack:
        raise PromQLError(f"unclosed delimiter, expected {stack[-1]!r}")


def canonical(expression: str) -> str:
    """Return a whitespace-insensitive canonical token sequence."""
    tokens = tokenize(expression)
    validate(tokens)
    parts: list[str] = []
    for token in tokens:
        if token.kind == "number":
            parts.append(format(Decimal(token.value).normalize(), "f"))
        else:
            parts.append(token.value)
    return " ".join(parts)


def durations(expression: str) -> tuple[str, ...]:
    """Return every duration literal found in an expression."""
    tokens = tokenize(expression)
    validate(tokens)
    return tuple(token.value for token in tokens if token.kind == "duration")


def numbers(expression: str) -> tuple[Decimal, ...]:
    """Return every numeric literal found in an expression."""
    tokens = tokenize(expression)
    validate(tokens)
    return tuple(Decimal(token.value) for token in tokens if token.kind == "number")


def selector_has_regex_wildcard(
    expression: str, *, allow_time_modifiers: bool = False
) -> bool:
    """Detect a matcher that can match every series in a selector."""
    tokens = tokenize(expression)
    validate(tokens, allow_time_modifiers=allow_time_modifiers)
    for index, token in enumerate(tokens[:-1]):
        following = tokens[index + 1]
        if token.value in {"=~", "!~"} and following.kind == "string":
            value = following.value.strip('"')
            if value in {".*", ".+", "^.*$"} or value.startswith(".*"):
                return True
    return False
