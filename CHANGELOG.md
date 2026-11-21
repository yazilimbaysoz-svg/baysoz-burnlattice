# Changelog — BurnLattice

Baysöz Labs <baysozlabs@proton.me>

All notable changes to this project are documented here. The format follows
Keep a Changelog and the project adheres to Semantic Versioning.

## 1.0.0 — 2026-11-21

### Added

- Strict backend-neutral SLO contract schema with semantic selector validation.
- Exact `Decimal` multi-window multi-burn-rate arithmetic for four production tiers.
- Deterministic Prometheus rule compiler for ratio and latency histogram SLIs.
- Contract-to-deployment drift gate with token-canonical expression comparison.
- Standalone rule hazard analysis and independent error-budget reconciliation.
- SARIF 2.1.0, JSON and text reports with stable SHA-256 digests.
- CLI subcommands: `compile`, `verify`, `audit`, `explain`, `validate`.
- Zero-defect CI workflow with pytest, Ruff and Semgrep gates.

### Security

- Rejected PromQL comments and time modifiers; bounded all untrusted inputs.
- No runtime dependency beyond PyYAML; no services, agents or local models.

Baysöz Labs <baysozlabs@proton.me>
