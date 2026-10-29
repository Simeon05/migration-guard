from dataclasses import dataclass, field
from pathlib import Path
import tomllib
from typing import Any


@dataclass(frozen=True)
class Config:
    target_version: int = 14
    fail_on: str = "high"
    deploy_model: str = "migrate-before-deploy"
    rule_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    migrations: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    code_roots: tuple[str, ...] = ()
    orm: tuple[str, ...] = ()
    suppress_require_reason: bool = False
    suppress_max_age_days: int | None = None


def load_config(path: Path) -> Config:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"could not load config {path}: {error}") from error

    allowed = {"core", "rules", "paths", "code", "suppress"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"unknown config section(s): {', '.join(sorted(unknown))}")

    core = raw.get("core", {})
    rules = raw.get("rules", {})
    paths = raw.get("paths", {})
    code = raw.get("code", {})
    suppress = raw.get("suppress", {})
    for name, value in (("core", core), ("rules", rules), ("paths", paths), ("code", code), ("suppress", suppress)):
        if not isinstance(value, dict):
            raise ValueError(f"config section {name!r} must be a table")

    target_version = core.get("target_version", 14)
    fail_on = core.get("fail_on", "high")
    deploy_model = core.get("deploy_model", "migrate-before-deploy")
    if not isinstance(target_version, int):
        raise ValueError("core.target_version must be an integer")
    if fail_on not in {"info", "low", "medium", "high"}:
        raise ValueError("core.fail_on must be info, low, medium, or high")
    if deploy_model not in {"migrate-before-deploy", "migrate-after-deploy", "blue-green"}:
        raise ValueError("core.deploy_model is invalid")

    return Config(
        target_version=target_version,
        fail_on=fail_on,
        deploy_model=deploy_model,
        rule_overrides=rules,
        migrations=tuple(paths.get("migrations", [])),
        exclude=tuple(paths.get("exclude", [])),
        code_roots=tuple(code.get("roots", [])),
        orm=tuple(code.get("orm", [])),
        suppress_require_reason=bool(suppress.get("require_reason", False)),
        suppress_max_age_days=suppress.get("max_age_days"),
    )
