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


@dataclass(frozen=True)
class Statement:
    kind: str
    table: str | None
    commands: tuple[Command, ...]
    start: int
    length: int


@dataclass(frozen=True)
class ParseResult:
    statements: tuple[Statement, ...]


@runtime_checkable
class Parser(Protocol):
    def parse(self, sql: str) -> ParseResult: ...

    def tokenize(self, sql: str) -> tuple[Token, ...]: ...
