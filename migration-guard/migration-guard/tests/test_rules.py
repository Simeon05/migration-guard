import pytest

from migration_guard.ports.parser import ParserError
from migration_guard.rules import detect_dropped_columns


def test_detects_dropped_column():
    sql = """
    ALTER TABLE customers
    DROP COLUMN email;
    """

    findings = detect_dropped_columns(sql, "drop_email.sql")

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == "PG001"
    assert finding.severity == "high"
    assert finding.evidence == "DROP COLUMN email"
    assert finding.line == 3


def test_ignores_drop_column_in_comment():
    sql = """
    -- DROP COLUMN email
    CREATE TABLE customers (id integer);
    """

    assert detect_dropped_columns(sql, "safe.sql") == []


def test_ignores_drop_column_in_string():
    sql = """
    SELECT 'DROP COLUMN email';
    """

    assert detect_dropped_columns(sql, "safe.sql") == []


def test_rejects_invalid_sql():
    with pytest.raises(ParserError):
        detect_dropped_columns("ALTER TABLE customers DROP COLUMN;", "invalid.sql")


def test_reports_line_where_drop_column_appears():
    sql = """
    ALTER TABLE customers
        DROP COLUMN email;
    """

    findings = detect_dropped_columns(sql, "multiline.sql")

    assert len(findings) == 1
    assert findings[0].line == 3


def test_ignores_drop_column_in_comment_when_reporting_line():
    sql = """ALTER TABLE customers
-- DROP COLUMN fake
DROP COLUMN email;"""

    findings = detect_dropped_columns(sql, "comment.sql")

    assert len(findings) == 1
    assert findings[0].evidence == "DROP COLUMN email"
    assert findings[0].line == 3


def test_reports_each_dropped_column_on_its_own_line():
    sql = """ALTER TABLE customers
    DROP COLUMN email,
    DROP COLUMN phone;"""

    findings = detect_dropped_columns(sql, "multiple.sql")

    assert len(findings) == 2
    assert [finding.evidence for finding in findings] == [
        "DROP COLUMN email",
        "DROP COLUMN phone",
    ]
    assert [finding.line for finding in findings] == [2, 3]


def test_reports_drop_column_after_string_literal_in_previous_statement():
    sql = """SELECT 'DROP COLUMN fake';
ALTER TABLE customers DROP COLUMN email;"""

    findings = detect_dropped_columns(sql, "after-string.sql")

    assert len(findings) == 1
    assert findings[0].line == 2


def test_reports_drop_column_on_crlf_input():
    sql = "ALTER TABLE customers\r\nDROP COLUMN email;\r\n"

    findings = detect_dropped_columns(sql, "crlf.sql")

    assert len(findings) == 1
    assert findings[0].line == 2


def test_reports_drop_column_after_unicode_before_statement():
    sql = "-- café ☕\nALTER TABLE customers DROP COLUMN email;"

    findings = detect_dropped_columns(sql, "unicode.sql")

    assert len(findings) == 1
    assert findings[0].line == 2


def test_reports_exact_span_for_quoted_identifier():
    sql = 'ALTER TABLE "Customer Accounts" DROP COLUMN IF EXISTS "Email Address";'

    findings = detect_dropped_columns(sql, "quoted.sql")

    assert len(findings) == 1
    assert findings[0].line == 1
    assert findings[0].evidence == 'DROP COLUMN IF EXISTS "Email Address"'


def test_reports_statement_after_dollar_quoted_body():
    sql = """SELECT $$DROP COLUMN fake$$;
ALTER TABLE customers DROP COLUMN email;"""

    findings = detect_dropped_columns(sql, "dollar-quote.sql")

    assert len(findings) == 1
    assert findings[0].line == 2


def test_reports_each_drop_across_multiple_statements():
    sql = """ALTER TABLE customers DROP COLUMN email;
ALTER TABLE orders DROP COLUMN phone;"""

    findings = detect_dropped_columns(sql, "multiple-statements.sql")

    assert len(findings) == 2
    assert [finding.line for finding in findings] == [1, 2]
