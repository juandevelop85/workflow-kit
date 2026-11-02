"""T1.4: honest closing and a stricter backlog."""
import unittest

from helpers import TempDirMixin, checker, commit, fixture_repo, init_git, run
from test_workflow_check import write

DONE = "# T1.1 · First ticket\n\n> **Status:** ✅ Done\n\n## Description\n\nDone.\n\n"


class HonestBacklog(TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.repo = fixture_repo("python", self.tmp)
        self.tickets = self.repo / "docs/tickets"
        self.backlog = self.tickets / "README.md"
        self.config = self.repo / ".agents/workflow.toml"

    def errors(self):
        result = checker(self.repo)
        return result.returncode, result.stdout

    def test_done_needs_a_real_criteria_section(self):
        write(self.tickets / "T1.1-first.md", DONE + "## Acceptance Criteria\n\n## Risks\n\n- none\n")
        code, out = self.errors()
        self.assertEqual(code, 1)
        self.assertIn("T1.1-first.md: marked done but «Acceptance Criteria» lists 0 criteria (minimum 1)", out)
        write(self.tickets / "T1.1-first.md", DONE + "The Acceptance Criteria were discussed.\n")
        self.assertIn("marked done but has no «## Acceptance Criteria» heading", self.errors()[1])
        self.config.write_text(self.config.read_text().replace(
            'backlog = "docs/tickets/README.md"', 'backlog = "docs/tickets/README.md"\ndone_min_criteria = 2'))
        write(self.tickets / "T1.1-first.md", DONE + "## Acceptance Criteria\n\n- test: one\n")
        self.assertIn("lists 1 criteria (minimum 2)", self.errors()[1])
        write(self.tickets / "T1.1-first.md", DONE + "## Acceptance Criteria\n\n- test: one\n1. test: two\n")
        self.assertEqual(self.errors()[0], 0)
        # sub-bullets, empty checkboxes and lists inside code fences are not criteria
        write(self.tickets / "T1.1-first.md", DONE + "## Acceptance Criteria\n\n- test: one\n  - detail\n"
              "  - detail\n- [ ]\n```\n- x\n## not a heading\n- y\n```\n")
        self.assertIn("lists 1 criteria (minimum 2)", self.errors()[1])

    def test_status_without_variation_selector_matches(self):
        self.backlog.write_text(self.backlog.read_text().replace("⏳ Pending", "⏸ Deferred"))
        write(self.tickets / "T1.2-second.md", "# T1.2 · Second\n\n> **Status:** ⏸️ Deferred\n")
        code, out = self.errors()
        self.assertEqual(code, 0, out)
        self.assertIn("0 error(s), 0 warning(s)", out)

    def test_statuses_that_differ_only_by_variation_selector_are_rejected(self):
        self.config.write_text(self.config.read_text() + '\n[tickets.statuses]\nproposed = "\u23f8"\n')
        self.assertIn("statuses «deferred» and «proposed» cannot be told apart", self.errors()[1])

    def test_duplicate_ids_are_an_error(self):
        self.backlog.write_text(self.backlog.read_text()
                                + "| **Phase 1** | [T1.2](T1.2-second.md) | Again | ⏳ Pending |\n")
        self.assertIn("backlog: T1.2 appears more than once", self.errors()[1])

    def test_link_must_point_at_the_ticket_file(self):
        self.backlog.write_text(self.backlog.read_text().replace("(T1.2-second.md)", "(old/T1.2-second.md)"))
        code, out = self.errors()
        self.assertEqual(code, 1)
        self.assertIn("backlog: T1.2 links to old/T1.2-second.md, but its file is docs/tickets/T1.2-second.md", out)

    def test_relative_links_that_reach_the_file_are_fine(self):
        self.backlog.write_text(self.backlog.read_text().replace("(T1.2-second.md)", "(./T1.2-second.md)"))
        self.assertEqual(self.errors()[0], 0)
        moved = self.repo / "docs/BACKLOG.md"
        moved.write_text(self.backlog.read_text().replace("(./T1.", "(tickets/T1.").replace("(T1.1", "(tickets/T1.1"))
        self.backlog.unlink()
        self.config.write_text(self.config.read_text().replace('backlog = "docs/tickets/README.md"',
                                                               'backlog = "docs/BACKLOG.md"'))
        code, out = self.errors()
        self.assertEqual(code, 0, out)

    def test_malformed_baseline_is_a_config_error(self):
        (self.repo / ".agents/baseline.txt").write_text("# debt\napp/main.py lots\n")
        code, out = self.errors()
        self.assertEqual(code, 1)
        self.assertIn(".agents/baseline.txt:2: expected «<path> <maximum lines>», got «app/main.py lots»", out)
        self.assertNotIn("Traceback", out)
        (self.repo / ".agents/baseline.txt").write_text("  # indented comment\napp/main.py \u00b2\n")
        code, out = self.errors()
        self.assertIn("baseline.txt:2: expected", out)
        self.assertNotIn("baseline.txt:1", out)


class CommitsCiteRealTickets(TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.repo = fixture_repo("python", self.tmp)
        self.config = self.repo / ".agents/workflow.toml"

    def test_default_commit_pattern_follows_id_pattern(self):
        tickets = self.repo / "docs/tickets"
        for name in ("T1.1-first.md", "T1.2-second.md"):
            (tickets / name).rename(tickets / name.replace("T1.", "PROJ-1"))
        backlog = tickets / "README.md"
        backlog.write_text(backlog.read_text().replace("T1.", "PROJ-1"))
        self.config.write_text(self.config.read_text().replace(
            'backlog = "docs/tickets/README.md"',
            'backlog = "docs/tickets/README.md"\nid_pattern = \'PROJ-\\d+\'\nfile_glob = "PROJ-*.md"'))
        init_git(self.repo)
        commit(self.repo, "feat(core): PROJ-11 - first")
        result = checker(self.repo, "--commits", "5")
        self.assertEqual(result.returncode, 0, result.stdout)
        commit(self.repo, "feat(core): T1.1 - old style")
        self.assertIn("«feat(core): T1.1 - old style» does not follow", checker(self.repo, "--commits", "5").stdout)

    def test_commit_must_cite_a_ticket_of_the_backlog(self):
        init_git(self.repo)
        commit(self.repo, "feat(core): T1.1 - first")
        commit(self.repo, "feat(core): T43.1 - from another project")
        result = checker(self.repo, "--commits", "5")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cites T43.1, which is not in the backlog (history from before the kit: set [commits].since)",
                      result.stdout)
        self.assertNotIn("cites T1.1", result.stdout)

    def test_commits_since_exempts_older_history(self):
        init_git(self.repo)
        commit(self.repo, "feat(core): T43.1 - before the adoption")
        sha = run(["git", "rev-parse", "HEAD"], cwd=self.repo).stdout.strip()
        commit(self.repo, "feat(core): T1.1 - after the adoption")
        self.config.write_text(self.config.read_text() + f'\n[commits]\nsince = "{sha}"\n')
        result = checker(self.repo, "--commits", "5")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_an_invalid_since_is_a_readable_error(self):
        init_git(self.repo)
        commit(self.repo, "feat(core): T1.1 - first")
        self.config.write_text(self.config.read_text() + '\n[commits]\nsince = "nosuchref"\n')
        result = checker(self.repo, "--commits", "5")
        self.assertEqual(result.returncode, 1)
        self.assertIn("[commits].since «nosuchref» is not a commit of this repository", result.stdout)

    def test_the_area_is_never_taken_for_a_ticket_id(self):
        self.config.write_text(self.config.read_text().replace(
            'backlog = "docs/tickets/README.md"', 'backlog = "docs/tickets/README.md"\nid_pattern = \'T\\d+\\.\\d+|X\\d+\''))
        init_git(self.repo)
        commit(self.repo, "feat(api2): T1.1 - first")
        self.assertEqual(checker(self.repo, "--commits", "5").returncode, 0)
        commit(self.repo, "feat(core): T1.1 - and X9 too")
        self.assertIn("cites X9, which is not in the backlog", checker(self.repo, "--commits", "5").stdout)

    def test_commit_check_outside_git_is_an_error(self):
        result = checker(self.repo, "--commits", "5")
        self.assertEqual(result.returncode, 1)
        self.assertIn("the commit check needs a git repository", result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
