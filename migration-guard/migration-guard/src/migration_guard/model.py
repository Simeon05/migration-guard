from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class SourceSpan:
    file: str
    start_line: int
    start_col: int
    end_line: int | None = None
    end_col: int | None = None
    start_byte: int | None = None
    end_byte: int | None = None


@dataclass(frozen=True)
class LockInfo:
    mode: str
    relation: str | None = None
    duration_class: str = "unknown"
    blocks: tuple[str, ...] = ()
    version_notes: str | None = None


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    title: str
    file: str
    line: int
    evidence: str
    reason: str
    recommendation: str
    column: int = 1
    message: str | None = None
    why_it_matters: str | None = None
    safe_rewrite: str | None = None
    lock_level: str | None = None
    confidence: str = Confidence.HIGH.value
    docs_url: str | None = None
    span: SourceSpan | None = None
    lock: LockInfo | None = None
    rewrites_table: bool | None = None
    compat: str = "unknown"
    fingerprint: str | None = None
