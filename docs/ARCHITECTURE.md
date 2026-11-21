# Architecture — BurnLattice

Baysöz Labs <baysozlabs@proton.me>

## 1. System shape

BurnLattice is a pure function pipeline. No network calls, no daemons, no clocks and no
randomness appear in any code path that produces output.

```
SLO contract (JSON)          Prometheus rules (YAML)
      |                              |
      v                              v
  spec.py  ------> SloContract     rules.py ------> Rule[]
      |                              |
      +--> burnrate.py -> Rule[]     +--> analyzer.py -> Finding[]
      |                                     |
      +--> explanation_rows() --------------+
                    |
      drift.py (expected vs deployed) + budget_reconciliation()
                    |
              report.py (sorted Finding[])
                    |
        +-----------+------------+
        |           |            |
      text        JSON         SARIF 2.1.0
```

## 2. Module responsibilities

| Module | Responsibility |
| --- | --- |
| `attribution.py` | Immutable provenance and input-limit constants |
| `model.py` | Frozen, slotted domain types: contracts, SLIs, tiers, rules, findings |
| `promql.py` | Strict PromQL lexer, bracket validation, canonicalization, duration math |
| `spec.py` | Contract schema, semantic checks, matcher and alerting-policy validation |
| `burnrate.py` | Multi-window burn arithmetic and deterministic rule synthesis |
| `rules.py` | Bounded YAML parsing, structural validation, stable YAML emission |
| `drift.py` | Contract-to-deployment comparison and threshold reconciliation |
| `analyzer.py` | Production hazard rules for any Prometheus rule file |
| `sarif.py` | SARIF 2.1.0 document construction |
| `report.py` | Sorted reports, SHA-256 digest, renderers, exit-code policy |
| `cli.py` | `compile`, `verify`, `audit`, `explain`, `validate` subcommands |

## 3. Correctness model

For objective `O` (percent) and error budget `B = (100 - O) / 100`, a tier with burn
rate `R` fires when the observed error ratio exceeds `T = R × B` in **both** its short
and long windows. The confirmation ratio `long / short` suppresses noise; the short
window determines detection time. Budget consumed before firing is
`100 × R × short / window`. Time to full exhaustion is `window / R`.

All arithmetic uses `Decimal`, so `99.9` yields exactly `0.001` and `14.4 × 0.001`
yields exactly `0.0144`. No binary floating point appears in threshold derivation.

Guardrails enforced before emission:

- tier long window must not exceed the SLO window;
- short window must be strictly smaller than long window;
- `0 < R × B <= 1`;
- page channel must contain a tier with `R >= 6`; ticket must contain `R <= 3`;
- a tier cannot be assigned to two channels;
- ratio SLI `good` selectors must be strictly more restrictive than `total`;
- latency SLI metrics are histogram base names; `le` is derived from milliseconds.

## 4. Drift semantics

`verify` compiles the expected rules from the contract, then compares each deployed
alert by name. Expression comparison is token-canonical: whitespace and numeric
spelling are normalized, but metric names, matchers, ranges, operators and thresholds
must match exactly. Label drift is an error; group and machine-annotation drift are
warnings; extra routing labels are permitted. Explicit budget reconciliation also
recomputes `R × (1 - O)` from the rule's own annotations, so a tampered annotation is
detected even if the contract is not available (`audit`).

## 5. Safety and security posture

- `yaml.safe_load` only; no object construction, `eval`, `exec`, `subprocess` or `pickle`.
- PromQL comments (`#`) and time modifiers (`offset`, `@`) are rejected because they
  can invalidate window alignment.
- Inputs are bounded to 1 MiB and expressions to 20,000 characters.
- Matcher values are constrained to prevent YAML/PromQL injection through quotes,
  braces, comments and control characters.
- Output never embeds a guessed URL; the only URLs are known schema/repository values.
- Deterministic ordering and digests make CI results reproducible and auditable.

## 6. Extension points

New burn tiers are additive entries in `TIERS` with a suffix and exact `Decimal` rate.
New hazards are pure functions returning `Finding` tuples from `analyzer.py`. New
report formats are branches in `Report.render`. None of these changes require state or
a service dependency.

Baysöz Labs <baysozlabs@proton.me>
