import json

from migration_guard.model import Finding
from migration_guard.reporters.common import ordered_findings


def render_sarif(findings: list[Finding]) -> str:
    ordered = ordered_findings(findings)
    rules: dict[str, dict[str, object]] = {}
    results: list[dict[str, object]] = []
    for finding in ordered:
        rules.setdefault(
            finding.rule_id,
            {
                "id": finding.rule_id,
                "name": finding.title,
                "shortDescription": {"text": finding.title},
            },
        )
        results.append(
            {
                "ruleId": finding.rule_id,
                "level": finding.severity,
                "message": {"text": finding.reason},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": finding.file},
                            "region": {
                                "startLine": finding.line,
                                "startColumn": finding.column,
                            },
                        }
                    }
                ],
            }
        )
    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "MigrationGuard",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
