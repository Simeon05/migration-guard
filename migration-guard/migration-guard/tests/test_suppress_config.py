from pathlib import Path

import pytest

from migration_guard.config import load_config
from migration_guard.rules import detect_dropped_columns
from migration_guard.suppress import apply_suppressions


def test_inline_suppression_requires_reason_and_matches_next_line():
    sql = """-- migrationguard-ignore PG001 reason=\"legacy cleanup\"
ALTER TABLE customers DROP COLUMN email;"""
    finding = detect_dropped_columns(sql, "migration.sql")[0]

    result = apply_suppressions(sql, [finding])

    assert result.findings == []
    assert result.suppressed[0].reason == "legacy cleanup"


def test_suppression_does_not_read_directives_inside_string_literals():
    sql = """SELECT '-- migrationguard-ignore PG001 reason=\"fake\"';
ALTER TABLE customers DROP COLUMN email;"""
    finding = detect_dropped_columns(sql, "migration.sql")[0]

    result = apply_suppressions(sql, [finding])

    assert result.findings == [finding]
    assert result.suppressed == []


def test_missing_suppression_reason_is_rejected_in_strict_mode():
    sql = "-- migrationguard-ignore PG001\nALTER TABLE customers DROP COLUMN email;"
    finding = detect_dropped_columns(sql, "migration.sql")[0]

    with pytest.raises(ValueError, match="reason"):
        apply_suppressions(sql, [finding], require_reason=True)


def test_config_loads_supported_values(tmp_path: Path):
    config_path = tmp_path / ".migrationguard.toml"
    config_path.write_text(
        """[core]
target_version = 15
fail_on = \"medium\"
deploy_model = \"migrate-before-deploy\"

[rules]
PG001 = { severity = \"high\" }

[paths]
migrations = [\"db/**/*.sql\"]
exclude = [\"db/legacy/**\"]

[code]
roots = [\"src\"]
orm = [\"django\"]

[suppress]
require_reason = true
max_age_days = 90
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.target_version == 15
    assert config.fail_on == "medium"
    assert config.rule_overrides["PG001"]["severity"] == "high"
    assert config.suppress_require_reason is True


def test_config_rejects_unknown_top_level_keys(tmp_path: Path):
    config_path = tmp_path / ".migrationguard.toml"
    config_path.write_text("[unknown]\nvalue = true\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown"):
        load_config(config_path)
