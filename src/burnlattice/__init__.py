"""BurnLattice - deterministic SLO burn-rate compiler and drift gate.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

from .attribution import ATTRIBUTION, SCHEMA_VERSION, TOOL_NAME, VERSION
from .analyzer import analyze_rules
from .burnrate import TIERS, BurnMathError, explanation_rows, generate_rules, tier_math
from .drift import budget_reconciliation, verify_drift
from .model import BurnMath, BurnTier, Finding, Rule, Severity, SliSpec, SloContract
from .promql import PromQLError, canonical, parse_duration, tokenize
from .report import Report, sorted_findings
from .rules import RulesError, parse_rules, render_rules
from .sarif import to_sarif
from .spec import SpecError, contract_from_mapping, load_contract

__all__ = [
    "ATTRIBUTION",
    "SCHEMA_VERSION",
    "TOOL_NAME",
    "VERSION",
    "TIERS",
    "BurnMath",
    "BurnMathError",
    "BurnTier",
    "Finding",
    "PromQLError",
    "Report",
    "Rule",
    "RulesError",
    "Severity",
    "SliSpec",
    "SloContract",
    "SpecError",
    "analyze_rules",
    "budget_reconciliation",
    "canonical",
    "contract_from_mapping",
    "explanation_rows",
    "generate_rules",
    "load_contract",
    "parse_duration",
    "parse_rules",
    "render_rules",
    "sorted_findings",
    "tier_math",
    "to_sarif",
    "tokenize",
    "verify_drift",
]
