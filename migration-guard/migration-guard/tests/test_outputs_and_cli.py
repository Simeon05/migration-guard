import json
from pathlib import Path

from typer.testing import CliRunner

from migration_guard.cli import app
from migration_guard.model import Finding
from migration_guard.reporters.json import render_json
from migration_guard.reporters.sarif import render_sarif


def _finding(file: str, line: int, rule_id: str = "PG001") -> Finding:
    return Finding(
        rule_id=rule_id,
        severity="high",
        title="Dropping a table column",
        file=file,
        line=line,
        evidence="DROP COLUMN email",
        reason="The column may still be referenced.",
        recommendation="Use an expand/contract migration.",
    )


def test_json_report_has_versioned_schema_and_stable_order():
    rendered = render_json([_finding("b.sql", 2), _finding("a.sql", 1)])
    payload = json.loads(rendered)

    assert payload["schema_version"] == "1"
    assert [item["file"] for item in payload["findings"]] == ["a.sql", "b.sql"]


def test_sarif_report_has_locations_and_rule_metadata():
    payload = json.loads(render_sarif([_finding("migration.sql", 4)]))

    assert payload["version"] == "2.1.0"
    result = payload["runs"][0]["results"][0]
    assert result["ruleId"] == "PG001"
    assert result["locations"][0]["physicalLocation"]["region"]["startLine"] == 4


def test_cli_accepts_directory_and_returns_failure_for_findings(tmp_path: Path):
    migration = tmp_path / "nested" / "migration.sql"
    migration.parent.mkdir()
    migration.write_text("ALTER TABLE customers DROP COLUMN email;\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--format", "json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["findings"][0]["rule_id"] == "PG001"


def test_cli_returns_zero_for_safe_directory(tmp_path: Path):
    (tmp_path / "safe.sql").write_text(
        "CREATE TABLE customers (id integer);\n", encoding="utf-8"
    )

    result = CliRunner().invoke(app, ["check", str(tmp_path)])

    assert result.exit_code == 0

