"""Unified gate reports, digests and exit-code policy.

Baysöz Labs <baysozlabs@proton.me>
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .attribution import ATTRIBUTION, TOOL_NAME, VERSION
from .model import Finding, Severity
from .sarif import to_sarif


@dataclass(frozen=True, slots=True)
class Report:
    """A deterministic report for one CLI verification command."""

    command: str
    source: str
    findings: tuple[Finding, ...]

    def __post_init__(self) -> None:
        """Reject unsorted finding collections at construction time."""
        keys = [finding.sort_key for finding in self.findings]
        if keys != sorted(keys):
            raise ValueError("findings must be sorted before reporting")

    def counts(self) -> dict[str, int]:
        """Return counts per severity."""
        result = {severity.value: 0 for severity in Severity}
        for finding in self.findings:
            result[finding.severity.value] += 1
        return result

    def to_dict(self) -> dict[str, object]:
        """Return the canonical JSON structure for this report."""
        counts = self.counts()
        return {
            "schema_version": "1.0",
            "tool": TOOL_NAME,
            "tool_version": VERSION,
            "attribution": ATTRIBUTION,
            "command": self.command,
            "source": self.source,
            "summary": {
                "total": len(self.findings),
                "errors": counts["error"],
                "warnings": counts["warning"],
                "notes": counts["note"],
            },
            "findings": [finding.to_dict() for finding in self.findings],
        }

    def digest(self) -> str:
        """Return a stable SHA-256 digest of the canonical report."""
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_json(self) -> str:
        """Render the report as UTF-8 JSON text."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"

    def to_sarif_json(self) -> str:
        """Render the report as SARIF 2.1.0 JSON text."""
        return json.dumps(to_sarif(self.findings, self.source), ensure_ascii=False, indent=2) + "\n"

    def to_text(self) -> str:
        """Render a compact, deterministic terminal report."""
        counts = self.counts()
        lines = [
            f"{TOOL_NAME} {VERSION} - {ATTRIBUTION}",
            f"command: {self.command}",
            f"source: {self.source or '<input>'}",
            f"findings: {len(self.findings)} "
            f"(errors={counts['error']} warnings={counts['warning']} "
            f"notes={counts['note']})",
        ]
        for finding in self.findings:
            location = finding.path or self.source or "<input>"
            if finding.line:
                location = f"{location}:{finding.line}"
            lines.append(f"  [{finding.severity.value}] {finding.rule_id} {location}")
            lines.append(f"    {finding.message}")
            if finding.detail:
                lines.append(f"    detail: {finding.detail}")
        lines.append(f"digest: sha256:{self.digest()}")
        lines.append(ATTRIBUTION)
        return "\n".join(lines) + "\n"

    def render(self, format_name: str) -> str:
        """Render a report in the requested format."""
        if format_name == "json":
            return self.to_json()
        if format_name == "sarif":
            return self.to_sarif_json()
        if format_name == "text":
            return self.to_text()
        raise ValueError(f"unsupported report format: {format_name}")

    def exit_code(self, fail_on: Severity) -> int:
        """Return 1 when a finding reaches or exceeds the chosen severity."""
        for finding in self.findings:
            if finding.severity.rank >= fail_on.rank:
                return 1
        return 0


def sorted_findings(findings: tuple[Finding, ...] | list[Finding]) -> tuple[Finding, ...]:
    """Sort findings using the canonical report ordering."""
    return tuple(sorted(findings, key=lambda finding: finding.sort_key))
