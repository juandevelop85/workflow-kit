"""`sensitive` and `review-plan`: which changes need which reviewers."""
from __future__ import annotations

import json
import pathlib
import sys

from .config import ConfigError, efficiency, load_config, tickets_cfg
from .gitutil import changed_files, diff_size
from .globs import glob_to_regex
from .tickets import count_criteria, ticket_file


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


def plan_review(root: pathlib.Path, cfg: dict, base: str | None, tid: str | None, files: dict[str, int]) -> dict:
    eff = efficiency(cfg)
    total = sum(max(n, 0) for n in files.values())
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
