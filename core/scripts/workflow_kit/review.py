"""`sensitive` and `review-plan`: which changes need which reviewers."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

from .config import ConfigError, efficiency, load_config, tickets_cfg
from .cache import UnsafeCache, cache_write
from .gitutil import GIT, SAFE_DIFF, changed_files, diff_size, full_diff, head_or_empty, untracked
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


REVIEW_DIFF = ".agents/.cache/review/diff.patch"        # what to review
WORKING_DIFF = ".agents/.cache/review/working.patch"    # the part that applies on HEAD


def write_review_diff(root: pathlib.Path, base: str | None) -> str:
    """Write the diff for the review agents, which have no shell to run `git diff` themselves."""
    everything, working = full_diff(root, base)
    head = subprocess.run([*GIT, "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True)
    header = (f"# review diff of {head.stdout.strip() or '(no commits)'} plus the working tree"
              f"{f', since {base}' if base else ''}; written {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    # The patch that can be applied first: if it is refused, no new diff.patch sits next to an old one.
    cache_write(root, WORKING_DIFF, working)
    cache_write(root, REVIEW_DIFF, header + everything)
    return REVIEW_DIFF


def fingerprint(root: pathlib.Path) -> str:
    """A hash of HEAD, the index, the working tree and the untracked files: it changes if any of their
    content changes. (Ignored files and the inside of `.git`, its config included, are not covered.)"""
    h = hashlib.sha256()
    def run(*args: str) -> bytes:
        return subprocess.run([*GIT, *args], cwd=root, capture_output=True).stdout
    h.update(run("rev-parse", "--verify", "--quiet", "HEAD"))
    h.update(run(*SAFE_DIFF, head_or_empty(root)))
    h.update(run(*SAFE_DIFF, "--cached", head_or_empty(root)))  # staging alone is a change too
    for name in sorted(untracked(root)):
        path = root / name
        h.update(b"\0" + name.encode("utf-8", "surrogateescape") + b"\0")
        if path.is_symlink():
            h.update(os.readlink(path).encode("utf-8", "surrogateescape"))
        elif path.is_file():
            with path.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
    return h.hexdigest()


def run_fingerprint(root: pathlib.Path) -> int:
    print(fingerprint(root))
    return 0


def run_review_plan(root: pathlib.Path, base: str | None, tid: str | None, as_json: bool,
                    write_diff: bool = False) -> int:
    try:
        cfg = load_config(root)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    try:
        sizes = diff_size(root, base)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    plan = plan_review(root, cfg, base, tid, sizes)
    if write_diff:
        try:
            plan["diff_file"] = write_review_diff(root, base)
        except UnsafeCache as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    if as_json:
        print(json.dumps(plan, indent=2))
    else:
        print(f"diff: {plan['files']} file(s), {plan['lines']} changed line(s)")
        print("launch: " + (" ".join(plan["launch"]) or "none"))
        print("why: " + "; ".join(plan["reasons"]))
        if write_diff:
            print(f"diff for the reviewers: {plan['diff_file']}")
    return 0
