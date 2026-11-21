"""Command-line interface for BurnLattice.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from .analyzer import analyze_rules
from .attribution import ATTRIBUTION, TOOL_NAME, VERSION
from .burnrate import BurnMathError, generate_rules, explanation_rows
from .drift import budget_reconciliation, verify_drift
from .model import Finding, Severity
from .promql import PromQLError, format_duration
from .report import Report, sorted_findings
from .rules import RulesError, parse_rules, read_rules, render_rules
from .spec import SpecError, load_contract

_DESCRIPTION = (
    "Deterministic SLO burn-rate policy compiler and CI drift gate. "
    "By Baysöz Labs <baysozlabs@proton.me>."
)
_EPILOG = (
    "BurnLattice performs strict multi-window multi-burn-rate arithmetic, "
    "compiles Prometheus alert rules, detects silent contract drift and emits "
    "SARIF for CI.\n"
    f"{ATTRIBUTION}"
)
_VERSION = f"{TOOL_NAME} {VERSION} - {ATTRIBUTION}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description=_DESCRIPTION,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=_VERSION)
    subcommands = parser.add_subparsers(dest="command", required=True)

    compile_cmd = subcommands.add_parser(
        "compile",
        help="compile an SLO contract into Prometheus alert rules",
        description=f"Compile an SLO contract. {ATTRIBUTION}",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    compile_cmd.add_argument("spec", help="path to an SLO contract JSON file")
    compile_cmd.add_argument("-o", "--output", help="write rules to this file")

    verify_cmd = subcommands.add_parser(
        "verify",
        help="verify deployed rules against a contract",
        description=f"Verify deployed rules against a contract. {ATTRIBUTION}",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    verify_cmd.add_argument("spec", help="path to an SLO contract JSON file")
    verify_cmd.add_argument("rules", help="path to a Prometheus rules YAML file")
    _add_report_options(verify_cmd)

    audit_cmd = subcommands.add_parser(
        "audit",
        help="audit Prometheus rules for production hazards",
        description=f"Audit Prometheus rules for production hazards. {ATTRIBUTION}",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    audit_cmd.add_argument("rules", help="path to a Prometheus rules YAML file")
    _add_report_options(audit_cmd)

    explain_cmd = subcommands.add_parser(
        "explain",
        help="show derived error-budget arithmetic",
        description=f"Show derived error-budget arithmetic. {ATTRIBUTION}",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    explain_cmd.add_argument("spec", help="path to an SLO contract JSON file")
    explain_cmd.add_argument(
        "--format", choices=("text", "json"), default="text", help="output format"
    )

    validate_cmd = subcommands.add_parser(
        "validate",
        help="validate an SLO contract without generating output",
        description=f"Validate an SLO contract. {ATTRIBUTION}",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    validate_cmd.add_argument("spec", help="path to an SLO contract JSON file")
    return parser


def _add_report_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("text", "json", "sarif"),
        default="text",
        help="report format (default: text)",
    )
    parser.add_argument(
        "--fail-on",
        choices=("error", "warning", "note"),
        default="error",
        help="minimum severity that fails the gate (default: error)",
    )
    parser.add_argument("-o", "--output", help="write report to this file")


def _emit(text: str, output: str | None) -> None:
    if output:
        Path(output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def _report_and_exit(
    command: str, source: str, findings: tuple[Finding, ...], args: argparse.Namespace
) -> int:
    report = Report(command=command, source=source, findings=sorted_findings(findings))
    _emit(report.render(args.format), args.output)
    return report.exit_code(Severity(args.fail_on))


def _explain(spec_path: str, format_name: str) -> int:
    contract = load_contract(spec_path)
    rows = explanation_rows(contract)
    if format_name == "json":
        payload = {
            "attribution": ATTRIBUTION,
            "tool": TOOL_NAME,
            "tool_version": VERSION,
            "service": contract.service,
            "slo": contract.name,
            "objective_percent": format(contract.objective.normalize(), "f"),
            "window": format_duration(contract.window_seconds),
            "error_budget_ratio": format(contract.error_budget.normalize(), "f"),
            "tiers": [
                {
                    "tier": row.tier.tier_id,
                    "channel": row.channel,
                    "burn_rate": format(row.tier.burn_rate.normalize(), "f"),
                    "short_window": row.tier.short,
                    "long_window": row.tier.long,
                    "error_threshold": format(row.threshold.normalize(), "f"),
                    "budget_pct_at_short": format(
                        row.budget_pct_at_short.quantize(Decimal("0.01")), "f"
                    ),
                    "time_to_exhaust": format_duration(row.time_to_exhaust_seconds),
                }
                for row in rows
            ],
        }
        _emit(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", None)
        return 0
    lines = [
        f"{TOOL_NAME} {VERSION} - {ATTRIBUTION}",
        f"contract: {contract.service}/{contract.name}",
        f"objective: {contract.objective}% | window: "
        f"{format_duration(contract.window_seconds)} | "
        f"error budget: {format(contract.error_budget.normalize(), 'f')}",
        "",
        f"{'tier':<14} {'channel':<8} {'burn':>6} {'short':>6} {'long':>6} "
        f"{'threshold':>12} {'budget@short':>13} {'exhaust':>9}",
    ]
    for row in rows:
        lines.append(
            f"{row.tier.tier_id:<14} {row.channel:<8} "
            f"{format(row.tier.burn_rate.normalize(), 'f'):>6} "
            f"{row.tier.short:>6} {row.tier.long:>6} "
            f"{format(row.threshold.normalize(), 'f'):>12} "
            f"{format(row.budget_pct_at_short.quantize(Decimal('0.01')), 'f') + '%':>13} "
            f"{format_duration(row.time_to_exhaust_seconds):>9}"
        )
    lines.extend(["", "long-window confirmation is implicit in each tier.", ATTRIBUTION])
    _emit("\n".join(lines) + "\n", None)
    return 0


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "compile":
        contract = load_contract(args.spec)
        _emit(render_rules(contract, generate_rules(contract)), args.output)
        return 0
    if args.command == "verify":
        contract = load_contract(args.spec)
        text, source = read_rules(args.rules)
        actual = parse_rules(text, source)
        findings = (
            verify_drift(contract, generate_rules(contract), actual, source)
            + budget_reconciliation(actual)
            + analyze_rules(actual)
        )
        return _report_and_exit("verify", source, findings, args)
    if args.command == "audit":
        text, source = read_rules(args.rules)
        actual = parse_rules(text, source)
        findings = analyze_rules(actual) + budget_reconciliation(actual)
        return _report_and_exit("audit", source, findings, args)
    if args.command == "explain":
        return _explain(args.spec, args.format)
    contract = load_contract(args.spec)
    _emit(
        f"contract OK: {contract.service}/{contract.name} "
        f"(objective {contract.objective}%, window "
        f"{format_duration(contract.window_seconds)}) - {ATTRIBUTION}\n",
        None,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the BurnLattice CLI and return a process exit code."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except (SpecError, RulesError, PromQLError, BurnMathError, OSError, ValueError) as exc:
        print(f"{TOOL_NAME}: error: {exc}", file=sys.stderr)
        return 2
