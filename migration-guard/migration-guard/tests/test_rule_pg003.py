from migration_guard.rules import detect_renames


def test_detects_column_rename():
    findings = detect_renames(
        "ALTER TABLE users RENAME COLUMN email TO email_address;", "rename.sql"
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "PG003"
    assert findings[0].evidence == "RENAME COLUMN email TO email_address"


def test_detects_schema_qualified_table_rename():
    findings = detect_renames(
        "ALTER TABLE public.users RENAME TO customers;", "rename.sql"
    )

    assert len(findings) == 1
    assert findings[0].evidence == "RENAME TO customers"
    assert "public.users" in findings[0].reason


def test_supports_quoted_column_names():
    findings = detect_renames(
        'ALTER TABLE "User Accounts" RENAME COLUMN "e-mail" TO "email";',
        "rename.sql",
    )

    assert len(findings) == 1
    assert '"e-mail"' in findings[0].evidence


def test_ignores_rename_in_comments_and_strings():
    sql = """-- ALTER TABLE users RENAME COLUMN email TO fake;
SELECT 'RENAME COLUMN email TO fake';"""

    assert detect_renames(sql, "safe.sql") == []
