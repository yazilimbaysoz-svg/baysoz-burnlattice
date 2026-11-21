# Market Research — BurnLattice

Baysöz Labs <baysozlabs@proton.me>

Research snapshot: 2026-11-21, obtained live with `gh search repos`, `gh search issues`
and issue detail reads through the GitHub API. All star counts are observations at that
time, not claims of permanence.

## 1. Ecosystem signal: observability is consolidating, correctness is not

Live high-star repositories returned by `gh search repos "observability"`:

| Repository | Stars | Position |
| --- | ---: | --- |
| `netdata/netdata` | 81,575 | Full-stack collection and visualization |
| `grafana/grafana` | 78,030 | Dashboards and querying |
| `PostHog/posthog` | 41,003 | Product/AI observability |
| `SigNoz/signoz` | 32,692 | OTel-native APM platform |
| `cilium/cilium` | 25,880 | eBPF networking and observability |
| `jaegertracing/jaeger` | 23,436 | Distributed tracing |
| `openobserve/openobserve` | 23,142 | Logs, metrics, traces, SLO in one platform |
| `vectordotdev/vector` | 22,930 | Telemetry pipeline |
| `VictoriaMetrics/VictoriaMetrics` | 18,159 | Storage and querying |

Observability capacity is abundant. What is scarce is an **independent, offline,
deterministic correctness gate** that tells an SRE team whether the alerting policy in
production still encodes the SLO that was agreed with customers. Every platform above
owns its own rule evaluation; none of them is a neutral verifier for CI.

## 2. Concrete pain points mined from live issues

`gh search issues --repo slok/sloth` (2,573 stars; the dominant standalone Prometheus
SLO generator) returned unresolved, substantive defects:

- [slok/sloth#842](https://github.com/slok/sloth/issues/842) — `denominator_corrected_rules/v1`
  produces negative SLI values (~ -52,000%) on non-continuous traffic because the
  correction factor `rate(5m) / rate(30d)` explodes during a traffic spike. This is an
  error-budget arithmetic failure in a tool teams trust for alert generation.
- [slok/sloth#847](https://github.com/slok/sloth/issues/847) — a `promql/parser` API
  break blocks upgrading past `prometheus/prometheus` v0.310.0, which in turn blocks
  CVE-2026-42154 / CVE-2026-42151 fixes. Three dependency bumps already failed CI.
  Proof that embedding a fast-moving parser creates supply-chain fragility.
- [slok/sloth#829](https://github.com/slok/sloth/issues/829) — time-bucket SLOs
  over-burn the budget on partial brownouts: 1% failures in a minute burn 100% of that
  minute's budget, roughly 7x less response time than event-based accounting. The issue
  asks for backend-agnostic, event-based, OpenSLO-aligned definitions.

Adjacent adapters show the same fragmentation: `coroot/coroot` (8,027 stars) already
bundles SLO-based alerting with RCA, and `openobserve/openobserve` bundles SLO inside a
platform. Each implementation has its own definition format and its own arithmetic.

## 3. The gap BurnLattice fills

1. **Policy drift is invisible.** Generated rules are copied, hand-edited, templated and
   merged. Nothing checks that the deployed multi-window thresholds still equal
   `burn_rate × (1 - objective)` for the contracted SLO window.
2. **Arithmetic is rarely re-derived.** A single changed objective, window or tier
   multiplier silently changes the meaning of every page. #842 is exactly this class
   of failure.
3. **Parsers are a supply-chain liability.** #847 shows that binding to a specific
   Prometheus parser version can block security upgrades. BurnLattice uses a narrow,
   strict lexer for the expression subset it emits, with no Prometheus dependency.
4. **CI needs a neutral verifier.** A gate must be offline, side-effect free and
   deterministic, and must emit a machine-readable result (SARIF) without requiring a
   running Prometheus, collector, database or agent.
5. **Drift and hazards are different problems.** A rule file can be internally valid
   and still be operationally dangerous (match-all regexes, 30-second rate windows,
   unscoped selectors, duplicate alert names). Both checks belong in one gate.

## 4. Why this is not redundant with the existing portfolio

Existing Baysöz Labs work in `/home/runner/work/_temp/existing-repos.json` covers JWT
confusion, Terraform blast radius, OTel Collector config linting, ATR/Sigma parity,
Actions lockfiles, telemetry **cardinality** risk (`baysoz-cardinalis`), environment
drift (`envlens`, `envpair`), log PII masking and KVKK/GDPR redaction.

BurnLattice is orthogonal:

- It does **not** estimate cardinality; it verifies error-budget arithmetic and
  burn-window policy.
- It does **not** lint collector configuration; it consumes Prometheus rule YAML and an
  SLO contract.
- It does **not** redact data, scan dependencies or mask logs; it never reads telemetry
  payloads at all.
- It is a compiler plus verifier with derived numerical output (thresholds, budget
  consumption, exhaustion time), not a linter that only reports style violations.

## 5. Technology choice

Python 3.13 with `uv` and a single small runtime dependency (PyYAML) is the right fit:
`Decimal` gives exact error-budget arithmetic; the standard library supplies JSON,
hashing, CLI and regex parsing; no service, agent, compiler toolchain or local model is
required. The result is a ~millisecond gate that can run on every pull request.

Baysöz Labs <baysozlabs@proton.me>
