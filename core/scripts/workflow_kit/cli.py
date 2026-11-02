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
classify   the minimum lane of the current change (quick, standard, deep), why, and the
           questions that may raise it: how much process this change needs.
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
import pathlib
import sys

from .checks import run_check
from .gates import run_gates, run_gates_report
from .lanes import run_classify
from .review import run_review_plan, run_sensitive
from .tickets import run_context

SUBCOMMANDS = ("check", "gates", "sensitive", "context", "classify", "review-plan")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-") or argv[0] not in SUBCOMMANDS:
        argv.insert(0, "check")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    default_root = str(pathlib.Path(__file__).resolve().parents[3])
    for name in SUBCOMMANDS:
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
        if name == "classify":
            p.add_argument("--base", default=None, help="also count changes since this ref")
            p.add_argument("--json", action="store_true")
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
    if args.cmd == "classify":
        return run_classify(root, args.base, args.json)
    if args.cmd == "review-plan":
        return run_review_plan(root, args.base, args.ticket, args.json)
    if args.cmd == "gates":
        if args.run:
            return run_gates_report(root, args.tail)
        return run_gates(root, args.json)
    if args.cmd == "sensitive":
        return run_sensitive(root, args.base, args.files)
    return run_check(root, args.commits)
