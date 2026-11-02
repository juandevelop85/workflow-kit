"""The git calls of the checker: changed files and diff sizes."""
from __future__ import annotations

import pathlib
import subprocess


# A repository can carry a configuration that makes git run a command (`core.fsmonitor`): switch
# that off. Run this checker only on repositories you would run `git` on.
GIT = ["git", "-c", "core.fsmonitor=false"]


def changed_files(root: pathlib.Path, base: str | None) -> list[str]:
    def git(*args):
        res = subprocess.run([*GIT, *args], cwd=root, capture_output=True, text=True)
        return res.stdout.splitlines() if res.returncode == 0 else []
    files = set(git("diff", "--name-only")) | set(git("diff", "--name-only", "--cached"))
    files |= set(git("ls-files", "--others", "--exclude-standard"))
    if base:
        files |= set(git("diff", "--name-only", f"{base}...HEAD"))
    return sorted(files)


# A binary file has no line count; it is recorded with this value so that callers can tell.
BINARY = -1


def numstat(root: pathlib.Path, *args: str) -> dict[str, int]:
    # `--no-renames`: a move is its old path removed and its new path added, so a path glob (a
    # sensitive surface) matches both ends instead of a folded `{old => new}` name.
    res = subprocess.run([*GIT, "diff", "--numstat", "--no-renames", *args], cwd=root, capture_output=True, text=True)
    return parse_numstat(res)


def commit_size(root: pathlib.Path, sha: str) -> dict[str, int] | None:
    """{path: changed lines} of one commit (the root commit included); None if git fails."""
    res = subprocess.run([*GIT, "show", "--numstat", "--no-renames", "--format=", sha],
                         cwd=root, capture_output=True, text=True)
    return parse_numstat(res) if res.returncode == 0 else None


def parse_numstat(res: subprocess.CompletedProcess) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in res.stdout.splitlines() if res.returncode == 0 else []:
        added, removed, name = (line.split("\t", 2) + ["", ""])[:3]
        if added == removed == "-":
            out[name] = BINARY
            continue
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
            with path.open("rb") as fh:
                binary = b"\0" in fh.read(8192)
            sizes[name] = BINARY if binary else sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
    return sizes
