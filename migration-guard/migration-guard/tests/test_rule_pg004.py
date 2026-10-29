from migration_guard.rules import detect_type_changes


def test_detects_alter_column_type():
    findings = detect_type_changes(
        "ALTER TABLE users ALTER COLUMN age TYPE bigint;", "type.sql"
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "PG004"
    assert findings[0].severity == "high"
    assert findings[0].evidence == "ALTER TABLE users ALTER COLUMN age TYPE bigint"


def test_detects_quoted_type_change():
    findings = detect_type_changes(
        'ALTER TABLE "User Accounts" ALTER COLUMN "age-years" TYPE bigint;',
        "type.sql",
    )

    assert len(findings) == 1
    assert findings[0].line == 1


def test_ignores_other_alter_column_operations():
    assert detect_type_changes(
        "ALTER TABLE users ALTER COLUMN age SET DEFAULT 0;", "safe.sql"
    ) == []
