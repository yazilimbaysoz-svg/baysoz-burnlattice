# Plan — BurnLattice

Baysöz Labs <baysozlabs@proton.me>

## Phase 1 — Research (complete)

- Inspected the existing portfolio to exclude redundant ideas.
- Mined live GitHub trends with `gh search repos` and open issues with `gh search issues`.
- Identified SLO arithmetic and policy drift as an uncovered, high-impact gap.
- Recorded evidence and differentiation in `docs/MARKET_RESEARCH.md`.

## Phase 2 — Design (complete)

- Froze the contract schema, tier definitions and multi-window expression shape.
- Chose Python 3.13, `uv`, PyYAML and a standard-library-only lexer/reporting stack.
- Defined deterministic exit codes: 0 clean, 1 gate violation, 2 invalid input.
- Defined the threat model in `SECURITY.md` and module boundaries in `docs/ARCHITECTURE.md`.

## Phase 3 — Implementation (complete)

- Strict contract validation and semantic subset checks.
- Exact `Decimal` burn-rate compiler with deterministic YAML emission.
- Drift detection, standalone hazard analysis and budget reconciliation.
- SARIF 2.1.0, JSON and text reports with stable digests.
- Five subcommands: `compile`, `verify`, `audit`, `explain`, `validate`.

## Phase 4 — Verification (complete)

- `uv venv && uv pip install -e . && uv pip install pytest`
- `uv run pytest -q`
- `ruff check --select E,F,W,S,B .`
- `semgrep --config p/default --error .`
- Adversarial live execution of CLI and library APIs.
- Supreme Grand Jury Tribunal verdict: **UNANIMOUS PASS (6/6 jurors)**.
  Live checks covered exact burn arithmetic, clean versus hand-drifted rules (exit 0/1),
  six adversarial hazard classes, SARIF determinism, injection rejection, anti-stub
  source audit and attribution across 61 public files.

## Phase 5 — Release (complete)

- Public repository under `yazilimbaysoz-svg` with crisp description and topics.
- Showcase metadata written to the single designated `.factory-result.json`.

Baysöz Labs <baysozlabs@proton.me>
