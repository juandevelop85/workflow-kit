"""Regression tests for the attacks found while reviewing the installer.

The target repository of `install` / `update` may be untrusted: it can carry symlinks, a doctored
manifest, a hostile script where the kit would put its own, or arguments that try to smuggle
configuration. Each test is an attack that worked before it was fixed.
"""
import hashlib
import json
import pathlib
import sys
import tomllib
import unittest

from helpers import KIT, TempDirMixin, checker, fixture_repo, init_git, install, run, update


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def init_script(repo: pathlib.Path) -> str:
    return str(repo / ".agents/scripts/workflow_init.py")


class InstallerOnAnUntrustedRepository(TempDirMixin, unittest.TestCase):
    def test_a_doctored_manifest_cannot_delete_files_outside_the_repository(self):
        repo = self.tmp / "repo"
        repo.mkdir()
        install(KIT, repo)
        victim = self.tmp / "victim.txt"
        victim.write_text("important\n")
        manifest = repo / ".agents/.kit-manifest.json"
        data = json.loads(manifest.read_text())
        data["files"]["../victim.txt"] = sha(victim)       # attacker knows the hash of the file
        data["files"]["/etc/hosts"] = sha(pathlib.Path("/etc/hosts"))
        manifest.write_text(json.dumps(data))
        result = update(KIT, repo)
        self.assertTrue(victim.exists())
        self.assertIn("ignored unsafe manifest entry: ../victim.txt", result.stdout)
        self.assertIn("ignored unsafe manifest entry: /etc/hosts", result.stdout)

    def test_a_manifest_entry_outside_the_agents_directory_is_ignored(self):
        repo = self.tmp / "repo"
        repo.mkdir()
        install(KIT, repo)
        (repo / "README.md").write_text("mine\n")
        manifest = repo / ".agents/.kit-manifest.json"
        data = json.loads(manifest.read_text())
        data["files"]["README.md"] = sha(repo / "README.md")
        manifest.write_text(json.dumps(data))
        update(KIT, repo)
        self.assertTrue((repo / "README.md").exists(), "only files under .agents/ may ever be removed")

    def test_a_symlinked_agents_directory_is_refused_so_nothing_is_written_elsewhere(self):
        repo = self.tmp / "repo"
        outside = self.tmp / "outside"
        repo.mkdir()
        outside.mkdir()
        (repo / ".agents").symlink_to(outside)
        result = install(KIT, repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn(".agents is a symlink", result.stderr)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(update(KIT, repo).returncode, 1)

    def test_a_symlinked_subdirectory_of_agents_does_not_redirect_writes(self):
        repo = self.tmp / "repo"
        outside = self.tmp / "outside"
        (repo / ".agents").mkdir(parents=True)
        outside.mkdir()
        (repo / ".agents/skills").symlink_to(outside)
        result = install(KIT, repo)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(list(outside.iterdir()), [], "nothing was written through the link")

    def test_a_hostile_script_already_in_the_target_is_never_executed_by_install(self):
        repo = self.tmp / "repo"
        marker = self.tmp / "PWNED"
        (repo / ".agents/scripts").mkdir(parents=True)
        (repo / ".agents/scripts/workflow_init.py").write_text(
            f"import pathlib; pathlib.Path({str(marker)!r}).write_text('x')\n")
        result = install(KIT, repo)
        self.assertFalse(marker.exists(), "install ran code that came from the target repository")
        self.assertIn("conflict (kept yours): .agents/scripts/workflow_init.py", result.stdout)
        self.assertTrue((repo / ".agents/workflow.toml").exists(), "the kit's own init still ran")

    def test_a_dangling_symlink_in_the_project_layer_is_not_written_through(self):
        repo = self.tmp / "repo"
        repo.mkdir()
        elsewhere = self.tmp / "elsewhere.txt"
        (repo / "CLAUDE.md").symlink_to(elsewhere)
        install(KIT, repo)
        self.assertFalse(elsewhere.exists())


class InitWithHostileArguments(TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        install(KIT, self.repo)
        (self.repo / ".agents/workflow.toml").unlink()

    def init(self, *args: str):
        return run([sys.executable, init_script(self.repo), "--root", str(self.repo), *args])

    def test_a_project_name_cannot_inject_configuration(self):
        hostile = 'x"\n[gates.extra]\nname = "pwn"\ncommand = "touch /tmp/injected"\n#'
        result = self.init("--name", hostile)
        self.assertEqual(result.returncode, 1)
        self.assertIn("control characters", result.stderr)
        self.assertFalse((self.repo / ".agents/workflow.toml").exists())

    def test_a_language_policy_cannot_inject_configuration(self):
        result = self.init("--language-policy", 'ok"\n[checks]\nbacklog = false\n#')
        self.assertEqual(result.returncode, 1)
        self.assertFalse((self.repo / ".agents/workflow.toml").exists())

    def test_quotes_backslashes_and_unicode_in_a_name_are_escaped_not_rejected(self):
        name = 'My "quoted" project \\ ñ 日本'
        self.assertEqual(self.init("--name", name).returncode, 0)
        config = tomllib.loads((self.repo / ".agents/workflow.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["project"]["name"], name)
        self.assertNotIn("extra", config.get("gates", {}))

    def test_the_tickets_directory_cannot_leave_the_repository(self):
        for bad in ("../../escaped", "/tmp/abs", "a/../../b", "has space", "x;rm -rf"):
            result = self.init("--tickets-dir", bad)
            self.assertEqual(result.returncode, 1, bad)
            self.assertIn("--tickets-dir", result.stderr)
        self.assertFalse((self.tmp / "escaped").exists())

    def test_the_id_prefix_is_restricted_so_it_cannot_break_the_regexes(self):
        for bad in ("T'", "1T", "", "A B", "T" * 40, "T\n"):
            self.assertEqual(self.init("--id-prefix", bad).returncode, 1, repr(bad))
        self.assertEqual(self.init("--id-prefix", "TKT-2").returncode, 0)
        self.assertEqual(checker(self.repo).returncode, 0)


class CheckerOnAnUntrustedRepository(TempDirMixin, unittest.TestCase):
    def test_symlinked_source_files_are_not_followed(self):
        repo = fixture_repo("python", self.tmp)
        big = self.tmp / "huge_elsewhere.py"
        big.write_text("x\n" * 5000)
        (repo / "app/link.py").symlink_to(big)
        result = checker(repo)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("link.py", result.stdout)

    def test_a_repository_cannot_run_a_command_through_git_config(self):
        repo = fixture_repo("python", self.tmp)
        init_git(repo)
        marker = self.tmp / "fsmonitor-ran"
        hook = self.tmp / "hook.sh"
        hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
        hook.chmod(0o755)
        run(["git", "config", "core.fsmonitor", str(hook)], cwd=repo, check=True)
        # control: plain git does run the configured command
        run(["git", "diff", "--name-only"], cwd=repo)
        if not marker.exists():
            self.skipTest("this git version does not run core.fsmonitor for `git diff`")
        marker.unlink()
        checker(repo, "sensitive")
        checker(repo, "--commits", "2")
        self.assertFalse(marker.exists(), "the checker let the repository run a command via git")


if __name__ == "__main__":
    unittest.main()
