from bisect import bisect_right

from migration_guard.adapters.parser_pglast import PglastParser
from migration_guard.model import Finding
from migration_guard.ports.parser import Parser, Token


def _line_and_column(source: str, offset: int) -> tuple[int, int]:
    """Convert a parser character offset to a one-based line and column.

    pglast exposes scanner and statement offsets in Python string coordinates.
    Keeping the conversion here means Unicode characters, CRLF newlines, and
    tabs are handled consistently for every finding.
    """
    if offset < 0 or offset > len(source):
        raise ValueError(f"offset {offset} is outside the source")

    line_starts = [0]
    line_starts.extend(
        index + 1 for index, character in enumerate(source) if character == "\n"
    )
    line_index = bisect_right(line_starts, offset) - 1
    return line_index + 1, offset - line_starts[line_index] + 1


def _drop_column_spans(
    sql: str, tokens: tuple[Token, ...], statement_start: int, statement_end: int
):
    """Yield exact source spans for DROP COLUMN token sequences."""
    statement_tokens = [
        token
        for token in tokens
        if statement_start <= token.start < statement_end
    ]
    for index, token in enumerate(statement_tokens):
        if token.name != "DROP" or index + 1 >= len(statement_tokens):
            continue
        if statement_tokens[index + 1].name != "COLUMN":
            continue

        end_index = index + 1
        if (
            end_index + 2 < len(statement_tokens)
            and statement_tokens[end_index + 1].name == "IF_P"
            and statement_tokens[end_index + 2].name == "EXISTS"
        ):
            end_index += 2
        column_index = end_index + 1
        if column_index >= len(statement_tokens):
            continue

        column_token = statement_tokens[column_index]
        yield token.start, column_token.end


def detect_dropped_columns(sql: str, file: str) -> list[Finding]:
    """Return findings for columns removed by ALTER TABLE statements.

    Parsing is intentionally allowed to raise pglast's ParseError so callers
    can decide how to present invalid SQL to users.
    """
    findings: list[Finding] = []
    parser: Parser = PglastParser()
    parse_result = parser.parse(sql)
    tokens = parser.tokenize(sql)

    for statement in parse_result.statements:
        if statement.kind != "AlterTableStmt":
            continue

        table = statement.table
        statement_start = statement.start
        statement_end = statement_start + statement.length

        drop_spans = iter(
            _drop_column_spans(sql, tokens, statement_start, statement_end)
        )
        for command in statement.commands:
            if command.kind != "AT_DropColumn":
                continue

            column = command.name
            try:
                start, end = next(drop_spans)
            except StopIteration as error:
                raise ValueError("could not locate DROP COLUMN command tokens") from error
            line, _column = _line_and_column(sql, start)
            findings.append(
                Finding(
                    rule_id="PG001",
                    severity="high",
                    title="Dropping a table column",
                    file=file,
                    line=line,
                    evidence=sql[start:end],
                    reason=(
                        f"Dropping {table}.{column} may break application queries "
                        "or dependents that still reference the column."
                    ),
                    recommendation=(
                        "Verify all application and database references before "
                        "removing the column, then deploy the removal separately."
                    ),
                )
            )

    return findings


def detect_destructive_operations(sql: str, file: str) -> list[Finding]:
    """Return findings for destructive table, schema, and truncate statements."""
    findings: list[Finding] = []
    parser: Parser = PglastParser()
    parse_result = parser.parse(sql)
    tokens = parser.tokenize(sql)

    for statement in parse_result.statements:
        if statement.kind not in {"DropStmt", "TruncateStmt"}:
            continue
        if statement.object_kind not in {"table", "schema"}:
            continue

        object_texts = _destructive_object_texts(
            sql, tokens, statement.start, statement.start + statement.length, len(statement.objects)
        )
        command = (
            "TRUNCATE TABLE"
            if statement.kind == "TruncateStmt"
            else "DROP " + statement.object_kind.upper()
        )
        for index, object_name in enumerate(statement.objects):
            exact_name = object_texts[index] if index < len(object_texts) else object_name
            evidence = f"{command} {'IF EXISTS ' if statement.missing_ok else ''}{exact_name}"
            if statement.restart_identity:
                evidence += " RESTART IDENTITY"
            evidence += " CASCADE" if statement.cascade else ""
            line, _column = _line_and_column(sql, statement.start)
            if statement.kind == "TruncateStmt":
                reason = (
                    f"TRUNCATE takes ACCESS EXCLUSIVE on {object_name}, blocks concurrent "
                    "operations, and removes all rows without firing DELETE triggers."
                )
                recommendation = "Use a controlled, batched DELETE when concurrent access must continue."
            elif statement.object_kind == "schema":
                reason = f"Dropping schema {object_name} removes its contained objects and may remove dependent objects."
                recommendation = "Use an explicit, reviewed object-by-object decommissioning plan."
            else:
                reason = f"Dropping table {object_name} removes its data and dependent database objects."
                recommendation = "Use a delayed rename-and-drop plan after application references are removed."
            if statement.cascade:
                reason += " CASCADE can remove dependent objects recursively."
            findings.append(
                Finding(
                    rule_id="PG002",
                    severity="high",
                    title="Destructive database operation",
                    file=file,
                    line=line,
                    evidence=evidence,
                    reason=reason,
                    recommendation=recommendation,
                    lock_level="ACCESS EXCLUSIVE",
                    confidence="high",
                )
            )

    return findings


def _destructive_object_texts(
    sql: str,
    tokens: tuple[Token, ...],
    statement_start: int,
    statement_end: int,
    count: int,
) -> list[str]:
    """Extract exact source text for object names from scanner tokens."""
    statement_tokens = [
        token for token in tokens if statement_start <= token.start < statement_end
    ]
    index = 1
    if statement_tokens and statement_tokens[0].name == "TRUNCATE":
        if index < len(statement_tokens) and statement_tokens[index].name == "TABLE":
            index += 1
        if index < len(statement_tokens) and statement_tokens[index].name == "ONLY":
            index += 1
    else:
        if index < len(statement_tokens):
            index += 1
        if (
            index + 1 < len(statement_tokens)
            and statement_tokens[index].name == "IF_P"
            and statement_tokens[index + 1].name == "EXISTS"
        ):
            index += 2

    names: list[str] = []
    for _ in range(count):
        start_index = index
        while index < len(statement_tokens):
            token = statement_tokens[index]
            if token.name in {"ASCII_44", "CASCADE", "RESTRICT", "RESTART", "IDENTITY", "ASCII_59"}:
                break
            index += 1
        if start_index < index:
            names.append(sql[statement_tokens[start_index].start : statement_tokens[index - 1].end])
        while index < len(statement_tokens) and statement_tokens[index].name == "ASCII_44":
            index += 1
    return names


def detect_renames(sql: str, file: str) -> list[Finding]:
    findings: list[Finding] = []
    parser: Parser = PglastParser()
    parse_result = parser.parse(sql)
    tokens = parser.tokenize(sql)
    for statement in parse_result.statements:
        if statement.kind != "RenameStmt" or not statement.rename_kind:
            continue
        line, _column = _line_and_column(sql, statement.start)
        object_name = statement.table or "unknown relation"
        if statement.rename_kind == "column":
            evidence = _rename_evidence(
                sql, tokens, statement.start, statement.start + statement.length
            )
            reason = (
                f"Renaming {object_name}.{statement.old_name} can break old application "
                "code while a rolling deploy is still in progress."
            )
        else:
            evidence = _rename_evidence(
                sql, tokens, statement.start, statement.start + statement.length
            )
            reason = (
                f"Renaming {object_name} can break application queries and database "
                "dependents that still use the old relation name."
            )
        findings.append(
            Finding(
                rule_id="PG003",
                severity="high",
                title="Renaming a database object",
                file=file,
                line=line,
                evidence=evidence,
                reason=reason,
                recommendation="Use an expand/contract rollout with dual reads or writes before removing the old name.",
                confidence="high",
            )
        )
    return findings


def _rename_evidence(
    sql: str, tokens: tuple[Token, ...], statement_start: int, statement_end: int
) -> str:
    statement_tokens = [
        token for token in tokens if statement_start <= token.start < statement_end
    ]
    rename_index = next(index for index, token in enumerate(statement_tokens) if token.name == "RENAME")
    end_index = rename_index + 1
    if end_index < len(statement_tokens) and statement_tokens[end_index].name == "COLUMN":
        end_index += 1
    while end_index < len(statement_tokens) and statement_tokens[end_index].name != "ASCII_59":
        end_index += 1
    end_token = statement_tokens[end_index - 1]
    return sql[statement_tokens[rename_index].start : end_token.end]


def detect_type_changes(sql: str, file: str) -> list[Finding]:
    findings: list[Finding] = []
    parser: Parser = PglastParser()
    parse_result = parser.parse(sql)
    for statement in parse_result.statements:
        if statement.kind != "AlterTableStmt":
            continue
        if not any(command.kind == "AT_AlterColumnType" for command in statement.commands):
            continue
        line, _column = _line_and_column(sql, statement.start)
        evidence = sql[statement.start : statement.start + statement.length].strip()
        evidence = evidence.rstrip(";").rstrip()
        findings.append(
            Finding(
                rule_id="PG004",
                severity="high",
                title="Changing a column type",
                file=file,
                line=line,
                evidence=evidence,
                reason=(
                    f"Changing a type on {statement.table or 'the table'} may rewrite or scan the table "
                    "and can require ACCESS EXCLUSIVE locking."
                ),
                recommendation="Add a new column, backfill in batches, validate, and switch reads and writes gradually.",
                lock_level="ACCESS EXCLUSIVE",
                confidence="medium",
            )
        )
    return findings


def detect_not_null_changes(sql: str, file: str) -> list[Finding]:
    findings: list[Finding] = []
    parser: Parser = PglastParser()
    for statement in parser.parse(sql).statements:
        if statement.kind != "AlterTableStmt" or not any(
            command.kind == "AT_SetNotNull" for command in statement.commands
        ):
            continue
        line, _column = _line_and_column(sql, statement.start)
        evidence = sql[statement.start : statement.start + statement.length].strip().rstrip(";").rstrip()
        findings.append(
            Finding(
                rule_id="PG005",
                severity="high",
                title="Setting a column NOT NULL",
                file=file,
                line=line,
                evidence=evidence,
                reason="SET NOT NULL may scan an existing table while holding a strong lock.",
                recommendation="Add and validate a NOT VALID CHECK constraint first, then set NOT NULL.",
                lock_level="ACCESS EXCLUSIVE",
                confidence="medium",
            )
        )
    return findings


def detect_index_creation(sql: str, file: str) -> list[Finding]:
    findings: list[Finding] = []
    parser: Parser = PglastParser()
    for statement in parser.parse(sql).statements:
        if statement.kind != "IndexStmt" or statement.concurrent:
            continue
        line, _column = _line_and_column(sql, statement.start)
        evidence = sql[statement.start : statement.start + statement.length].strip().rstrip(";").rstrip()
        findings.append(
            Finding(
                rule_id="PG006",
                severity="high",
                title="Creating an index without CONCURRENTLY",
                file=file,
                line=line,
                evidence=evidence,
                reason="A non-concurrent index build can block writes on a busy table.",
                recommendation="Use CREATE INDEX CONCURRENTLY outside a transaction when the deployment model permits it.",
                lock_level="SHARE",
                confidence="high",
            )
        )
    return findings


def detect_remaining_risks(sql: str, file: str) -> list[Finding]:
    findings: list[Finding] = []
    parser: Parser = PglastParser()
    statements = parser.parse(sql).statements
    in_transaction = False
    has_lock_timeout = any(
        statement.variable_name == "lock_timeout" for statement in statements
    )
    for statement in statements:
        if statement.kind == "TransactionStmt":
            if statement.transaction_kind in {"TRANS_STMT_BEGIN", "TRANS_STMT_START"}:
                in_transaction = True
            elif statement.transaction_kind in {"TRANS_STMT_COMMIT", "TRANS_STMT_ROLLBACK"}:
                in_transaction = False
            continue

        line, _column = _line_and_column(sql, statement.start)
        evidence = sql[statement.start : statement.start + statement.length].strip().rstrip(";").rstrip()
        rule_id: str | None = None
        title = ""
        reason = ""
        recommendation = ""
        severity = "high"

        if statement.kind == "IndexStmt" and statement.concurrent and in_transaction:
            rule_id = "PG007"
            title = "Concurrent index creation inside a transaction"
            reason = "CREATE INDEX CONCURRENTLY cannot run inside a transaction block."
            recommendation = "Run the migration outside the framework's transaction wrapper."
        elif statement.kind == "AlterTableStmt":
            command_kinds = {command.kind for command in statement.commands}
            details = {command.detail for command in statement.commands}
            if "AT_AddConstraint" in command_kinds and {"CONSTR_FOREIGN", "CONSTR_CHECK"} & details:
                rule_id = "PG008"
                title = "Constraint validation during table alteration"
                reason = "Adding a foreign-key or CHECK constraint without NOT VALID may scan existing data."
                recommendation = "Add it NOT VALID, validate separately, then enforce it."
                severity = "medium"
            elif "AT_AddConstraint" in command_kinds and {"CONSTR_UNIQUE", "CONSTR_PRIMARY"} & details:
                rule_id = "PG009"
                title = "Direct unique or primary-key constraint creation"
                reason = "Direct constraint creation can build an index under a strong lock."
                recommendation = "Build a unique index concurrently, then attach the constraint using the index."
            elif "AT_AddColumn" in command_kinds and "DEFAULT" in details:
                rule_id = "PG010"
                title = "Adding a column with a default"
                reason = "A default can rewrite an existing table on older PostgreSQL versions or when non-constant."
                recommendation = "Add the column nullable, backfill in batches, then add the default and constraint."
        elif statement.kind == "DropStmt" and statement.object_kind == "index" and not statement.concurrent:
            rule_id = "PG011"
            title = "Dropping an index without CONCURRENTLY"
            reason = "A non-concurrent index drop can block concurrent table access."
            recommendation = "Use DROP INDEX CONCURRENTLY outside a transaction."

        if rule_id:
            findings.append(
                Finding(
                    rule_id=rule_id,
                    severity=severity,
                    title=title,
                    file=file,
                    line=line,
                    evidence=evidence,
                    reason=reason,
                    recommendation=recommendation,
                    confidence="medium",
                )
            )

    locking_ids = {"PG004", "PG005", "PG006", "PG008", "PG009", "PG010", "PG011"}
    locking_statement = any(
        statement.kind in {"IndexStmt", "DropStmt"}
        or any(command.kind in {"AT_AlterColumnType", "AT_SetNotNull", "AT_AddConstraint", "AT_AddColumn"} for command in statement.commands)
        for statement in statements
    )
    if not has_lock_timeout and (any(finding.rule_id in locking_ids for finding in findings) or locking_statement):
        first = next(
            (finding for finding in findings if finding.rule_id in locking_ids),
            None,
        )
        if first is None:
            first_statement = next(statement for statement in statements if statement.kind != "TransactionStmt")
            first_line, _first_column = _line_and_column(sql, first_statement.start)
            first = Finding(
                rule_id="INTERNAL",
                severity="info",
                title="locking operation",
                file=file,
                line=first_line,
                evidence=sql[first_statement.start : first_statement.start + first_statement.length].strip().rstrip(";").rstrip(),
                reason="",
                recommendation="",
            )
        findings.append(
            Finding(
                rule_id="PG012",
                severity="medium",
                title="Locking migration without lock_timeout",
                file=file,
                line=first.line,
                evidence=first.evidence,
                reason="Locking DDL without lock_timeout can queue behind long transactions and block application traffic.",
                recommendation="Set a bounded lock_timeout and retry the migration when the lock cannot be acquired promptly.",
                confidence="medium",
            )
        )
    return findings
