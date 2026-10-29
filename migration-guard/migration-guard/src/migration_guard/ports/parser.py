from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class ParserError(ValueError):
    """Raised when a migration cannot be parsed."""


@dataclass(frozen=True)
class Token:
    start: int
    end: int
    name: str


@dataclass(frozen=True)
class Command:
    kind: str
    name: str | None
    detail: str | None = None


@dataclass(frozen=True)
class Statement:
    kind: str
    table: str | None
    commands: tuple[Command, ...]
    start: int
    length: int
    object_kind: str | None = None
    objects: tuple[str, ...] = ()
    cascade: bool = False
    missing_ok: bool = False
    restart_identity: bool = False
    rename_kind: str | None = None
    old_name: str | None = None
    new_name: str | None = None
    concurrent: bool = False
    variable_name: str | None = None
    transaction_kind: str | None = None


@dataclass(frozen=True)
class ParseResult:
    statements: tuple[Statement, ...]


@runtime_checkable
class Parser(Protocol):
    def parse(self, sql: str) -> ParseResult: ...

    def tokenize(self, sql: str) -> tuple[Token, ...]: ...
