"""Acceptance criterion 2: the checker on three example repositories (Rust, Node, Python).

Each stack gets the same good and bad cases: it must detect a ticket without a backlog row,
a misaligned status, a file over the limit and a badly formatted commit, and it must not
raise false positives on correct repositories.
"""
import pathlib
import unittest

from helpers import STACKS, TempDirMixin, checker, commit, fixture_repo, init_git


def write(path: pathlib.Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def source_dir(stack: str) -> str:
    return {"rust": "src", "node": "src", "python": "app"}[stack]


def source_ext(stack: str) -> str:
    return {"rust": "rs", "node": "js", "python": "py"}[stack]


class CheckerOnThreeStacks(TempDirMixin, unittest.TestCase):
    def each_stack(self):
        """(stack, repo) pairs. Plain list on purpose: yielding inside `subTest` from a generator
        makes unittest report failures as an AttributeError instead of the assertion."""
        return [(stack, fixture_repo(stack, self.tmp)) for stack in STACKS]

    def test_correct_repositories_have_no_errors_and_no_false_positives(self):
        for stack, repo in self.each_stack():
            with self.subTest(stack=stack):
                result = checker(repo)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn("0 error(s), 0 warning(s)", result.stdout)

    def test_vendored_and_generated_directories_are_not_measured(self):
        # the fixtures hold a 30-line file under target/, node_modules/ and .venv/
        for stack, repo in self.each_stack():
            with self.subTest(stack=stack):
                result = checker(repo)
                self.assertNotIn("generated.rs", result.stdout)
                self.assertNotIn("vendored", result.stdout)
                self.assertEqual(result.returncode, 0, result.stdout)

    def test_detects_a_ticket_with_no_row_in_the_backlog(self):
        for stack, repo in self.each_stack():
            with self.subTest(stack=stack):
                write(repo / "docs/tickets/T1.3-orphan.md", "# T1.3 · Orphan\n\n> **Status:** ⏳ Pending\n")
                result = checker(repo)
                self.assertEqual(result.returncode, 1)
                self.assertIn("T1.3-orphan.md: does not appear in the backlog", result.stdout)

    def test_detects_a_row_pointing_to_a_missing_file(self):
        for stack, repo in self.each_stack():
            with self.subTest(stack=stack):
                backlog = repo / "docs/tickets/README.md"
                backlog.write_text(backlog.read_text() + "| **Phase 1** | [T1.9](T1.9-ghost.md) | Ghost | ⏳ Pending |\n")
                result = checker(repo)
                self.assertEqual(result.returncode, 1)
                self.assertIn("T1.9 links to T1.9-ghost.md, which does not exist", result.stdout)

    def test_detects_a_misaligned_status(self):
        for stack, repo in self.each_stack():
            with self.subTest(stack=stack):
                ticket = repo / "docs/tickets/T1.2-second.md"
                ticket.write_text(ticket.read_text().replace("⏳ Pending", "🔄 In progress"))
                result = checker(repo)
                self.assertEqual(result.returncode, 1)
                self.assertIn("T1.2-second.md: ticket status 🔄 differs from backlog ⏳", result.stdout)

    def test_detects_a_done_ticket_without_acceptance_criteria(self):
        for stack, repo in self.each_stack():
            with self.subTest(stack=stack):
                ticket = repo / "docs/tickets/T1.1-first.md"
                ticket.write_text(ticket.read_text().replace("## Acceptance Criteria", "## Notes"))
                result = checker(repo)
                self.assertEqual(result.returncode, 1)
                self.assertIn("marked done but has no «Acceptance Criteria» section", result.stdout)

    def test_detects_a_file_over_the_limit_and_only_warns_between_the_two(self):
        for stack, repo in self.each_stack():
            with self.subTest(stack=stack):
                ext, d = source_ext(stack), source_dir(stack)
                write(repo / f"{d}/big.{ext}", "x\n" * 12)      # 12 > error_lines (8)
                write(repo / f"{d}/medium.{ext}", "x\n" * 6)    # warn_lines (5) < 6 <= 8
                result = checker(repo)
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"{d}/big.{ext}: 12 lines > 8", result.stdout)
                self.assertIn(f"warning: {d}/medium.{ext}: 6 lines > 5", result.stdout)
                self.assertNotIn(f"ERROR: {d}/medium.{ext}", result.stdout)

    def test_baseline_acknowledges_debt_but_forbids_growth(self):
        for stack, repo in self.each_stack():
            with self.subTest(stack=stack):
                ext, d = source_ext(stack), source_dir(stack)
                write(repo / f"{d}/legacy.{ext}", "x\n" * 12)
                (repo / ".agents/baseline.txt").write_text(f"{d}/legacy.{ext} 12\n")
                ok = checker(repo)
                self.assertEqual(ok.returncode, 0, ok.stdout)
                self.assertIn("acknowledged debt", ok.stdout)
                write(repo / f"{d}/legacy.{ext}", "x\n" * 13)
                grew = checker(repo)
                self.assertEqual(grew.returncode, 1)
                self.assertIn("grows over its baseline (12)", grew.stdout)

    def test_detects_a_badly_formatted_commit_and_accepts_a_good_one(self):
        for stack, repo in self.each_stack():
            with self.subTest(stack=stack):
                init_git(repo)
                commit(repo, "feat(core): T1.1 - first ticket")
                good = checker(repo, "--commits", "5")
                self.assertEqual(good.returncode, 0, good.stdout)
                commit(repo, "fix stuff")
                bad = checker(repo, "--commits", "5")
                self.assertEqual(bad.returncode, 1)
                self.assertIn("«fix stuff» does not follow <type>(<area>): <TID> - <title>", bad.stdout)

    def test_gates_are_resolved_from_the_stack_preset(self):
        expected = {
            "rust": {"format", "lint", "test"},
            "node": {"lint", "typecheck", "test"},
            "python": {"lint", "format", "test"},
        }
        for stack, repo in self.each_stack():
            with self.subTest(stack=stack):
                result = checker(repo, "gates")
                self.assertEqual(result.returncode, 0, result.stderr)
                names = {line.split("\t")[0] for line in result.stdout.splitlines()}
                self.assertEqual(names, expected[stack])


class CheckerConfiguration(TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.repo = fixture_repo("python", self.tmp)
        self.config = self.repo / ".agents/workflow.toml"

    def test_missing_configuration_is_a_clear_error(self):
        self.config.unlink()
        result = checker(self.repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("workflow.toml not found", result.stdout)

    def test_invalid_toml_and_invalid_regex_are_errors_not_crashes(self):
        self.config.write_text("this is = = not toml")
        self.assertIn("invalid TOML", checker(self.repo).stdout)
        self.config.write_text('[tickets]\nid_pattern = "(unclosed"\n')
        result = checker(self.repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a valid regex", result.stdout)

    def test_unknown_preset_is_an_error(self):
        self.config.write_text(self.config.read_text().replace('preset = "python"', 'preset = "cobol"'))
        result = checker(self.repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown stack preset «cobol»", result.stdout)

    def test_every_switched_off_check_or_gate_is_reported_on_every_run(self):
        self.config.write_text(
            self.config.read_text()
            + '\n[checks]\nsizes = false\nbacklog = false\n'
            + '\n[gates.override.lint]\nenabled = false\n'
        )
        result = checker(self.repo)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("check «sizes» is DISABLED", result.stdout)
        self.assertIn("check «backlog» is DISABLED", result.stdout)
        self.assertIn("gate «lint» is DISABLED", result.stdout)
        gates = checker(self.repo, "gates")
        self.assertNotIn("lint\t", gates.stdout)
        self.assertIn("DISABLED", gates.stderr)

    def test_a_disabled_check_really_does_not_run(self):
        write(self.repo / "app/big.py", "x\n" * 20)
        self.config.write_text(self.config.read_text() + '\n[checks]\nsizes = false\n')
        self.assertEqual(checker(self.repo).returncode, 0)

    def test_gate_override_and_extra_gates(self):
        self.config.write_text(
            self.config.read_text()
            + '\n[gates.override.test]\ncommand = "make test"\n'
            + '\n[[gates.extra]]\nname = "docs"\ncommand = "make docs"\n'
        )
        lines = dict(l.split("\t") for l in checker(self.repo, "gates").stdout.splitlines())
        self.assertEqual(lines["test"], "make test")
        self.assertEqual(lines["docs"], "make docs")

    def test_custom_ticket_format_is_honoured(self):
        # another id prefix, other statuses and another header line
        (self.repo / "docs/tickets").rename(self.repo / "work")
        self.config.write_text(
            self.config.read_text()
            .replace('dir = "docs/tickets"', 'dir = "work"')
            .replace('backlog = "docs/tickets/README.md"', 'backlog = "work/README.md"\nid_pattern = \'T\\d+\\.\\d+\'')
        )
        self.assertEqual(checker(self.repo).returncode, 0)

    def test_sensitive_surfaces_are_matched_by_glob(self):
        write(self.repo / "app/auth/login.py", "x = 1\n")
        write(self.repo / "app/other.py", "x = 1\n")
        result = checker(self.repo, "sensitive", "app/auth/login.py", "app/other.py", "deep/er/auth/x.py")
        self.assertEqual(result.stdout.split(), ["app/auth/login.py", "deep/er/auth/x.py"])

    def test_sensitive_reads_the_git_changes_when_no_paths_are_given(self):
        init_git(self.repo)
        commit(self.repo, "feat(core): T1.1 - first")
        write(self.repo / "app/auth/login.py", "x = 1\n")
        write(self.repo / "app/other.py", "x = 1\n")
        result = checker(self.repo, "sensitive")
        self.assertEqual(result.stdout.split(), ["app/auth/login.py"])


if __name__ == "__main__":
    unittest.main()
