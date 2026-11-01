"""Configuration: `.agents/workflow.toml`, its defaults and its validation."""
from __future__ import annotations

import pathlib
import re
import tomllib


DEFAULT_STATUSES = {
    "done": "✅",
    "in_progress": "🔄",
    "pending": "⏳",
    "deferred": "⏸️",
    "proposed": "📝",
}
# Built from `[tickets].id_pattern` (see `commit_pattern`).
DEFAULT_COMMIT_TEMPLATE = r"^[a-z]+\([a-z0-9_-]+\): (?:{id}) - .+"
KNOWN_TOP_LEVEL = {"project", "tickets", "commits", "size", "gates", "sensitive", "checks", "efficiency"}
KNOWN_CHECKS = ("backlog", "honest_closing", "sizes")
EFFICIENCY_DEFAULTS = {
    "light_max_lines": 30,        # a non-docs diff this small is self-reviewed
    "auditor_min_criteria": 3,    # launch test-auditor from this many criteria
    "gate_tail_lines": 15,        # lines of a failing gate shown in the report
    "gate_timeout_seconds": 1800,
    "doc_globs": ["**/*.md", "**/*.txt", "docs/**"],
}
CACHE_DIR = ".agents/.cache/gates"


class ConfigError(Exception):
    """The configuration is missing or invalid."""


def kit_dir(root: pathlib.Path) -> pathlib.Path:
    return root / ".agents"


def load_config(root: pathlib.Path) -> dict:
    path = kit_dir(root) / "workflow.toml"
    if not path.exists():
        raise ConfigError(f"{path.relative_to(root)} not found (run the workflow init command)")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path.relative_to(root)}: invalid TOML: {exc}") from exc
    return data


def tickets_cfg(cfg: dict) -> dict:
    t = dict(cfg.get("tickets", {}))
    t.setdefault("dir", "docs/tickets")
    t.setdefault("backlog", f"{t['dir']}/README.md")
    t.setdefault("id_pattern", r"T\d+\.\d+")
    t.setdefault("file_glob", "T*.md")
    t.setdefault("header_status", r"^>\s*\*\*Status:\*\*\s*(.*)$")
    t.setdefault("done_requires_section", "Acceptance Criteria")
    t.setdefault("done_min_criteria", 1)
    statuses = dict(DEFAULT_STATUSES)
    statuses.update(t.get("statuses", {}))
    t["statuses"] = statuses
    return t


def commit_pattern(cfg: dict) -> str:
    """The configured commit pattern, or the default built from the ticket id pattern."""
    default = DEFAULT_COMMIT_TEMPLATE.replace("{id}", tickets_cfg(cfg)["id_pattern"])
    return cfg.get("commits", {}).get("pattern", default)


def validate_config(cfg: dict, errors: list[str], warnings: list[str]) -> None:
    for key in cfg:
        if key not in KNOWN_TOP_LEVEL:
            warnings.append(f"workflow.toml: unknown section [{key}] (ignored)")
    t = tickets_cfg(cfg)
    for field in ("id_pattern", "header_status"):
        try:
            re.compile(t[field])
        except re.error as exc:
            errors.append(f"workflow.toml: [tickets].{field} is not a valid regex: {exc}")
    pattern = commit_pattern(cfg)
    try:
        re.compile(pattern)
    except re.error as exc:
        errors.append(f"workflow.toml: [commits].pattern is not a valid regex: {exc}")
    plain = {k: str(v).replace("\ufe0f", "") for k, v in t["statuses"].items()}
    for a in plain:
        for b in plain:
            if a < b and (plain[a] in plain[b] or plain[b] in plain[a]):
                errors.append(f"workflow.toml: statuses «{a}» and «{b}» cannot be told apart")
    minimum = t["done_min_criteria"]
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
        errors.append("workflow.toml: [tickets].done_min_criteria must be a whole number >= 0")
    for key, value in cfg.get("efficiency", {}).items():
        default = EFFICIENCY_DEFAULTS.get(key)
        if default is None:
            warnings.append(f"workflow.toml: unknown key «{key}» in [efficiency] (ignored)")
        elif isinstance(default, list) != isinstance(value, list) or (
            isinstance(default, int) and (isinstance(value, bool) or not isinstance(value, int) or value < 0)
        ):
            errors.append(f"workflow.toml: [efficiency].{key} has an invalid value")
    checks = cfg.get("checks", {})
    for name, enabled in checks.items():
        if name not in KNOWN_CHECKS:
            warnings.append(f"workflow.toml: unknown check «{name}» in [checks]")
        elif enabled is False:
            warnings.append(f"check «{name}» is DISABLED in workflow.toml")


def efficiency(cfg: dict) -> dict:
    out = dict(EFFICIENCY_DEFAULTS)
    out.update(cfg.get("efficiency", {}))
    return out


def check_enabled(cfg: dict, name: str) -> bool:
    return cfg.get("checks", {}).get(name, True) is not False
