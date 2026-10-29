from pathlib import Path

import typer
from pglast.parser import ParseError

from migration_guard.rules import detect_dropped_columns


app = typer.Typer(help="Check PostgreSQL migrations for potential risks.")


@app.callback()
def main() -> None:
    """Check PostgreSQL migrations for potential risks."""


@app.command()
def check(file: Path) -> None:
    """Analyse a PostgreSQL migration file."""
    if not file.is_file():
        typer.echo(f"Error: File not found: {file}", err=True)
        raise typer.Exit(code=1)

    try:
        sql = file.read_text(encoding="utf-8")
        findings = detect_dropped_columns(sql, str(file))
    except (ParseError, UnicodeDecodeError) as error:
        typer.echo(f"Error: Could not analyse file: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo("MigrationGuard")
    typer.echo("")

    if not findings:
        typer.echo("No supported risks detected.")
        typer.echo("This does not guarantee the migration is safe.")
        return

    for finding in findings:
        typer.echo(f"{finding.severity.upper()} {finding.rule_id} — {finding.title}")
        typer.echo(f"File: {finding.file}")
        typer.echo(f"Line: {finding.line}")
        typer.echo(f"Evidence: {finding.evidence}")
        typer.echo(f"Reason: {finding.reason}")
        typer.echo(f"Recommendation: {finding.recommendation}")


if __name__ == "__main__":
    app()
