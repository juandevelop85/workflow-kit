"""Shared helpers: build throwaway repositories from the fixtures."""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

KIT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = KIT / "tests" / "fixtures"
STACKS = ("rust", "node", "python")


def run(cmd, cwd=None, check=False):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)


def install(kit: pathlib.Path, target: pathlib.Path, stack: str = "none", *extra: str):
    return run([sys.executable, str(kit / "install.py"), "install", "--target", str(target),
                "--stack", stack, *extra])


def update(kit: pathlib.Path, target: pathlib.Path, *extra: str):
    return run([sys.executable, str(kit / "install.py"), "update", "--target", str(target), *extra])


def checker(repo: pathlib.Path, *args: str):
    script = repo / ".agents" / "scripts" / "workflow_check.py"
    return run([sys.executable, str(script), *args, "--root", str(repo)]) if args[:1] and not args[0].startswith("-") \
        else run([sys.executable, str(script), "check", *args, "--root", str(repo)])


def init_git(repo: pathlib.Path):
    run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    run(["git", "config", "user.name", "Test"], cwd=repo, check=True)


def commit(repo: pathlib.Path, message: str):
    run(["git", "add", "-A"], cwd=repo, check=True)
    run(["git", "commit", "-q", "--allow-empty", "-m", message], cwd=repo, check=True)


def fixture_repo(stack: str, tmp: pathlib.Path) -> pathlib.Path:
    """A copy of the good fixture with the kit core installed on top."""
    repo = tmp / f"{stack}-repo"
    shutil.copytree(FIXTURES / stack / "good", repo)
    result = install(KIT, repo, stack)
    assert result.returncode == 0, result.stdout + result.stderr
    return repo


class TempDirMixin:
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()
