import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from migration_guard.model import Finding
from migration_guard.reporters.common import ordered_findings


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def render_json(findings: list[Finding]) -> str:
    payload = {
        "schema_version": "1",
        "findings": [_json_value(finding) for finding in ordered_findings(findings)],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
