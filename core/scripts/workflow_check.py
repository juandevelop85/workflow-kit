#!/usr/bin/env python3
"""Workflow checker: turns the rules a project wrote down into checks.

Everything project-specific comes from `.agents/workflow.toml`; nothing here
assumes a language, a directory layout or a product. Standard library only
(Python 3.11+, for `tomllib`).

Subcommands
-----------
check      (default) backlog coherence, honest closing, file sizes, commit
           format. Exit code 1 if there is any error; warnings do not fail.
gates      print the quality gates of the project, one `name<TAB>command` per
           line, resolved from the stack preset plus the project overrides.
sensitive  print the changed files that match the project's sensitive
           surfaces (the ones that require a security review).
context    print a compact brief of one ticket (status, dependencies and their
           status, acceptance criteria, rules to read) so the agent does not
           have to read the whole backlog.
review-plan  measure the diff and say which independent reviewers are worth
           launching (a tiny or docs-only change gets a self-review checklist).
gates --run  run the gates, keep the full output in a log file and print one
           line per gate (plus the tail of the ones that fail).

Every check or gate that the project has switched off is reported as a
warning on each run: a rule that can be silenced without anyone noticing is
not a rule.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import tomllib

DEFAULT_STATUSES = {
    "done": "✅",
    "in_progress": "🔄",
    "pending": "⏳",
    "deferred": "⏸️",
    "proposed": "📝",
}
DEFAULT_COMMIT_PATTERN = r"^[a-z]+\([a-z0-9_-]+\): T\d+\.\d+ - .+"
KNOWN_TOP_LEVEL = {"project", "tickets", "commits", "size", "gates", "sensitive", "checks", "efficiency"}
KNOWN_CHECKS = ("backlog", "honest_closing", "sizes")
ALWAYS_SKIPPED_DIRS = {".git"}
EFFICIENCY_DEFAULTS = {
    "light_max_lines": 30,        # a non-docs diff this small is self-reviewed
    "auditor_min_criteria": 3,    # launch test-auditor from this many criteria
    "gate_tail_lines": 15,        # lines of a failing gate shown in the report
    "gate_timeout_seconds": 1800,
    "doc_globs": ["**/*.md", "**/*.txt", "docs/**"],
}
CACHE_DIR = ".agents/.cache/gates"
# A repository can carry a configuration that makes git run a command (`core.fsmonitor`): switch
# that off. Run this checker only on repositories you would run `git` on.
GIT = ["git", "-c", "core.fsmonitor=false"]


class ConfigError(Exception):
    """The configuration is missing or invalid."""


# --------------------------------------------------------------------------- config

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
    statuses = dict(DEFAULT_STATUSES)
    statuses.update(t.get("statuses", {}))
    t["statuses"] = statuses
    return t


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
    pattern = cfg.get("commits", {}).get("pattern", DEFAULT_COMMIT_PATTERN)
    try:
        re.compile(pattern)
    except re.error as exc:
        errors.append(f"workflow.toml: [commits].pattern is not a valid regex: {exc}")
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


# --------------------------------------------------------------------------- globs

def glob_to_regex(pattern: str) -> re.Pattern:
    """`**` crosses directories, `*` and `?` do not. Anchored at the root."""
    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def iter_files(root: pathlib.Path, include: list[str], exclude: list[str]):
    inc = [glob_to_regex(p) for p in include]
    exc = [glob_to_regex(p) for p in exclude]
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = pathlib.PurePath(dirpath).relative_to(root).as_posix()
        def pruned(d: str) -> bool:
            rel_d = d if rel_dir == "." else f"{rel_dir}/{d}"
            return d in ALWAYS_SKIPPED_DIRS or any(e.match(f"{rel_d}/x") for e in exc)

        dirnames[:] = [d for d in dirnames if not pruned(d)]
        for name in filenames:
            rel = f"{rel_dir}/{name}" if rel_dir != "." else name
            if any(i.match(rel) for i in inc) and not any(e.match(rel) for e in exc):
                yield pathlib.Path(dirpath) / name, rel


# --------------------------------------------------------------------------- presets

def load_preset(root: pathlib.Path, name: str) -> dict:
    if name in ("", "none"):
        return {"gate": [], "size": {}}
    path = kit_dir(root) / "presets" / f"{name}.toml"
    if not path.exists():
        raise ConfigError(f"unknown stack preset «{name}» (no {path.relative_to(root)})")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def resolve_gates(root: pathlib.Path, cfg: dict) -> tuple[list[dict], list[str]]:
    """Gates = preset gates, with project overrides, plus project extras."""
    gates_cfg = cfg.get("gates", {})
    preset = load_preset(root, gates_cfg.get("preset", "none"))
    overrides = gates_cfg.get("override", {})
    gates, warnings = [], []
    for gate in preset.get("gate", []):
        name = gate["name"]
        ov = overrides.get(name, {})
        if ov.get("enabled", True) is False:
            warnings.append(f"gate «{name}» is DISABLED in workflow.toml")
            continue
        gates.append({"name": name, "command": ov.get("command", gate["command"])})
    for name in overrides:
        if name not in {g["name"] for g in preset.get("gate", [])}:
            warnings.append(f"workflow.toml: [gates.override.{name}] matches no gate of the preset")
    for extra in gates_cfg.get("extra", []):
        gates.append({"name": extra["name"], "command": extra["command"]})
    return gates, warnings


# --------------------------------------------------------------------------- checks

def status_of(text: str, statuses: dict):
    for symbol in statuses.values():
        if symbol in text:
            return symbol
    return None


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


# ---------------------------------------------------------------------- subcommands

def changed_files(root: pathlib.Path, base: str | None) -> list[str]:
    def git(*args):
        res = subprocess.run([*GIT, *args], cwd=root, capture_output=True, text=True)
        return res.stdout.splitlines() if res.returncode == 0 else []
    files = set(git("diff", "--name-only")) | set(git("diff", "--name-only", "--cached"))
    files |= set(git("ls-files", "--others", "--exclude-standard"))
    if base:
        files |= set(git("diff", "--name-only", f"{base}...HEAD"))
    return sorted(files)


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


def run_gates(root: pathlib.Path, as_json: bool) -> int:
    try:
        cfg = load_config(root)
        gates, warnings = resolve_gates(root, cfg)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if as_json:
        print(json.dumps(gates, indent=2))
    else:
        for g in gates:
            print(f"{g['name']}\t{g['command']}")
    return 0


def run_sensitive(root: pathlib.Path, base: str | None, files: list[str]) -> int:
    try:
        cfg = load_config(root)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    globs = cfg.get("sensitive", {}).get("globs", [])
    candidates = files or changed_files(root, base)
    regexes = [glob_to_regex(g) for g in globs]
    for rel in candidates:
        if any(r.match(rel) for r in regexes):
            print(rel)
    return 0


def ticket_file(root: pathlib.Path, cfg: dict, tid: str) -> pathlib.Path | None:
    t = tickets_cfg(cfg)
    for path in sorted((root / t["dir"]).glob(t["file_glob"])):
        if path.name.startswith(tid) and not path.name[len(tid):len(tid) + 1].isdigit():
            return path
    return None


def section_of(body: str, title: str) -> str:
    m = re.search(rf"^##\s+{re.escape(title)}\s*$(.*?)(?=^##\s|\Z)", body, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def count_criteria(body: str, section: str) -> int:
    return len(re.findall(r"^\s*(?:[-*+]|\d+[.)])\s+\S", section_of(body, section), re.MULTILINE))


def backlog_rows(root: pathlib.Path, cfg: dict) -> dict[str, str]:
    t = tickets_cfg(cfg)
    backlog = root / t["backlog"]
    row_re = re.compile(rf"^\|.*?\[({t['id_pattern']})\]\(([^)]+)\).*\|\s*(.*?)\s*\|\s*$")
    rows: dict[str, str] = {}
    if backlog.exists():
        for line in backlog.read_text(encoding="utf-8").splitlines():
            m = row_re.match(line)
            if m:
                rows[m.group(1)] = m.group(3)
    return rows


def run_context(root: pathlib.Path, tid: str) -> int:
    try:
        cfg = load_config(root)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    t = tickets_cfg(cfg)
    path = ticket_file(root, cfg, tid)
    if path is None:
        print(f"ERROR: no ticket file for {tid} in {t['dir']}", file=sys.stderr)
        return 1
    body = path.read_text(encoding="utf-8")
    rows = backlog_rows(root, cfg)
    title = body.splitlines()[0].lstrip("# ").strip() if body else tid
    m = re.search(t["header_status"], body, re.MULTILINE)
    print(f"ticket: {title}")
    print(f"file: {path.relative_to(root).as_posix()}")
    print(f"status: backlog «{rows.get(tid, 'not in the backlog')}», header «{m.group(1).strip() if m else 'none'}»")
    dep_line = re.search(r"^>\s*\*\*Depends on:\*\*\s*(.*)$", body, re.MULTILINE)
    deps = re.findall(t["id_pattern"], dep_line.group(1)) if dep_line else []
    if deps:
        print("depends on:")
        for dep in deps:
            status = rows.get(dep, "not in the backlog")
            done = t["statuses"]["done"] in status
            print(f"  {dep}: {status}" + ("" if done else "   <-- NOT DONE"))
    else:
        print("depends on: none")
    print("rules to read: " + (", ".join(cfg.get("project", {}).get("rules", [])) or "none"))
    for heading in ("Description", "Technical Scope", "Acceptance Criteria"):
        text = section_of(body, heading)
        print(f"\n## {heading}\n{text or '(missing)'}")
    return 0


def numstat(root: pathlib.Path, *args: str) -> dict[str, int]:
    res = subprocess.run([*GIT, "diff", "--numstat", *args], cwd=root, capture_output=True, text=True)
    out: dict[str, int] = {}
    for line in res.stdout.splitlines() if res.returncode == 0 else []:
        added, removed, name = (line.split("\t", 2) + ["", ""])[:3]
        out[name] = out.get(name, 0) + sum(int(n) for n in (added, removed) if n.isdigit())
    return out


def diff_size(root: pathlib.Path, base: str | None) -> dict[str, int]:
    sizes = numstat(root, "HEAD")
    if base:
        for name, n in numstat(root, f"{base}...HEAD").items():
            sizes[name] = max(sizes.get(name, 0), n)
    untracked = subprocess.run([*GIT, "ls-files", "--others", "--exclude-standard"], cwd=root,
                               capture_output=True, text=True).stdout.splitlines()
    for name in untracked:
        path = root / name
        if path.is_file() and not path.is_symlink():
            sizes[name] = sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
    return sizes


def plan_review(root: pathlib.Path, cfg: dict, base: str | None, tid: str | None, files: dict[str, int]) -> dict:
    eff = efficiency(cfg)
    total = sum(files.values())
    docs = [glob_to_regex(g) for g in eff["doc_globs"]]
    docs_only = bool(files) and all(any(r.match(f) for r in docs) for f in files)
    sens = [glob_to_regex(g) for g in cfg.get("sensitive", {}).get("globs", [])]
    sensitive = sorted(f for f in files if any(r.match(f) for r in sens))
    criteria = None
    if tid:
        path = ticket_file(root, cfg, tid)
        if path:
            criteria = count_criteria(path.read_text(encoding="utf-8"),
                                      tickets_cfg(cfg)["done_requires_section"] or "Acceptance Criteria")
    launch, reasons = [], []
    if not files:
        reasons.append("no changes")
    elif docs_only or total <= eff["light_max_lines"]:
        reasons.append(("docs-only change" if docs_only else f"{total} changed lines <= {eff['light_max_lines']}")
                       + ": self-review against the ticket and the rules, no subagent")
    else:
        launch.append("reviewer")
        reasons.append(f"{total} changed lines in {len(files)} file(s)")
        if criteria is not None and criteria >= eff["auditor_min_criteria"]:
            launch.append("test-auditor")
            reasons.append(f"{criteria} acceptance criteria >= {eff['auditor_min_criteria']}")
    if sensitive:
        launch.append("security-reviewer")
        reasons.append("touches a sensitive surface: " + ", ".join(sensitive))
    return {"files": len(files), "lines": total, "docs_only": docs_only, "criteria": criteria,
            "launch": launch, "reasons": reasons}


def run_review_plan(root: pathlib.Path, base: str | None, tid: str | None, as_json: bool) -> int:
    try:
        cfg = load_config(root)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    plan = plan_review(root, cfg, base, tid, diff_size(root, base))
    if as_json:
        print(json.dumps(plan, indent=2))
    else:
        print(f"diff: {plan['files']} file(s), {plan['lines']} changed line(s)")
        print("launch: " + (" ".join(plan["launch"]) or "none"))
        print("why: " + "; ".join(plan["reasons"]))
    return 0


def run_gates_report(root: pathlib.Path, tail: int | None) -> int:
    """Run every gate; keep the full output on disk, print only what a decision needs."""
    try:
        cfg = load_config(root)
        gates, warnings = resolve_gates(root, cfg)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    eff = efficiency(cfg)
    tail = eff["gate_tail_lines"] if tail is None else tail
    for w in warnings:
        print(f"warning: {w}")
    logs = root / CACHE_DIR
    logs.mkdir(parents=True, exist_ok=True)
    (root / ".agents/.cache/.gitignore").write_text("*\n", encoding="utf-8")
    failed = 0
    for gate in gates:
        log = logs / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', gate['name'])}.log"
        started = time.monotonic()
        try:
            res = subprocess.run(gate["command"], shell=True, cwd=root, capture_output=True, text=True,
                                 errors="replace", timeout=eff["gate_timeout_seconds"])
            code, output = res.returncode, res.stdout + res.stderr
        except subprocess.TimeoutExpired as exc:
            code, output = 124, f"timed out after {eff['gate_timeout_seconds']}s\n{exc.stdout or ''}"
        log.write_text(output if isinstance(output, str) else output.decode(errors="replace"), encoding="utf-8")
        took = time.monotonic() - started
        rel = log.relative_to(root).as_posix()
        if code == 0:
            print(f"PASS {gate['name']} ({took:.1f}s)")
        else:
            failed += 1
            print(f"FAIL {gate['name']} (exit {code}, {took:.1f}s) full output: {rel}")
            for line in output.splitlines()[-tail:] if tail else []:
                print(f"  | {line}")
    print(f"\n{len(gates)} gate(s): {len(gates) - failed} passed, {failed} failed")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-") or argv[0] not in {"check", "gates", "sensitive", "context", "review-plan"}:
        argv.insert(0, "check")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    default_root = str(pathlib.Path(__file__).resolve().parents[2])
    for name in ("check", "gates", "sensitive", "context", "review-plan"):
        p = sub.add_parser(name)
        p.add_argument("--root", default=default_root)
        if name == "check":
            p.add_argument("--commits", type=int, default=0, help="also check the last N commit subjects")
        if name == "gates":
            p.add_argument("--json", action="store_true")
            p.add_argument("--run", action="store_true", help="run the gates and print a compact report")
            p.add_argument("--tail", type=int, default=None, help="lines of a failing gate to show (with --run)")
        if name == "context":
            p.add_argument("ticket", help="ticket id, e.g. T1.1")
        if name == "review-plan":
            p.add_argument("--base", default=None, help="also count changes since this ref")
            p.add_argument("--ticket", default=None, help="ticket id, to count its acceptance criteria")
            p.add_argument("--json", action="store_true")
        if name == "sensitive":
            p.add_argument("--base", default=None, help="also include files changed since this ref")
            p.add_argument("files", nargs="*", help="check these paths instead of the git changes")
    args = ap.parse_args(argv)
    root = pathlib.Path(args.root)
    if args.cmd == "context":
        return run_context(root, args.ticket)
    if args.cmd == "review-plan":
        return run_review_plan(root, args.base, args.ticket, args.json)
    if args.cmd == "gates":
        if args.run:
            return run_gates_report(root, args.tail)
        return run_gates(root, args.json)
    if args.cmd == "sensitive":
        return run_sensitive(root, args.base, args.files)
    return run_check(root, args.commits)


if __name__ == "__main__":
    sys.exit(main())
