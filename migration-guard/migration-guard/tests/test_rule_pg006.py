from migration_guard.rules import detect_index_creation


def test_detects_non_concurrent_index_creation():
    findings = detect_index_creation("CREATE INDEX users_email_idx ON users (email);", "index.sql")

    assert len(findings) == 1
    assert findings[0].rule_id == "PG006"
    assert findings[0].severity == "high"


def test_ignores_concurrent_index_creation():
    assert detect_index_creation(
        "CREATE INDEX CONCURRENTLY users_email_idx ON users (email);", "index.sql"
    ) == []


def test_ignores_index_text_in_strings_and_comments():
    sql = """-- CREATE INDEX fake ON users (email);
SELECT 'CREATE INDEX fake ON users (email)';"""

    assert detect_index_creation(sql, "safe.sql") == []
