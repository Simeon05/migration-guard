from pathlib import Path

import typer

from migration_guard.config import Config, load_config
from migration_guard.ports.parser import ParserError
from migration_guard.reporters.json import render_json
from migration_guard.reporters.sarif import render_sarif
from migration_guard.rules import (
    detect_destructive_operations,
    detect_dropped_columns,
    detect_renames,
    detect_not_null_changes,
    detect_index_creation,
    detect_remaining_risks,
    detect_type_changes,
)
from migration_guard.suppress import apply_suppressions


app = typer.Typer(help="Check PostgreSQL migrations for potential risks.")


@app.callback()
def main() -> None:
    """Check PostgreSQL migrations for potential risks."""


@app.command()
def check(
    paths: list[Path],
    format: str = typer.Option("text", "--format"),
    fail_on: str | None = typer.Option(None, "--fail-on"),
    config_path: Path | None = typer.Option(None, "--config"),
) -> None:
    """Analyse PostgreSQL migration files or directories."""
    if format not in {"text", "json", "sarif"}:
        typer.echo(f"Error: Unsupported format: {format}", err=True)
        raise typer.Exit(code=2)

    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(item for item in path.rglob("*.sql") if item.is_file())
        else:
            typer.echo(f"Error: File not found: {path}", err=True)
            raise typer.Exit(code=2)

    try:
        config = load_config(config_path) if config_path else Config()
    except (OSError, ValueError) as error:
        typer.echo(f"Error: Could not load config: {error}", err=True)
        raise typer.Exit(code=2) from error

    threshold = fail_on or config.fail_on
    if threshold not in {"info", "low", "medium", "high"}:
        typer.echo(f"Error: Unsupported fail threshold: {threshold}", err=True)
        raise typer.Exit(code=2)

    severity_rank = {"info": 0, "low": 1, "medium": 2, "high": 3}
    findings = []
    suppressed_count = 0
    try:
        for file in sorted(set(files)):
            sql = file.read_text(encoding="utf-8")
            result = apply_suppressions(
                sql,
                detect_dropped_columns(sql, str(file))
                + detect_destructive_operations(sql, str(file))
                + detect_renames(sql, str(file))
                + detect_type_changes(sql, str(file))
                + detect_not_null_changes(sql, str(file))
                + detect_index_creation(sql, str(file))
                + detect_remaining_risks(sql, str(file)),
                require_reason=config.suppress_require_reason,
            )
            findings.extend(result.findings)
            suppressed_count += len(result.suppressed)
    except (ParserError, UnicodeDecodeError, ValueError) as error:
        typer.echo(f"Error: Could not analyse file: {error}", err=True)
        raise typer.Exit(code=2) from error

    if format == "json":
        typer.echo(render_json(findings), nl=False)
    elif format == "sarif":
        typer.echo(render_sarif(findings), nl=False)
    else:
        typer.echo("MigrationGuard")
        typer.echo("")
        if not findings:
            typer.echo("No supported risks detected.")
            typer.echo("This does not guarantee the migration is safe.")
        else:
            for finding in sorted(
                findings,
                key=lambda item: (item.file, item.line, item.column, item.rule_id),
            ):
                typer.echo(f"{finding.severity.upper()} {finding.rule_id} — {finding.title}")
                typer.echo(f"File: {finding.file}")
                typer.echo(f"Line: {finding.line}")
                typer.echo(f"Evidence: {finding.evidence}")
                typer.echo(f"Reason: {finding.reason}")
                typer.echo(f"Recommendation: {finding.recommendation}")
        if suppressed_count:
            typer.echo(f"Suppressed findings: {suppressed_count}")

    if any(severity_rank[finding.severity] >= severity_rank[threshold] for finding in findings):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
