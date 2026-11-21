# Security Policy — BurnLattice

Baysöz Labs <baysozlabs@proton.me>

## Supported versions

Security fixes are delivered for the latest 1.x release.

## Threat model and mitigations

| Threat | Mitigation |
| --- | --- |
| Oversized or malicious YAML/JSON | 1 MiB input cap, bounded expression length, `yaml.safe_load` |
| PromQL injection via matcher values | Allow-list label names; reject quotes, braces, comments, control characters and unsafe escapes |
| Window misalignment bypass | `offset` and `@` modifiers rejected; range selectors require exactly one duration |
| Silent threshold tampering | Contract drift comparison plus independent budget reconciliation |
| Supply-chain parser breakage | No Prometheus or PromQL library dependency; narrow internal lexer |
| Non-reproducible CI results | Sorted findings, canonical JSON, SHA-256 report digest, no timestamps |
| Arbitrary code execution | No `eval`, `exec`, `pickle`, `subprocess`, dynamic imports or network calls |
| Secret exposure | No credentials read, generated, logged or stored; no telemetry payloads ingested |

## Hardening notes for operators

Run the gate on untrusted pull requests with a read-only checkout. Provide the smallest
possible rule files and contracts. Do not place credentials in rule labels or
annotations: BurnLattice does not redact arbitrary annotation values.

## Reporting a vulnerability

Email **baysozlabs@proton.me** with a precise reproduction, affected version and impact.
Do not open a public issue for an unpatched vulnerability. Expected acknowledgement is
within five working days; a fix or mitigation plan follows triage.

Baysöz Labs <baysozlabs@proton.me>
