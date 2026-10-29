from pglast import ast
from pglast.parser import ParseError, parse_sql, scan

from migration_guard.ports.parser import (
    Command,
    ParseResult,
    ParserError,
    Statement,
    Token,
)


class PglastParser:
    def parse(self, sql: str) -> ParseResult:
        try:
            raw_statements = parse_sql(sql)
        except ParseError as error:
            raise ParserError(str(error)) from error

        statements: list[Statement] = []
        for raw_statement in raw_statements:
            node = raw_statement.stmt
            commands: tuple[Command, ...] = ()
            table: str | None = None
            object_kind: str | None = None
            objects: tuple[str, ...] = ()
            cascade = False
            missing_ok = False
            restart_identity = False
            rename_kind: str | None = None
            old_name: str | None = None
            new_name: str | None = None
            concurrent = False
            variable_name: str | None = None
            transaction_kind: str | None = None
            if isinstance(node, ast.AlterTableStmt):
                table = node.relation.relname
                normalized_commands = []
                for command in node.cmds:
                    definition = getattr(command, "def_", None)
                    constraint_type = getattr(definition, "contype", None)
                    detail = constraint_type.name if constraint_type else None
                    if detail is None and any(
                        getattr(constraint, "contype", None).name == "CONSTR_DEFAULT"
                        for constraint in (getattr(definition, "constraints", None) or ())
                        if getattr(constraint, "contype", None)
                    ):
                        detail = "DEFAULT"
                    if detail is None and getattr(definition, "raw_default", None) is not None:
                        detail = "DEFAULT"
                    normalized_commands.append(
                        Command(
                            kind=command.subtype.name,
                            name=getattr(command, "name", None),
                            detail=detail,
                        )
                    )
                commands = tuple(normalized_commands)
            elif isinstance(node, ast.DropStmt):
                object_kind = node.removeType.name.removeprefix("OBJECT_").lower()
                if object_kind == "schema":
                    objects = tuple(item.sval for item in node.objects)
                else:
                    objects = tuple(
                        ".".join(item.sval for item in object_path)
                        for object_path in node.objects
                    )
                cascade = node.behavior.name == "DROP_CASCADE"
                missing_ok = node.missing_ok
                concurrent = node.concurrent
            elif isinstance(node, ast.TruncateStmt):
                object_kind = "table"
                objects = tuple(
                    ".".join(part for part in (relation.schemaname, relation.relname) if part)
                    for relation in node.relations
                )
                cascade = node.behavior.name == "DROP_CASCADE"
                restart_identity = node.restart_seqs
            elif isinstance(node, ast.RenameStmt):
                table = ".".join(
                    part
                    for part in (node.relation.schemaname, node.relation.relname)
                    if part
                )
                rename_kind = node.renameType.name.removeprefix("OBJECT_").lower()
                old_name = node.subname or node.relation.relname
                new_name = node.newname
            elif isinstance(node, ast.IndexStmt):
                concurrent = node.concurrent
            elif isinstance(node, ast.VariableSetStmt):
                variable_name = node.name
            elif isinstance(node, ast.TransactionStmt):
                transaction_kind = node.kind.name

            statements.append(
                Statement(
                    kind=type(node).__name__,
                    table=table,
                    commands=commands,
                    start=max(raw_statement.stmt_location, 0),
                    length=raw_statement.stmt_len,
                    object_kind=object_kind,
                    objects=objects,
                    cascade=cascade,
                    missing_ok=missing_ok,
                    restart_identity=restart_identity,
                    rename_kind=rename_kind,
                    old_name=old_name,
                    new_name=new_name,
                    concurrent=concurrent,
                    variable_name=variable_name,
                    transaction_kind=transaction_kind,
                )
            )
        return ParseResult(statements=tuple(statements))

    def tokenize(self, sql: str) -> tuple[Token, ...]:
        return tuple(
            Token(start=token.start, end=token.end + 1, name=token.name)
            for token in scan(sql)
        )
