"""Writes under `.agents/.cache/`, refusing symlinks: a hostile repository could point them anywhere."""
from __future__ import annotations

import os
import pathlib

CACHE_ROOT = ".agents/.cache"


class UnsafeCache(Exception):
    """A path of the cache is a symlink or not a directory."""


def _real_dirs(root: pathlib.Path, rel_dir: pathlib.PurePosixPath) -> pathlib.Path:
    """Walk `rel_dir` from `root`, creating missing directories, refusing any symlink on the way."""
    current = root
    for part in rel_dir.parts:
        current = current / part
        if current.is_symlink():
            raise UnsafeCache(f"refusing to write through a symlink: {current.relative_to(root).as_posix()}")
        if not current.exists():
            current.mkdir()
        elif not current.is_dir():
            raise UnsafeCache(f"not a directory: {current.relative_to(root).as_posix()}")
    return current


def cache_write(root: pathlib.Path, rel: str, text: str) -> None:
    """Write `text` to `rel` (under `.agents/.cache/`), which ignores itself in git."""
    pure = pathlib.PurePosixPath(rel)
    if pure.parts[:2] != (".agents", ".cache") or ".." in pure.parts:
        raise UnsafeCache(f"not a cache path: {rel}")
    _write(_real_dirs(root, pathlib.PurePosixPath(CACHE_ROOT)), ".gitignore", "*\n", root)
    _write(_real_dirs(root, pure.parent), pure.name, text, root)


def _write(directory: pathlib.Path, name: str, text: str, root: pathlib.Path) -> None:
    path = directory / name
    try:
        # O_NOFOLLOW: a symlink planted at the file itself is refused by the kernel, not followed.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    except OSError as exc:
        raise UnsafeCache(f"refusing to write {path.relative_to(root).as_posix()}: {exc.strerror}") from exc
    with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as fh:
        fh.write(text)
