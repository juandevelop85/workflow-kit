"""The `check` subcommand: backlog coherence, honest closing, sizes and commit format."""
from __future__ import annotations

import pathlib
import re
import subprocess

from .config import ConfigError, DEFAULT_COMMIT_PATTERN, check_enabled, load_config, tickets_cfg, validate_config
from .gates import load_preset, resolve_gates
from .gitutil import GIT
from .globs import iter_files
from .tickets import status_of


def check_backlog(root, cfg, errors, warnings):
    t = tickets_cfg(cfg)
    tickets = root / t["dir"]
    backlog = root / t["backlog"]
    if not backlog.exists():
        errors.append(f"{t['backlog']}: backlog file not found")
        return
    row_re = re.compile(rf"^\|.*?\[({t['id_pattern']})\]\(([^)]+)\).*\|\s*(.*?)\s*\|\s*$")
    header_re = re.compile(t["header_status"], re.MULTILINE)
    statuses = t["statuses"]
    done_symbol = statuses["done"]
    rows = {}
    for line in backlog.read_text(encoding="utf-8").splitlines():
        m = row_re.match(line)
        if m:
            tid, link, status = m.groups()
            rows[tid] = (pathlib.PurePosixPath(link).name, status)
    files = {p.name: p for p in tickets.glob(t["file_glob"]) if p.name != backlog.name}
    for tid, (name, status) in rows.items():
        path = files.get(name)
        if path is None:
            errors.append(f"backlog: {tid} links to {name}, which does not exist")
            continue
        body = path.read_text(encoding="utf-8")
        m = header_re.search(body)
        header = status_of(m.group(1), statuses) if m else None
        row_status = status_of(status, statuses)
        if header is None:
            warnings.append(f"{name}: no status line (only the backlog row counts)")
        elif header != row_status:
            errors.append(f"{name}: ticket status {header} differs from backlog {row_status}")
        section = t["done_requires_section"]
        if check_enabled(cfg, "honest_closing") and section:
            if row_status == done_symbol and section not in body:
                errors.append(f"{name}: marked done but has no «{section}» section")
    indexed = {name for name, _ in rows.values()}
    for name in sorted(set(files) - indexed):
        errors.append(f"{name}: does not appear in the backlog")


def read_baseline(root: pathlib.Path, cfg: dict) -> dict[str, int]:
    rel = cfg.get("size", {}).get("baseline", ".agents/baseline.txt")
    path = root / rel
    baseline: dict[str, int] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                name, limit = line.rsplit(None, 1)
                baseline[name] = int(limit)
    return baseline


def check_sizes(root, cfg, errors, warnings):
    size = cfg.get("size", {})
    preset = load_preset(root, cfg.get("gates", {}).get("preset", "none"))
    include = size.get("include", preset.get("size", {}).get("include", []))
    exclude = list(size.get("exclude", preset.get("size", {}).get("exclude", [])))
    # The kit's own files are not the project's code, whatever the stack.
    exclude += [".agents/**", ".claude/**"]
    if not include:
        warnings.append("size: no [size].include globs and no stack preset: sizes not checked")
        return
    warn_at = int(size.get("warn_lines", 800))
    max_at = int(size.get("error_lines", 1500))
    baseline = read_baseline(root, cfg)
    for path, rel in sorted(iter_files(root, include, exclude), key=lambda x: x[1]):
        if path.is_symlink():
            continue  # never follow a link out of the repository (or into a device file)
        lines = sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
        if rel in baseline:
            if lines > baseline[rel]:
                errors.append(f"{rel}: {lines} lines, grows over its baseline ({baseline[rel]})")
            else:
                warnings.append(f"{rel}: {lines} lines (acknowledged debt, limit {max_at})")
        elif lines > max_at:
            errors.append(f"{rel}: {lines} lines > {max_at}: split it in the same change")
        elif lines > warn_at:
            warnings.append(f"{rel}: {lines} lines > {warn_at}: consider splitting it")


def check_commits(root, cfg, count, errors):
    pattern = re.compile(cfg.get("commits", {}).get("pattern", DEFAULT_COMMIT_PATTERN))
    hint = cfg.get("commits", {}).get("format_hint", "<type>(<area>): <TID> - <title>")
    out = subprocess.run(
        [*GIT, "log", f"-n{count}", "--no-merges", "--format=%h %s"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    for line in out:
        sha, _, subject = line.partition(" ")
        if not pattern.match(subject):
            errors.append(f"commit {sha}: «{subject}» does not follow {hint}")


def run_check(root: pathlib.Path, commits: int) -> int:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        cfg = load_config(root)
    except ConfigError as exc:
        print(f"ERROR: {exc}")
        return 1
    validate_config(cfg, errors, warnings)
    if not errors:
        try:
            # Resolves the preset first: an unknown one is a clear error, not a traceback.
            _, gate_warnings = resolve_gates(root, cfg)
            warnings.extend(gate_warnings)
            if check_enabled(cfg, "backlog"):
                check_backlog(root, cfg, errors, warnings)
            if check_enabled(cfg, "sizes"):
                check_sizes(root, cfg, errors, warnings)
            if commits:
                check_commits(root, cfg, commits, errors)
        except ConfigError as exc:
            errors.append(str(exc))
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0
