"""Tickets and the backlog: statuses, sections, criteria and the `context` brief."""
from __future__ import annotations

import pathlib
import re
import sys

from .config import ConfigError, load_config, tickets_cfg


VARIATION_SELECTOR = "\ufe0f"


def status_of(text: str, statuses: dict):
    """The status symbol found in `text`; `⏸` and `⏸️` (with U+FE0F) are the same symbol."""
    plain = text.replace(VARIATION_SELECTOR, "")
    for symbol in statuses.values():
        if symbol.replace(VARIATION_SELECTOR, "") in plain:
            return symbol
    return None


def parse_backlog(backlog: pathlib.Path, id_pattern: str) -> list[tuple[str, str, str]]:
    """(ticket id, link, status cell) for every ticket row of the backlog table, in order."""
    row_re = re.compile(rf"^\|.*?\[({id_pattern})\]\(([^)]+)\).*\|\s*(.*?)\s*\|\s*$")
    rows = []
    for line in backlog.read_text(encoding="utf-8").splitlines():
        m = row_re.match(line)
        if m:
            rows.append(m.groups())
    return rows


def ticket_file(root: pathlib.Path, cfg: dict, tid: str) -> pathlib.Path | None:
    t = tickets_cfg(cfg)
    for path in sorted((root / t["dir"]).glob(t["file_glob"])):
        if path.name.startswith(tid) and not path.name[len(tid):len(tid) + 1].isdigit():
            return path
    return None


def section_of(body: str, title: str) -> str:
    """The text under `## <title>` up to the next `## ` heading; headings inside code fences do not count."""
    out, inside, fenced = [], False, False
    for line in body.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced and re.match(r"^##\s", line):
            inside = re.fullmatch(rf"##\s+{re.escape(title)}\s*", line) is not None
            continue
        if inside:
            out.append(line)
    return "\n".join(out).strip()


def count_criteria(body: str, section: str) -> int:
    """Top-level list items with text (`-`, `*`, `+`, `1.`), outside code fences; `- [ ]` alone is empty."""
    count, fenced = 0, False
    for line in section_of(body, section).splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced:
            item = re.match(r"^ ?(?:[-*+]|\d+[.)])\s+(.*)$", line)
            text = re.sub(r"^\[[ xX]\]", "", item.group(1)).strip() if item else ""
            if text and not re.fullmatch(r"[-*_ ]+", text):
                count += 1
    return count


def backlog_rows(root: pathlib.Path, cfg: dict) -> dict[str, str]:
    t = tickets_cfg(cfg)
    backlog = root / t["backlog"]
    if not backlog.exists():
        return {}
    return {tid: status for tid, _, status in parse_backlog(backlog, t["id_pattern"])}


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
            done = status_of(status, t["statuses"]) == t["statuses"]["done"]
            print(f"  {dep}: {status}" + ("" if done else "   <-- NOT DONE"))
    else:
        print("depends on: none")
    print("rules to read: " + (", ".join(cfg.get("project", {}).get("rules", [])) or "none"))
    for heading in ("Description", "Technical Scope", "Acceptance Criteria"):
        text = section_of(body, heading)
        print(f"\n## {heading}\n{text or '(missing)'}")
    return 0
