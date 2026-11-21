"""End-to-end CLI tests.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from burnlattice.burnrate import generate_rules
from burnlattice.cli import main
from burnlattice.rules import render_rules
from burnlattice.spec import load_contract
from tests.helpers import check, example

_SPEC = example("checkout-availability.json")


def _clean_rules(destination: Path) -> Path:
    contract = load_contract(_SPEC)
    destination.write_text(render_rules(contract, generate_rules(contract)), encoding="utf-8")
    return destination


def test_version_has_attribution(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    check(exit_info.value.code == 0, "version command failed")
    output = capsys.readouterr().out
    check("Baysöz Labs <baysozlabs@proton.me>" in output, "version lacks attribution")


def test_help_has_attribution(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    check(exit_info.value.code == 0, "help command failed")
    output = capsys.readouterr().out
    check("Baysöz Labs <baysozlabs@proton.me>" in output, "help lacks attribution")
    check("SLO burn-rate policy compiler" in output, "help lacks description")
    check("compile" in output and "verify" in output and "audit" in output, "subcommands missing")


def test_compile_writes_real_rules(tmp_path: Path) -> None:
    output = tmp_path / "rules.yml"
    check(main(["compile", str(_SPEC), "-o", str(output)]) == 0, "compile failed")
    text = output.read_text(encoding="utf-8")
    check("CheckoutAvailabilityBurnFast1h6h" in text, "compiled alert missing")
    check("Baysöz Labs <baysozlabs@proton.me>" in text, "compiled rules lack attribution")


def test_validate_and_explain(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    check(main(["validate", str(_SPEC)]) == 0, "validate failed")
    check("contract OK" in capsys.readouterr().out, "validate output missing")
    check(main(["explain", str(_SPEC)]) == 0, "explain failed")
    text = capsys.readouterr().out
    check("14.4" in text and "0.0144" in text, "explain math missing")
    check(main(["explain", str(_SPEC), "--format", "json"]) == 0, "explain json failed")
    payload = json.loads(capsys.readouterr().out)
    check(payload["tiers"][0]["error_threshold"] == "0.0144", "explain json math wrong")
    unused = tmp_path
    check(unused.exists(), "temp path should exist")


def test_verify_clean_and_drifted(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rules = _clean_rules(tmp_path / "rules.yml")
    sarif = tmp_path / "report.sarif"
    check(
        main(["verify", str(_SPEC), str(rules), "--format", "sarif", "-o", str(sarif)]) == 0,
        "clean verification failed",
    )
    document = json.loads(sarif.read_text(encoding="utf-8"))
    check(document["runs"][0]["results"] == [], "clean report has findings")
    drifted = tmp_path / "drifted.yml"
    drifted.write_text(rules.read_text(encoding="utf-8").replace("[1h]", "[5m]"), encoding="utf-8")
    check(main(["verify", str(_SPEC), str(drifted), "-o", str(tmp_path / "out.txt")]) == 1,
          "drift was not detected")
    check("SLO_DRIFT_EXPRESSION" in (tmp_path / "out.txt").read_text(encoding="utf-8"),
          "drift finding missing")
    capsys.readouterr()


def test_audit_hazard_fails_gate(tmp_path: Path) -> None:
    rules = _clean_rules(tmp_path / "rules.yml")
    rules.write_text(
        rules.read_text(encoding="utf-8").replace("[1h]", "[1h] offset 5m"), encoding="utf-8"
    )
    check(main(["audit", str(rules), "--fail-on", "error"]) == 1, "hazard did not fail gate")


def test_invalid_input_returns_two(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    check(main(["validate", str(broken)]) == 2, "invalid contract did not return exit 2")
    missing = tmp_path / "missing.yml"
    check(main(["audit", str(missing)]) == 2, "missing file did not return exit 2")
