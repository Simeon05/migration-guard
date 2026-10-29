from migration_guard.rules import detect_remaining_risks


def ids(sql: str):
    return [finding.rule_id for finding in detect_remaining_risks(sql, "migration.sql")]


def test_pg007_concurrent_index_inside_transaction():
    assert "PG007" in ids("BEGIN; CREATE INDEX CONCURRENTLY ix ON users(email); COMMIT;")


def test_pg008_constraint_without_not_valid():
    assert "PG008" in ids(
        "ALTER TABLE users ADD CONSTRAINT fk FOREIGN KEY (org_id) REFERENCES orgs(id);"
    )


def test_pg009_unique_constraint_directly():
    assert "PG009" in ids(
        "ALTER TABLE users ADD CONSTRAINT uq UNIQUE (email);"
    )


def test_pg010_column_default_on_existing_table():
    assert "PG010" in ids(
        "ALTER TABLE users ADD COLUMN created_at timestamptz DEFAULT now();"
    )


def test_pg011_drop_index_without_concurrently():
    assert "PG011" in ids("DROP INDEX users_email_idx;")
    assert "PG011" not in ids("DROP INDEX CONCURRENTLY users_email_idx;")


def test_pg012_flags_locking_operation_without_timeout():
    assert "PG012" in ids("ALTER TABLE users ALTER COLUMN email SET NOT NULL;")
    assert "PG012" not in ids(
        "SET lock_timeout = '5s'; ALTER TABLE users ALTER COLUMN email SET NOT NULL;"
    )
