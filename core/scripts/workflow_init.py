#!/usr/bin/env python3
"""Generate the PROJECT layer of the workflow in a repository.

Creates (and never overwrites) the files that belong to the project:

    .agents/workflow.toml        configuration
    .agents/rules/project.md     project rules skeleton
    .agents/security-model.md    threat model skeleton
    .agents/baseline.txt         acknowledged size debt (empty)
    <tickets dir>/README.md      backlog
    CLAUDE.md, AGENTS.md         agent memory and guide

A file that already exists is kept and reported. The core (skills, agents,
commands, scripts) is installed by the kit's `install.py`, not by this script.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys

STACKS = ("rust", "node", "python", "none")
DEFAULT_LANGUAGE_POLICY = (
    "Identifiers, comments and documentation are written in English. "
    "Change this line if the project follows another policy."
)


ID_PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,15}$")
SAFE_DIR_RE = re.compile(r"^[A-Za-z0-9_./-]+$")


def toml_string(value: str) -> str:
    """A TOML basic string for any text; control characters are rejected, never smuggled in."""
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise ValueError("control characters (including newlines) are not allowed in this value")
    return json.dumps(value, ensure_ascii=False)


def safe_relative_dir(value: str) -> str:
    cleaned = value.strip().rstrip("/")
    pure = pathlib.PurePosixPath(cleaned)
    # `fullmatch`, not `match` with `$`: `$` also matches before a trailing newline.
    if not cleaned or pure.is_absolute() or ".." in pure.parts or not SAFE_DIR_RE.fullmatch(cleaned):
        raise ValueError(f"--tickets-dir must be a plain relative directory inside the repository: {value!r}")
    return cleaned


def inside(root: pathlib.Path, path: pathlib.Path) -> bool:
    """True if writing `path` stays inside `root` (no symlink, real parent under root)."""
    return not path.is_symlink() and (path.parent.resolve() / path.name).is_relative_to(root.resolve())


def render(template: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    leftover = re.findall(r"\{\{(\w+)\}\}", template)
    if leftover:
        raise ValueError(f"unfilled placeholders: {sorted(set(leftover))}")
    return template


def build_plan(root: pathlib.Path, args: argparse.Namespace, templates: pathlib.Path):
    prefix = args.id_prefix
    values = {
        "name": args.name,
        "name_toml": toml_string(args.name),
        "stack": args.stack,
        "tickets_dir": safe_relative_dir(args.tickets_dir),
        "id_prefix": prefix,
        "id_pattern": re.escape(prefix) + r"\d+\.\d+",
        "commit_pattern": r"^[a-z]+\([a-z0-9_-]+\): " + re.escape(prefix) + r"\d+\.\d+ - .+",
        "language_policy": args.language_policy,
        "language_policy_toml": toml_string(args.language_policy),
    }
    tickets_dir = values["tickets_dir"]
    # (target path, template, content override)
    return values, [
        (root / ".agents" / "workflow.toml", "workflow.toml.tmpl"),
        (root / ".agents" / "rules" / "project.md", "rules.md.tmpl"),
        (root / ".agents" / "security-model.md", "security-model.md.tmpl"),
        (root / tickets_dir / "README.md", "backlog.md.tmpl"),
        (root / "AGENTS.md", "AGENTS.md.tmpl"),
        (root / "CLAUDE.md", "CLAUDE.md.tmpl"),
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--root", default=".", help="repository root (default: current directory)")
    ap.add_argument("--stack", choices=STACKS, default="none")
    ap.add_argument("--name", default=None, help="project name (default: directory name)")
    ap.add_argument("--tickets-dir", default="docs/tickets")
    ap.add_argument("--id-prefix", default="T", help="ticket id prefix, e.g. T gives T1.1")
    ap.add_argument("--language-policy", default=DEFAULT_LANGUAGE_POLICY)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    args.name = args.name or root.name
    if not ID_PREFIX_RE.fullmatch(args.id_prefix):
        print(f"ERROR: --id-prefix must be letters, digits, '_' or '-' (starting with a letter): {args.id_prefix!r}",
              file=sys.stderr)
        return 1
    templates = pathlib.Path(__file__).resolve().parents[1] / "templates"
    if not templates.is_dir():
        print(f"ERROR: templates not found at {templates}", file=sys.stderr)
        return 1
    try:
        values, plan = build_plan(root, args, templates)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    created, kept = [], []
    for target, template_name in plan:
        rel = target.relative_to(root).as_posix()
        if os.path.lexists(target) or not inside(root, target):
            kept.append(rel)  # exists (even as a dangling symlink) or would leave the repository
            continue
        text = render((templates / template_name).read_text(encoding="utf-8"), values)
        if not args.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        created.append(rel)
    baseline = root / ".agents" / "baseline.txt"
    if os.path.lexists(baseline) or not inside(root, baseline):
        kept.append(".agents/baseline.txt")
    else:
        if not args.dry_run:
            baseline.parent.mkdir(parents=True, exist_ok=True)
            baseline.write_text(
                "# Files that already exceeded the size limit when the project adopted the kit.\n"
                "# Format: <path> <maximum lines>. They may only shrink: delete the line when you split the file.\n",
                encoding="utf-8",
            )
        created.append(".agents/baseline.txt")

    verb = "would create" if args.dry_run else "created"
    for rel in created:
        print(f"{verb}: {rel}")
    for rel in kept:
        print(f"kept (already exists): {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
