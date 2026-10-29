from pathlib import Path

from migration_guard.adapters.parser_pglast import PglastParser
from migration_guard.ports.parser import Parser


def test_pglast_adapter_implements_parser_port():
    assert isinstance(PglastParser(), Parser)


def test_parser_port_exposes_normalized_statement_and_token_data():
    result = PglastParser().parse("ALTER TABLE customers DROP COLUMN email;")

    assert len(result.statements) == 1
    statement = result.statements[0]
    assert statement.kind == "AlterTableStmt"
    assert statement.table == "customers"
    assert statement.start == 0
    assert statement.length > 0
    assert statement.commands[0].kind == "AT_DropColumn"
    assert statement.commands[0].name == "email"

    tokens = PglastParser().tokenize("ALTER TABLE customers DROP COLUMN email;")
    assert [token.name for token in tokens[:2]] == ["ALTER", "TABLE"]
    assert all(token.end > token.start for token in tokens)


def test_production_modules_do_not_import_pglast_outside_adapter():
    source_root = Path(__file__).parents[1] / "src" / "migration_guard"
    adapter_root = source_root / "adapters" / "parser_pglast"

    for path in source_root.rglob("*.py"):
        if adapter_root in path.parents:
            continue
        contents = path.read_text(encoding="utf-8")
        assert "from pglast" not in contents, path
        assert "import pglast" not in contents, path
