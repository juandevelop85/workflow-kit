#!/usr/bin/env python3
"""Install, update or inspect the workflow kit core in a repository.

    python3 install.py install --target DIR [--stack rust|node|python|none] [--name NAME]
    python3 install.py update  --target DIR [--force]
    python3 install.py status  --target DIR

The kit has two layers:

* the CORE (`core/`): skills, agents, commands, scripts, stack presets and
  templates. It is installed under `.agents/` and linked from `.claude/`. It
  is versioned (`VERSION`) and recorded in `.agents/.kit-manifest.json` with
  the hash of every file as installed.
* the PROJECT layer: `.agents/workflow.toml`, `.agents/rules/`,
  `.agents/security-model.md`, `.agents/baseline.txt`, the tickets, `CLAUDE.md`
  and `AGENTS.md`. Only `install` creates it (through `workflow_init.py`, and
  never over an existing file). **`update` never touches it.**

`update` replaces a core file only if the project has not modified it since
the last install; a locally modified core file is reported as a conflict and
kept (use `--force` to overwrite it). Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys

KIT_ROOT = pathlib.Path(__file__).resolve().parent
MANIFEST = ".agents/.kit-manifest.json"
SKIPPED_NAMES = {"__pycache__", ".DS_Store"}


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_version(kit: pathlib.Path) -> str:
    return (kit / "VERSION").read_text(encoding="utf-8").strip()


def core_files(kit: pathlib.Path) -> dict[str, pathlib.Path]:
    """Target path (relative to the repository) -> source file in the kit."""
    core = kit / "core"
    out: dict[str, pathlib.Path] = {}
    for path in sorted(core.rglob("*")):
        if path.is_file() and not (set(path.parts) & SKIPPED_NAMES) and path.suffix != ".pyc":
            out[".agents/" + path.relative_to(core).as_posix()] = path
    return out


def read_manifest(target: pathlib.Path) -> dict | None:
    path = target / MANIFEST
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_manifest(target: pathlib.Path, version: str, files: dict[str, str]) -> None:
    path = target / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": version, "files": files}, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


class UnsafePath(Exception):
    """A path would leave the target repository."""


def safe_dest(target: pathlib.Path, rel: str) -> pathlib.Path:
    """The destination of a core file, guaranteed to stay inside `target/.agents/`.

    The target may be an untrusted repository: it may contain symlinks, and its manifest may name
    anything. Refuse absolute paths, `..`, anything outside `.agents/`, and any path whose real
    location (following symlinks in its parents) is not under the real `target/.agents/`.
    """
    pure = pathlib.PurePosixPath(rel)
    if pure.is_absolute() or ".." in pure.parts or pure.parts[:1] != (".agents",):
        raise UnsafePath(f"refusing path outside .agents/: {rel}")
    base = (target / ".agents").resolve()
    dest = target / rel
    if not (dest.parent.resolve() / dest.name).is_relative_to(base) or dest.is_symlink():
        raise UnsafePath(f"refusing path that resolves outside {base} (symlink?): {rel}")
    return dest


def is_safe(target: pathlib.Path, rel: str) -> bool:
    try:
        safe_dest(target, rel)
        return True
    except UnsafePath:
        return False


def link(target: pathlib.Path, rel_link: str, points_to: str, notes: list[str]) -> None:
    """Create a symlink, never replacing something that is already there."""
    path = target / rel_link
    if not (path.parent.resolve()).is_relative_to(target.resolve()):
        notes.append(f"kept {rel_link} (its parent resolves outside the repository)")
        return
    if path.is_symlink() or path.exists():
        if path.is_symlink() and os.readlink(path) == points_to:
            return
        notes.append(f"kept {rel_link} (already exists and is not the kit link)")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(points_to)


def make_links(target: pathlib.Path, notes: list[str]) -> None:
    link(target, ".claude/agents", "../.agents/agents", notes)
    link(target, ".claude/commands", "../.agents/commands", notes)
    skills = target / ".agents" / "skills"
    if skills.is_dir():
        for skill in sorted(p.name for p in skills.iterdir() if p.is_dir()):
            link(target, f".claude/skills/{skill}", f"../../.agents/skills/{skill}", notes)


def install(kit: pathlib.Path, target: pathlib.Path, force: bool) -> tuple[list[str], list[str], dict[str, str]]:
    installed, conflicts = [], []
    recorded: dict[str, str] = {}
    for rel, src in core_files(kit).items():
        dst = safe_dest(target, rel)
        digest = sha(src)
        if dst.exists() and sha(dst) != digest and not force:
            conflicts.append(rel)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        dst.chmod(src.stat().st_mode & 0o777)
        recorded[rel] = digest
        installed.append(rel)
    return installed, conflicts, recorded


def cmd_install(args: argparse.Namespace) -> int:
    kit = pathlib.Path(args.kit).resolve()
    target = pathlib.Path(args.target).resolve()
    target.mkdir(parents=True, exist_ok=True)
    if (target / ".agents").is_symlink():
        print("Refusing to install: .agents is a symlink.", file=sys.stderr)
        return 1
    if read_manifest(target):
        print("The kit is already installed here: use `update`.", file=sys.stderr)
        return 1
    try:
        installed, conflicts, recorded = install(kit, target, args.force)
    except UnsafePath as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    write_manifest(target, read_version(kit), recorded)
    notes: list[str] = []
    make_links(target, notes)
    # Run the kit's own script, never the copy in the target: if that file already existed and
    # differed it was kept (a conflict), and the target may be an untrusted repository.
    init = kit / "core" / "scripts" / "workflow_init.py"
    cmd = [sys.executable, str(init), "--root", str(target), "--stack", args.stack]
    if args.name:
        cmd += ["--name", args.name]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(f"installed {len(installed)} core files (version {read_version(kit)})")
    for rel in conflicts:
        print(f"conflict (kept yours): {rel}")
    for note in notes:
        print(note)
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode
    return 2 if conflicts else 0


def cmd_update(args: argparse.Namespace) -> int:
    kit = pathlib.Path(args.kit).resolve()
    target = pathlib.Path(args.target).resolve()
    manifest = read_manifest(target)
    if manifest is None:
        print("No kit manifest found: run `install` first.", file=sys.stderr)
        return 1
    old: dict[str, str] = manifest.get("files", {})
    new_core = core_files(kit)
    recorded: dict[str, str] = {}
    updated, added, removed, conflicts, unchanged = [], [], [], [], 0
    if (target / ".agents").is_symlink():
        print("Refusing to update: .agents is a symlink.", file=sys.stderr)
        return 1
    skipped_unsafe: list[str] = []
    for rel, src in new_core.items():
        try:
            dst = safe_dest(target, rel)
        except UnsafePath as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        digest = sha(src)
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            dst.chmod(src.stat().st_mode & 0o777)
            added.append(rel)
            recorded[rel] = digest
            continue
        current = sha(dst)
        if current == digest:
            unchanged += 1
            recorded[rel] = digest
        elif current == old.get(rel) or args.force:
            dst.write_bytes(src.read_bytes())
            dst.chmod(src.stat().st_mode & 0o777)
            updated.append(rel)
            recorded[rel] = digest
        else:
            conflicts.append(rel)
            recorded[rel] = old.get(rel, digest)
    for rel, digest in old.items():
        if rel in new_core:
            continue
        try:
            dst = safe_dest(target, rel)
        except UnsafePath:
            skipped_unsafe.append(rel)  # a manipulated manifest: never act on it
            continue
        if dst.exists() and sha(dst) == digest:
            dst.unlink()
            removed.append(rel)
        elif dst.exists():
            conflicts.append(rel)
            recorded[rel] = digest
    write_manifest(target, read_version(kit), recorded)
    make_links(target, [])
    print(f"kit {manifest.get('version', '?')} -> {read_version(kit)}: "
          f"{len(updated)} updated, {len(added)} added, {len(removed)} removed, {unchanged} unchanged")
    for rel in conflicts:
        print(f"conflict (modified locally, kept yours): {rel}")
    for rel in skipped_unsafe:
        print(f"ignored unsafe manifest entry: {rel}")
    return 2 if conflicts else 0


def cmd_status(args: argparse.Namespace) -> int:
    kit = pathlib.Path(args.kit).resolve()
    target = pathlib.Path(args.target).resolve()
    manifest = read_manifest(target)
    if manifest is None:
        print("The kit is not installed here.")
        return 1
    print(f"installed: {manifest.get('version', '?')}   available: {read_version(kit)}")
    entries = {rel: d for rel, d in manifest.get("files", {}).items() if is_safe(target, rel)}
    modified = [rel for rel, digest in entries.items()
                if (target / rel).exists() and sha(target / rel) != digest]
    missing = [rel for rel in entries if not (target / rel).exists()]
    for rel in modified:
        print(f"modified locally: {rel}")
    for rel in missing:
        print(f"missing: {rel}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("install", "update", "status"):
        p = sub.add_parser(name)
        p.add_argument("--target", required=True, help="repository to install into")
        p.add_argument("--kit", default=str(KIT_ROOT), help=argparse.SUPPRESS)
        if name != "status":
            p.add_argument("--force", action="store_true", help="overwrite locally modified core files")
        if name == "install":
            p.add_argument("--stack", choices=("rust", "node", "python", "none"), default="none")
            p.add_argument("--name", default=None)
    args = ap.parse_args(argv)
    return {"install": cmd_install, "update": cmd_update, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
