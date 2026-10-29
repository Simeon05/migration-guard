from migration_guard.rules import detect_destructive_operations


def test_detects_drop_table():
    findings = detect_destructive_operations("DROP TABLE users;", "drop.sql")

    assert len(findings) == 1
    assert findings[0].rule_id == "PG002"
    assert findings[0].severity == "high"
    assert findings[0].evidence == "DROP TABLE users"


def test_detects_drop_table_if_exists_and_cascade():
    findings = detect_destructive_operations(
        "DROP TABLE IF EXISTS public.users CASCADE;", "drop.sql"
    )

    assert len(findings) == 1
    assert findings[0].evidence == "DROP TABLE IF EXISTS public.users CASCADE"
    assert "dependent" in findings[0].reason.lower()


def test_detects_each_table_in_multi_object_drop():
    findings = detect_destructive_operations(
        "DROP TABLE users, orders RESTRICT;", "drop.sql"
    )

    assert len(findings) == 2
    assert [finding.evidence for finding in findings] == [
        "DROP TABLE users",
        "DROP TABLE orders",
    ]


def test_detects_truncate():
    findings = detect_destructive_operations(
        "TRUNCATE TABLE public.users RESTART IDENTITY CASCADE;", "truncate.sql"
    )

    assert len(findings) == 1
    assert findings[0].evidence == "TRUNCATE TABLE public.users RESTART IDENTITY CASCADE"
    assert "ACCESS EXCLUSIVE" in findings[0].reason


def test_detects_drop_schema():
    findings = detect_destructive_operations(
        "DROP SCHEMA IF EXISTS tenant CASCADE;", "schema.sql"
    )

    assert len(findings) == 1
    assert findings[0].evidence == "DROP SCHEMA IF EXISTS tenant CASCADE"


def test_ignores_destructive_keywords_in_comments_and_strings():
    sql = """-- DROP TABLE fake;
SELECT 'TRUNCATE fake';
CREATE TABLE users (id integer);"""

    assert detect_destructive_operations(sql, "safe.sql") == []


def test_supports_quoted_names():
    findings = detect_destructive_operations(
        'DROP TABLE "User Accounts";', "quoted.sql"
    )

    assert len(findings) == 1
    assert findings[0].evidence == 'DROP TABLE "User Accounts"'
