"""The `check` subcommand: backlog coherence, honest closing, sizes and commit format."""
from __future__ import annotations

import os
import pathlib
import re
import subprocess

from .config import ConfigError, check_enabled, commit_pattern, load_config, tickets_cfg, validate_config
from .gates import load_preset, resolve_gates
from .gitutil import GIT
from .globs import iter_files
from .tickets import backlog_rows, count_criteria, parse_backlog, status_of


def check_backlog(root, cfg, errors, warnings):
    t = tickets_cfg(cfg)
    tickets = root / t["dir"]
    backlog = root / t["backlog"]
    if not backlog.exists():
        errors.append(f"{t['backlog']}: backlog file not found")
        return
    header_re = re.compile(t["header_status"], re.MULTILINE)
    statuses = t["statuses"]
    done_symbol = statuses["done"]
    rows = {}
    for tid, link, status in parse_backlog(backlog, t["id_pattern"]):
        if tid in rows:
            errors.append(f"backlog: {tid} appears more than once")
            continue
        rows[tid] = (link, pathlib.PurePosixPath(link).name, status)
    files = {p.name: p for p in tickets.glob(t["file_glob"]) if p.name != backlog.name}
    for tid, (link, name, status) in rows.items():
        path = files.get(name)
        if path is None:
            errors.append(f"backlog: {tid} links to {name}, which does not exist")
            continue
        if (backlog.parent / link).resolve() != path.resolve():
            errors.append(f"backlog: {tid} links to {link}, but its file is {path.relative_to(root).as_posix()}")
        body = path.read_text(encoding="utf-8")
        m = header_re.search(body)
        header = status_of(m.group(1), statuses) if m else None
        row_status = status_of(status, statuses)
        if header is None:
            warnings.append(f"{name}: no status line (only the backlog row counts)")
        elif header != row_status:
            errors.append(f"{name}: ticket status {header} differs from backlog {row_status}")
        section = t["done_requires_section"]
        if check_enabled(cfg, "honest_closing") and section and row_status == done_symbol:
            if not re.search(rf"^##\s+{re.escape(section)}\s*$", body, re.MULTILINE):
                errors.append(f"{name}: marked done but has no «## {section}» heading")
            elif count_criteria(body, section) < t["done_min_criteria"]:
                errors.append(f"{name}: marked done but «{section}» lists {count_criteria(body, section)} "
                              f"criteria (minimum {t['done_min_criteria']})")
    indexed = {name for _, name, _ in rows.values()}
    for name in sorted(set(files) - indexed):
        errors.append(f"{name}: does not appear in the backlog")


def read_baseline(root: pathlib.Path, cfg: dict) -> dict[str, int]:
    rel = cfg.get("size", {}).get("baseline", ".agents/baseline.txt")
    path = root / rel
    baseline: dict[str, int] = {}
    if path.exists():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip() and not line.lstrip().startswith("#"):
                parts = line.rsplit(None, 1)
                if len(parts) != 2 or not re.fullmatch(r"[0-9]+", parts[1]):
                    raise ConfigError(f"{rel}:{number}: expected «<path> <maximum lines>», got «{line.strip()}»")
                baseline[parts[0].strip()] = int(parts[1])
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


def git_c(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    """git with messages in English, whatever the locale, so errors can be quoted."""
    return subprocess.run([*GIT, *args], cwd=root, capture_output=True, text=True,
                          env={**os.environ, "LC_ALL": "C"})


def check_commits(root, cfg, count, errors, warnings):
    commits = cfg.get("commits", {})
    pattern = re.compile(commit_pattern(cfg))
    hint = commits.get("format_hint", "<type>(<area>): <TID> - <title>")
    id_re = re.compile(tickets_cfg(cfg)["id_pattern"])
    known = backlog_rows(root, cfg)
    if git_c(root, "rev-parse", "--git-dir").returncode != 0:
        errors.append("the commit check needs a git repository")
        return
    # History from before the project adopted the kit is exempted explicitly, never silently.
    span = []
    since = commits.get("since")
    if since:
        if git_c(root, "rev-parse", "--verify", "--quiet", f"{since}^{{commit}}").returncode == 0:
            span = [f"{since}..HEAD"]
        elif git_c(root, "rev-parse", "--is-shallow-repository").stdout.strip() == "true":
            warnings.append(f"[commits].since «{since}» is not in this shallow clone: checking the last "
                            f"{count} commits instead (fetch the full history to exempt older ones)")
        else:
            errors.append(f"[commits].since «{since}» is not a commit of this repository")
            return
    res = git_c(root, "log", f"-n{count}", "--no-merges", "--format=%h %s", *span)
    if res.returncode != 0:
        fatal = [line for line in res.stderr.splitlines() if line.startswith("fatal:")]
        errors.append("git log failed: " + (fatal or res.stderr.strip().splitlines() or ["no output"])[0])
        return
    for line in res.stdout.splitlines():
        sha, _, subject = line.partition(" ")
        if not pattern.match(subject):
            errors.append(f"commit {sha}: «{subject}» does not follow {hint}")
            continue
        # Ids are read after the `(area): ` prefix, so an area like `api2` is never taken for one.
        title = subject.split("): ", 1)[1] if "): " in subject else subject
        for cited in sorted({m.group(0) for m in id_re.finditer(title)}):
            if cited not in known:
                errors.append(f"commit {sha}: cites {cited}, which is not in the backlog "
                              "(history from before the kit: set [commits].since)")


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
                check_commits(root, cfg, commits, errors, warnings)
        except ConfigError as exc:
            errors.append(str(exc))
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0
