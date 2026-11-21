# BurnLattice

[![CI](https://github.com/yazilimbaysoz-svg/baysoz-burnlattice/actions/workflows/ci.yml/badge.svg)](https://github.com/yazilimbaysoz-svg/baysoz-burnlattice/actions/workflows/ci.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Baysöz Labs](https://img.shields.io/badge/maintained%20by-Bays%C3%B6z%20Labs-orange.svg)](mailto:baysozlabs@proton.me)

**Deterministic SLO burn-rate policy compiler and CI drift gate.**
Baysöz Labs <baysozlabs@proton.me>

BurnLattice turns a backend-neutral SLO contract into correct multi-window multi-burn-rate
Prometheus alerts, then proves that the rules deployed in production still encode that
same contract. It is offline, deterministic and emits SARIF 2.1.0 for pull-request gating.

## Why

High-star observability platforms generate and evaluate alerts, but nothing independently
verifies that a hand-edited rule file still means what the SLO promised. Live ecosystem
evidence is documented in [docs/MARKET_RESEARCH.md](docs/MARKET_RESEARCH.md).

- Catches silently changed burn windows, thresholds, labels and severities.
- Re-derives `burn_rate × (1 - objective)` with exact `Decimal` arithmetic.
- Detects match-all regexes, sub-5-minute rate windows, time modifiers and unscoped selectors.
- Requires no Prometheus server, collector, database, agent or local model.

## Install

```bash
uv venv
uv pip install -e .
uv pip install pytest
```

Python 3.13+ is required. The only runtime dependency is PyYAML.

## CLI output (real)

```text
$ burnlattice --version
burnlattice 1.0.0 - Baysöz Labs <baysozlabs@proton.me>

$ burnlattice explain examples/checkout-availability.json
burnlattice 1.0.0 - Baysöz Labs <baysozlabs@proton.me>
contract: checkout-api/checkout_availability
objective: 99.9% | window: 30d | error budget: 0.001

tier           channel    burn  short   long    threshold  budget@short   exhaust
fast_1h_6h     page       14.4     1h     6h       0.0144         2.00%       50h
fast_6h_1d     page          6     6h     1d        0.006         5.00%        5d
slow_1d_3d     ticket        3     1d     3d        0.003        10.00%       10d
slow_3d_30d    ticket        1     3d    30d        0.001        10.00%       30d

long-window confirmation is implicit in each tier.
Baysöz Labs <baysozlabs@proton.me>

$ burnlattice verify examples/checkout-availability.json examples/rules-clean.yml
burnlattice 1.0.0 - Baysöz Labs <baysozlabs@proton.me>
command: verify
source: examples/rules-clean.yml
findings: 0 (errors=0 warnings=0 notes=0)
digest: sha256:6d844b276fa720b5c73f0cb5e0f2ed0baae7c7b8a9098abcd1a98c0f23c3a722
Baysöz Labs <baysozlabs@proton.me>

$ burnlattice verify examples/checkout-availability.json examples/rules-with-drift.yml
burnlattice 1.0.0 - Baysöz Labs <baysozlabs@proton.me>
command: verify
source: examples/rules-with-drift.yml
findings: 1 (errors=1 warnings=0 notes=0)
  [error] SLO_DRIFT_EXPRESSION examples/rules-with-drift.yml:8
    alert CheckoutAvailabilityBurnFast1h6h expression drifted from the contract
    detail: expected: (sum(rate(http_requests_total{job="checkout-api",status=~"2.."}[1h])) ... | actual: (sum(rate(http_requests_total{job="checkout-api",status=~"2.."}[5m])) ...
digest: sha256:319723b4132562d3c81063327be7f0d069b60c74f147866e83f662b8f380c497
Baysöz Labs <baysozlabs@proton.me>
# exit code 1
```

## Architecture

```
contract.json -> spec.py -> SloContract -> burnrate.py -> expected rules
rules.yml     -> rules.py -> deployed rules --------------------+
                                      |                         |
                              analyzer.py                  drift.py
                                      +----------+------------+
                                                 v
                                    report.py -> text / JSON / SARIF
```

Details in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [PLAN.md](PLAN.md),
[SECURITY.md](SECURITY.md) and [CHANGELOG.md](CHANGELOG.md).

## Library use

```python
from burnlattice import generate_rules, load_contract, verify_drift
from burnlattice.rules import parse_rules, render_rules

contract = load_contract("examples/checkout-availability.json")
expected = generate_rules(contract)
rules_yaml = render_rules(contract, expected)
deployed = parse_rules(rules_yaml, "rules.yml")
findings = verify_drift(contract, expected, deployed, "rules.yml")
```

## Exit codes

| Code | Meaning |
| ---: | --- |
| 0 | No finding at or above `--fail-on` |
| 1 | Gate violation found |
| 2 | Invalid input or I/O failure |

## Security

Report vulnerabilities privately to **baysozlabs@proton.me**. See [SECURITY.md](SECURITY.md).

## License and attribution

MIT. Copyright (c) 2026 Baysöz Labs <baysozlabs@proton.me>.
No legal entity suffix is used.

Baysöz Labs <baysozlabs@proton.me>
