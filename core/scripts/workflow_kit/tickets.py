"""Tickets and the backlog: statuses, sections, criteria and the `context` brief."""
from __future__ import annotations

import pathlib
import re
import sys

from .config import ConfigError, load_config, tickets_cfg


def status_of(text: str, statuses: dict):
    for symbol in statuses.values():
        if symbol in text:
            return symbol
    return None


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
