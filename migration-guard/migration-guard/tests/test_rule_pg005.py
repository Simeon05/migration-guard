from migration_guard.rules import detect_not_null_changes


def test_detects_set_not_null():
    findings = detect_not_null_changes(
        "ALTER TABLE users ALTER COLUMN email SET NOT NULL;", "null.sql"
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "PG005"
    assert findings[0].severity == "high"


def test_supports_schema_qualified_set_not_null():
    findings = detect_not_null_changes(
        "ALTER TABLE public.users ALTER COLUMN email SET NOT NULL;", "null.sql"
    )

    assert len(findings) == 1
    assert findings[0].line == 1


def test_ignores_drop_not_null_and_comments():
    sql = """-- ALTER TABLE users ALTER COLUMN email SET NOT NULL;
ALTER TABLE users ALTER COLUMN email DROP NOT NULL;"""

    assert detect_not_null_changes(sql, "safe.sql") == []
