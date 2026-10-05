"""Acceptance criteria 3 and 5, and the install / update plan of the ticket:

3. `workflow-init` in an empty repository yields a structure that passes the gates untouched.
5. Updating the core never modifies the project's rules, configuration or tickets.
"""
import hashlib
import pathlib
import shutil
import tomllib
import unittest

from helpers import KIT, STACKS, TempDirMixin, checker, commit, fixture_repo, init_git, install, run, update
import sys


def digest_tree(root: pathlib.Path, skip: tuple[str, ...]) -> dict[str, str]:
    out = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and not path.is_symlink() and not any(rel.startswith(s) for s in skip):
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


CORE_PREFIXES = (
    ".agents/agents/", ".agents/skills/", ".agents/commands/", ".agents/scripts/",
    ".agents/presets/", ".agents/templates/", ".agents/.kit-manifest.json",
)


def newer_kit(tmp: pathlib.Path, version: str = "0.2.0") -> pathlib.Path:
    """A copy of the kit that looks like a later release."""
    dst = tmp / "kit-next"
    shutil.copytree(KIT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", "tests"))
    (dst / "VERSION").write_text(version + "\n")
    return dst


class InstallInEmptyRepository(TempDirMixin, unittest.TestCase):
    def test_install_in_an_empty_repository_passes_the_gates_without_editing_anything(self):
        for stack in ("none", *STACKS):
            with self.subTest(stack=stack):
                repo = self.tmp / f"empty-{stack}"
                repo.mkdir()
                result = install(KIT, repo, stack)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                check = checker(repo)
                self.assertEqual(check.returncode, 0, check.stdout)
                gates = checker(repo, "gates")
                self.assertEqual(gates.returncode, 0, gates.stderr)
                self.assertEqual(bool(gates.stdout.strip()), stack != "none")

    def test_it_creates_core_project_layer_links_and_manifest(self):
        repo = self.tmp / "r"
        repo.mkdir()
        self.assertEqual(install(KIT, repo, "python", "--name", "demo").returncode, 0)
        for rel in (
            ".agents/workflow.toml", ".agents/rules/project.md", ".agents/security-model.md",
            ".agents/baseline.txt", "docs/tickets/README.md", "CLAUDE.md", "AGENTS.md",
            ".agents/skills/ticket-runner/SKILL.md", ".agents/agents/reviewer.md",
            ".agents/commands/workflow-init.md", ".agents/presets/python.toml",
            ".agents/templates/ticket.md.tmpl", ".agents/.kit-manifest.json",
        ):
            self.assertTrue((repo / rel).is_file(), rel)
        self.assertTrue((repo / ".claude/agents").is_symlink())
        self.assertTrue((repo / ".claude/commands").is_symlink())
        self.assertTrue((repo / ".claude/skills/ticket-runner").is_symlink())
        self.assertTrue((repo / ".claude/agents/reviewer.md").is_file(), "the link resolves")
        config = tomllib.loads((repo / ".agents/workflow.toml").read_text())
        self.assertEqual(config["project"]["name"], "demo")
        self.assertEqual(config["gates"]["preset"], "python")

    def test_the_project_layer_is_never_overwritten_by_install(self):
        repo = self.tmp / "r"
        (repo / ".agents").mkdir(parents=True)
        custom = {
            ".agents/workflow.toml": '[tickets]\ndir = "mine"\nbacklog = "mine/README.md"\n',
            "CLAUDE.md": "my own memory\n",
        }
        for rel, text in custom.items():
            (repo / rel).write_text(text)
        (repo / "mine").mkdir()
        (repo / "mine/README.md").write_text("# mine\n")
        result = install(KIT, repo, "rust")
        self.assertEqual(result.returncode, 0, result.stdout)
        for rel, text in custom.items():
            self.assertEqual((repo / rel).read_text(), text, rel)
        self.assertIn("kept (already exists): .agents/workflow.toml", result.stdout)

    def test_install_twice_is_refused(self):
        repo = self.tmp / "r"
        repo.mkdir()
        install(KIT, repo)
        again = install(KIT, repo)
        self.assertEqual(again.returncode, 1)
        self.assertIn("use `update`", again.stderr)

    def test_a_custom_ticket_prefix_and_directory_produce_a_consistent_project(self):
        other = self.tmp / "other"
        other.mkdir()
        init_git(other)
        install(KIT, other, "none")
        # start the project layer again with other settings
        (other / ".agents/workflow.toml").unlink()
        shutil.rmtree(other / "docs")
        run([sys.executable, str(other / ".agents/scripts/workflow_init.py"), "--root", str(other),
             "--id-prefix", "TKT", "--tickets-dir", "work/items"], check=True)
        (other / "work/items/TKT1.1-first.md").write_text(
            "# TKT1.1 · First\n\n> **Status:** ⏳ Pending\n")
        backlog = other / "work/items/README.md"
        backlog.write_text(backlog.read_text() + "| **Phase 1** | [TKT1.1](TKT1.1-first.md) | First | ⏳ Pending |\n")
        self.assertEqual(checker(other).returncode, 0, checker(other).stdout)
        commit(other, "feat(core): TKT1.1 - first")
        self.assertEqual(checker(other, "--commits", "3").returncode, 0)
        commit(other, "feat(core): T1.1 - wrong prefix")
        self.assertEqual(checker(other, "--commits", "3").returncode, 1)

    def test_init_dry_run_creates_nothing(self):
        repo = self.tmp / "r"
        repo.mkdir()
        install(KIT, repo)
        shutil.rmtree(repo / "docs")
        (repo / ".agents/workflow.toml").unlink()
        (repo / "CLAUDE.md").unlink()
        result = run([sys.executable, str(repo / ".agents/scripts/workflow_init.py"),
                      "--root", str(repo), "--dry-run"])
        self.assertIn("would create: .agents/workflow.toml", result.stdout)
        self.assertFalse((repo / ".agents/workflow.toml").exists())
        self.assertFalse((repo / "CLAUDE.md").exists())

    def test_an_existing_claude_directory_is_not_replaced(self):
        repo = self.tmp / "r"
        (repo / ".claude/agents").mkdir(parents=True)
        (repo / ".claude/agents/mine.md").write_text("mine\n")
        result = install(KIT, repo)
        self.assertEqual(result.returncode, 0)
        self.assertIn("kept .claude/agents", result.stdout)
        self.assertTrue((repo / ".claude/agents/mine.md").is_file())
        self.assertFalse((repo / ".claude/agents").is_symlink())


class UpdateKeepsTheProjectLayer(TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.repo = fixture_repo("node", self.tmp)
        # a project layer that has been lived in: edited rules and config, new tickets
        (self.repo / ".agents/rules/project.md").write_text("# our rules\n\nNo mutable globals.\n")
        cfg = self.repo / ".agents/workflow.toml"
        cfg.write_text(cfg.read_text().replace('["**/auth/**"]', '["**/auth/**", "src/payments/**"]'))
        (self.repo / "docs/tickets/T1.3-extra.md").write_text("# T1.3 · Extra\n\n> **Status:** ⏳ Pending\n")
        backlog = self.repo / "docs/tickets/README.md"
        backlog.write_text(backlog.read_text() + "| **Phase 1** | [T1.3](T1.3-extra.md) | Extra | ⏳ Pending |\n")
        (self.repo / ".agents/baseline.txt").write_text("src/legacy.js 40\n")
        (self.repo / ".agents/security-model.md").write_text("# our threat model\n")

    def test_updating_the_core_does_not_touch_rules_configuration_or_tickets(self):
        before = digest_tree(self.repo, CORE_PREFIXES + (".claude/",))
        nxt = newer_kit(self.tmp)
        skill = nxt / "core/skills/ticket-runner/SKILL.md"
        skill.write_text(skill.read_text() + "\n## 8. A new section in v0.2.0\n")
        (nxt / "core/commands/brand-new.md").write_text("---\ndescription: new\n---\nnew command\n")
        result = update(nxt, self.repo)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = digest_tree(self.repo, CORE_PREFIXES + (".claude/",))
        self.assertEqual(before, after, "project-layer files changed during update")
        # and the core really was updated
        self.assertIn("A new section in v0.2.0", (self.repo / ".agents/skills/ticket-runner/SKILL.md").read_text())
        self.assertTrue((self.repo / ".agents/commands/brand-new.md").is_file())
        self.assertIn("0.1.0 -> 0.2.0", result.stdout)
        self.assertEqual(checker(self.repo).returncode, 0)

    def test_a_core_file_modified_locally_is_a_conflict_and_is_kept(self):
        runner = self.repo / ".agents/skills/ticket-runner/SKILL.md"
        runner.write_text(runner.read_text() + "\nOur local addition.\n")
        nxt = newer_kit(self.tmp)
        upstream = nxt / "core/skills/ticket-runner/SKILL.md"
        upstream.write_text(upstream.read_text() + "\nUpstream change.\n")
        result = update(nxt, self.repo)
        self.assertEqual(result.returncode, 2)
        self.assertIn("conflict (modified locally, kept yours): .agents/skills/ticket-runner/SKILL.md", result.stdout)
        self.assertIn("Our local addition.", runner.read_text())
        self.assertNotIn("Upstream change.", runner.read_text())
        forced = update(nxt, self.repo, "--force")
        self.assertEqual(forced.returncode, 0, forced.stdout)
        self.assertIn("Upstream change.", runner.read_text())

    def test_a_file_dropped_by_the_new_version_is_removed_only_if_untouched(self):
        nxt = newer_kit(self.tmp)
        (nxt / "core/commands/ticket-status.md").unlink()
        (nxt / "core/commands/quality-gate.md").unlink()
        edited = self.repo / ".agents/commands/quality-gate.md"
        edited.write_text(edited.read_text() + "\nlocal edit\n")
        result = update(nxt, self.repo)
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.repo / ".agents/commands/ticket-status.md").exists())
        self.assertTrue(edited.exists(), "a locally edited file is not deleted")

    def test_update_with_nothing_new_changes_nothing(self):
        before = digest_tree(self.repo, ())
        result = update(KIT, self.repo)
        self.assertEqual(result.returncode, 0)
        self.assertIn("0 updated, 0 added, 0 removed", result.stdout)
        self.assertEqual(before, digest_tree(self.repo, ()))

    def test_status_reports_local_modifications(self):
        runner = self.repo / ".agents/skills/ticket-runner/SKILL.md"
        runner.write_text(runner.read_text() + "x\n")
        result = run([sys.executable, str(KIT / "install.py"), "status", "--target", str(self.repo)])
        self.assertIn("installed: 0.1.0", result.stdout)
        self.assertIn("modified locally: .agents/skills/ticket-runner/SKILL.md", result.stdout)

    def test_update_without_a_prior_install_is_refused(self):
        bare = self.tmp / "bare"
        bare.mkdir()
        result = update(KIT, bare)
        self.assertEqual(result.returncode, 1)
        self.assertIn("run `install` first", result.stderr)


if __name__ == "__main__":
    unittest.main()
