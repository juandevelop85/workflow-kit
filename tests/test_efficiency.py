"""Token-saving features: `context`, `review-plan` and `gates --run`."""
import unittest

from helpers import TempDirMixin, checker, commit, fixture_repo, init_git
from test_workflow_check import write


class Efficiency(TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.repo = fixture_repo("python", self.tmp)
        self.config = self.repo / ".agents/workflow.toml"
        write(self.repo / "docs/tickets/T1.2-second.md",
              "# T1.2 · Second ticket\n\n> **Status:** ⏳ Pending\n> **Depends on:** T1.1, T1.5\n\n"
              "## Description\n\nDo it.\n\n## Acceptance Criteria\n\n- test: a\n- test: b\n- test: c\n\n## Risks\n\nnone\n")

    def plan(self, *args):
        return checker(self.repo, "review-plan", *args)

    # --- context
    def test_context_is_a_compact_brief_with_dependency_status(self):
        out = checker(self.repo, "context", "T1.2").stdout
        self.assertIn("ticket: T1.2 · Second ticket", out)
        self.assertIn("T1.1: ✅ Done", out)
        self.assertNotIn("T1.1: ✅ Done   <-- NOT DONE", out)
        self.assertIn("T1.5: not in the backlog   <-- NOT DONE", out)
        self.assertIn("- test: c", out)
        self.assertNotIn("Risks", out)
        self.assertIn(".agents/rules/project.md", out)

    def test_context_does_not_confuse_t1_1_with_t1_10(self):
        write(self.repo / "docs/tickets/T1.10-tenth.md", "# T1.10 · Tenth\n")
        write(self.repo / "docs/tickets/T1.1-first.md", "# T1.1 · First\n\n## Acceptance Criteria\n\n- x\n")
        self.assertIn("ticket: T1.1 · First", checker(self.repo, "context", "T1.1").stdout)

    def test_context_unknown_ticket_is_an_error(self):
        result = checker(self.repo, "context", "T9.9")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no ticket file for T9.9", result.stderr)

    # --- review-plan
    def test_no_changes_launches_nothing(self):
        init_git(self.repo)
        commit(self.repo, "feat(core): T1.1 - first")
        self.assertIn("launch: none", self.plan().stdout)

    def test_tiny_or_docs_only_change_is_self_reviewed(self):
        init_git(self.repo)
        commit(self.repo, "feat(core): T1.1 - first")
        write(self.repo / "app/small.py", "x = 1\n" * 5)
        out = self.plan().stdout
        self.assertIn("launch: none", out)
        self.assertIn("self-review", out)
        (self.repo / "app/small.py").unlink()
        write(self.repo / "docs/big.md", "line\n" * 200)
        self.assertIn("launch: none", self.plan().stdout)
        self.assertIn("docs-only", self.plan().stdout)

    def test_a_real_change_launches_reviewer_and_auditor_by_criteria(self):
        init_git(self.repo)
        commit(self.repo, "feat(core): T1.1 - first")
        write(self.repo / "app/big.py", "x = 1\n" * 100)
        self.assertIn("launch: reviewer\n", self.plan().stdout)
        self.assertIn("launch: reviewer test-auditor\n", self.plan("--ticket", "T1.2").stdout)

    def test_a_modified_line_is_counted_once(self):
        init_git(self.repo)
        write(self.repo / "app/tracked.py", "x = 1\n")
        commit(self.repo, "feat(core): T1.1 - first")
        write(self.repo / "app/tracked.py", "x = 1\n" + "y = 2\n" * 20)
        self.assertIn("diff: 1 file(s), 20 changed line(s)", self.plan().stdout)

    def test_a_sensitive_change_always_gets_the_security_reviewer(self):
        init_git(self.repo)
        commit(self.repo, "feat(core): T1.1 - first")
        self.config.write_text(self.config.read_text().replace("globs = []", 'globs = ["app/auth/**"]'))
        write(self.repo / "app/auth/login.py", "x = 1\n")
        self.assertIn("launch: security-reviewer\n", self.plan().stdout)

    def test_thresholds_are_configurable_and_validated(self):
        init_git(self.repo)
        commit(self.repo, "feat(core): T1.1 - first")
        write(self.repo / "app/mid.py", "x = 1\n" * 50)
        self.config.write_text(self.config.read_text() + "\n[efficiency]\nlight_max_lines = 100\n")
        self.assertIn("launch: none", self.plan().stdout)
        self.config.write_text(self.config.read_text().replace("= 100", '= "many"') + "bogus = 1\n")
        result = checker(self.repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("[efficiency].light_max_lines has an invalid value", result.stdout)
        self.assertIn("unknown key «bogus» in [efficiency]", result.stdout)

    # --- gates --run
    def set_gates(self, *gates):
        text = self.config.read_text().replace('preset = "python"', 'preset = "none"')
        for name, cmd in gates:
            text += f'\n[[gates.extra]]\nname = "{name}"\ncommand = "{cmd}"\n'
        self.config.write_text(text)

    def test_passing_gate_costs_one_line_and_its_output_goes_to_a_log(self):
        self.set_gates(("noisy", "seq 1 500"))
        result = checker(self.repo, "gates", "--run")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("PASS noisy", result.stdout)
        self.assertNotIn("499", result.stdout)
        log = self.repo / ".agents/.cache/gates/noisy.log"
        self.assertIn("500", log.read_text())

    def test_failing_gate_shows_only_the_tail_and_fails_the_run(self):
        self.set_gates(("boom", "seq 1 100; exit 3"), ("fine", "true"))
        result = checker(self.repo, "gates", "--run", "--tail", "3")
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL boom (exit 3", result.stdout)
        self.assertIn("| 100", result.stdout)
        self.assertNotIn("| 90", result.stdout)
        self.assertIn("PASS fine", result.stdout)
        self.assertIn("2 gate(s): 1 passed, 1 failed", result.stdout)

    def test_the_gate_log_directory_ignores_itself_in_git(self):
        self.set_gates(("g", "true"))
        init_git(self.repo)
        commit(self.repo, "feat(core): T1.1 - first")
        checker(self.repo, "gates", "--run")
        from helpers import run
        self.assertEqual(run(["git", "status", "--porcelain"], cwd=self.repo).stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
