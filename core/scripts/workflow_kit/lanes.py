"""`classify`: the minimum lane a change needs (quick, standard, deep) and why.

Organic Driven Development: the flow is the same for every change, how much of it runs depends on
the work. The checker measures what can be measured and sets a floor; the agent answers the
questions it cannot measure and may only raise the lane, never lower it.
"""
from __future__ import annotations

import json
import pathlib
import sys

from .config import ConfigError, lanes, load_config, validate_config
from .gitutil import BINARY, diff_size
from .globs import glob_to_regex

LANES = ("quick", "standard", "deep")
QUESTIONS = (
    "Is the change well understood (you can say what it does and why, from the code you read)?",
    "Is it free of behaviour, data or security risk beyond what the signals show?",
    "Can it be finished and reviewed on its own, in one place?",
    "Could someone resume it from the request and the diff alone, with no notes?",
)
WHAT_IT_TAKES = {
    "quick": "no ticket. Read the code, make the change, run the gates (`gates --run`) and the checker, "
             "self-review the diff, commit as `<type>(<area>): quick - <title>`.",
    "standard": "a ticket (`/ticket-new`), then the `ticket-runner` skill: tests first, gates, "
                "`review-plan`, one commit per ticket.",
    "deep": "a ticket split into steps (or several tickets) with an explicit Risks section, then "
            "`ticket-runner` with the full review; confirm the plan with the person before coding.",
}


def classify(cfg: dict, files: dict[str, int]) -> dict:
    """The minimum lane for a diff given as {path: changed lines} (`BINARY` for a binary file)."""
    lc = lanes(cfg)
    docs_re = [glob_to_regex(g) for g in lc["doc_globs"]]
    tests_re = [glob_to_regex(g) for g in lc["test_globs"]]
    process_re = [glob_to_regex(g) for g in lc["process_globs"]]
    sens_re = [glob_to_regex(g) for g in cfg.get("sensitive", {}).get("globs", [])]
    docs = [f for f in files if any(r.match(f) for r in docs_re)]
    tests = [f for f in files if f not in docs and any(r.match(f) for r in tests_re)]
    code = [f for f in files if f not in docs and f not in tests]
    process = sorted(f for f in files if any(r.match(f) for r in process_re))
    sensitive = sorted(f for f in files if any(r.match(f) for r in sens_re))
    binaries = sorted(f for f, n in files.items() if n == BINARY)
    total = sum(max(n, 0) for n in files.values())
    code_lines = sum(max(files[f], 0) for f in code)
    lane, reasons = "quick", []

    def at_least(level: str, why: str) -> None:
        nonlocal lane
        reasons.append(why)
        if LANES.index(level) > LANES.index(lane):
            lane = level

    if not files:
        reasons.append("no changes")
    if code or tests:
        if total >= lc["deep_min_lines"]:
            at_least("deep", f"{total} changed lines >= {lc['deep_min_lines']}")
        if len(files) >= lc["deep_min_files"]:
            at_least("deep", f"{len(files)} files >= {lc['deep_min_files']}")
    if sensitive:
        at_least("standard", "touches a sensitive surface: " + ", ".join(sensitive))
    if process:
        at_least("standard", "changes the workflow itself: " + ", ".join(process))
    if binaries:
        at_least("standard", "binary files (their size cannot be measured): " + ", ".join(binaries))
    if code and not tests and code_lines > lc["untested_code_max_lines"]:
        at_least("standard", f"{code_lines} lines of code changed without a test change "
                             f"(> {lc['untested_code_max_lines']})")
    limit = lc["quick_max_lines"] if code or tests else lc["quick_docs_max_lines"]
    if total > limit:
        at_least("standard", f"{total} changed lines > {limit}" + ("" if code or tests else " (docs-only)"))
    if len(files) > lc["quick_max_files"]:
        at_least("standard", f"{len(files)} files > {lc['quick_max_files']}")
    if lane == "quick" and not lc["quick_pattern"]:
        at_least("standard", "the quick lane is turned off ([lanes].quick_pattern is empty)")
    if files and lane == "quick":
        reasons.append(f"{total} changed lines in {len(files)} file(s), no sensitive surface")
    return {"lane": lane, "reasons": reasons, "files": len(files), "lines": total,
            "code_lines": code_lines, "tests_changed": bool(tests), "sensitive": sensitive}


def run_classify(root: pathlib.Path, base: str | None, as_json: bool) -> int:
    try:
        cfg = load_config(root)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    errors: list[str] = []
    validate_config(cfg, errors, [])
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    try:
        result = classify(cfg, diff_size(root, base))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps({**result, "questions": list(QUESTIONS)}, indent=2))
        return 0
    print(f"minimum lane: {result['lane']}")
    print("why: " + "; ".join(result["reasons"]))
    print("raise the lane if any answer is no:")
    for question in QUESTIONS:
        print(f"  - {question}")
    print(f"{result['lane']} takes: {WHAT_IT_TAKES[result['lane']]}")
    return 0
