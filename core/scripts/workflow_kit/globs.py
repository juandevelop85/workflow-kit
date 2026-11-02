"""Glob matching (`**` crosses directories) and the file walk used by the size check."""
from __future__ import annotations

import os
import pathlib
import re


ALWAYS_SKIPPED_DIRS = {".git"}


def glob_to_regex(pattern: str) -> re.Pattern:
    """`**` crosses directories, `*` and `?` do not. Anchored at the root."""
    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def iter_files(root: pathlib.Path, include: list[str], exclude: list[str]):
    inc = [glob_to_regex(p) for p in include]
    exc = [glob_to_regex(p) for p in exclude]
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = pathlib.PurePath(dirpath).relative_to(root).as_posix()
        def pruned(d: str) -> bool:
            rel_d = d if rel_dir == "." else f"{rel_dir}/{d}"
            return d in ALWAYS_SKIPPED_DIRS or any(e.match(f"{rel_d}/x") for e in exc)

        dirnames[:] = [d for d in dirnames if not pruned(d)]
        for name in filenames:
            rel = f"{rel_dir}/{name}" if rel_dir != "." else name
            if any(i.match(rel) for i in inc) and not any(e.match(rel) for e in exc):
                yield pathlib.Path(dirpath) / name, rel
