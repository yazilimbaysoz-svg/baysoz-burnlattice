"""Test helpers without bare assert statements.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def check(condition: bool, message: str) -> None:
    """Fail a test with an explicit diagnostic."""
    if not condition:
        raise AssertionError(message)


def example(name: str) -> Path:
    """Return the path of a repository example fixture."""
    return PROJECT_ROOT / "examples" / name
