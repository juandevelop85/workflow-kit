"""The git calls of the checker: changed files and diff sizes."""
from __future__ import annotations

import os
import pathlib
import subprocess


# A repository can carry a configuration that makes git run a command (`core.fsmonitor`): switch
# that off. Run this checker only on repositories you would run `git` on.
GIT = ["git", "-c", "core.fsmonitor=false", "-c", "core.quotepath=off"]


def changed_files(root: pathlib.Path, base: str | None) -> list[str]:
    def git(*args):
        res = subprocess.run([*GIT, *args], cwd=root, capture_output=True, text=True)
        return res.stdout.splitlines() if res.returncode == 0 else []
    files = set(git("diff", "--name-only")) | set(git("diff", "--name-only", "--cached"))
    files |= set(untracked(root))
    if base:
        files |= set(git("diff", "--name-only", f"{base}...HEAD"))
    return sorted(files)


# A binary file has no line count; it is recorded with this value so that callers can tell.
BINARY = -1


def numstat(root: pathlib.Path, *args: str) -> dict[str, int]:
    # `--no-renames`: a move is its old path removed and its new path added, so a path glob (a
    # sensitive surface) matches both ends instead of a folded `{old => new}` name.
    res = subprocess.run([*GIT, "diff", "--no-ext-diff", "--no-textconv", "--numstat", "--no-renames", *args], cwd=root, capture_output=True, text=True)
    return parse_numstat(res)


def commit_size(root: pathlib.Path, sha: str) -> dict[str, int] | None:
    """{path: changed lines} of one commit (the root commit included); None if git fails."""
    res = subprocess.run([*GIT, "show", "--no-ext-diff", "--no-textconv", "--numstat", "--no-renames", "--format=", sha],
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


# The tree of a repository with no commits: diffing against it works before the first commit.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
# A repository can configure an external diff or a textconv driver (`diff.external`,
# `.gitattributes`): patch-mode diffs never run them.
SAFE_DIFF = ["diff", "--no-ext-diff", "--no-textconv", "--binary"]
UNTRACKED_MAX_BYTES = 1_000_000


def head_or_empty(root: pathlib.Path) -> str:
    res = subprocess.run([*GIT, "rev-parse", "--verify", "--quiet", "HEAD"], cwd=root, capture_output=True, text=True)
    return "HEAD" if res.returncode == 0 else EMPTY_TREE


def untracked(root: pathlib.Path) -> list[str]:
    """Untracked, not ignored paths, exactly as on disk (`-z`: no quoting of unusual names)."""
    res = subprocess.run([*GIT, "ls-files", "-z", "--others", "--exclude-standard"], cwd=root, capture_output=True)
    return [n.decode("utf-8", "surrogateescape") for n in res.stdout.split(b"\0") if n] if res.returncode == 0 else []


def check_base(base: str | None) -> None:
    if base is not None and (not base or base.startswith("-")):
        raise ValueError(f"--base must be a git ref, not an option: {base!r}")


def full_diff(root: pathlib.Path, base: str | None) -> tuple[str, str]:
    """(everything to review, the part that applies on HEAD): `base...HEAD`, then the working tree
    against HEAD, then the untracked files. Binary-safe; never runs an external diff driver."""
    check_base(base)

    def git(*args: str) -> str:
        return subprocess.run([*GIT, *args], cwd=root, capture_output=True, text=True, errors="replace").stdout
    working = [git(*SAFE_DIFF, head_or_empty(root))]
    for name in untracked(root):
        path = root / name
        if path.is_symlink() and path.is_dir():
            working.append(f"# untracked symlink {name} -> {os.readlink(path)} (to a directory, not diffed)\n")
        elif path.is_symlink() or (path.is_file() and path.stat().st_size <= UNTRACKED_MAX_BYTES):
            working.append(git(*SAFE_DIFF, "--no-index", "--", "/dev/null", name))
        elif path.is_file():
            working.append(f"# skipped untracked {name}: over {UNTRACKED_MAX_BYTES} bytes\n")
    committed = git(*SAFE_DIFF, f"{base}...HEAD") if base else ""
    return committed + "".join(working), "".join(working)


def diff_size(root: pathlib.Path, base: str | None) -> dict[str, int]:
    check_base(base)
    sizes = numstat(root, head_or_empty(root))
    if base:
        for name, n in numstat(root, f"{base}...HEAD").items():
            sizes[name] = max(sizes.get(name, 0), n)
    for name in untracked(root):
        path = root / name
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as fh:
                binary = b"\0" in fh.read(8192)
            sizes[name] = BINARY if binary else sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
    return sizes
