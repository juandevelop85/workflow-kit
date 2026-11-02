"""T1.5: proportional ceremony. `classify` sets a minimum lane; quick commits are audited."""
import json
import sys
import unittest
from unittest import mock

from helpers import KIT, TempDirMixin, checker, commit, fixture_repo, init_git, run
from test_workflow_check import write


class Lanes(TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.repo = fixture_repo("python", self.tmp)
        self.config = self.repo / ".agents/workflow.toml"
        init_git(self.repo)
        commit(self.repo, "feat(core): T1.1 - first")

    def lane(self):
        result = checker(self.repo, "classify", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_small_change_is_quick(self):
        write(self.repo / "docs/guide.md", "line\n" * 250)
        self.assertEqual(self.lane()["lane"], "quick")
        (self.repo / "docs/guide.md").unlink()
        write(self.repo / "app/small.py", "x = 1\n" * 5)
        self.assertEqual(self.lane()["lane"], "quick")
        out = checker(self.repo, "classify").stdout
        self.assertIn("minimum lane: quick", out)
        self.assertIn("raise the lane if any answer is no", out)

    def test_sensitive_change_is_at_least_standard(self):
        write(self.repo / "app/auth/token.py", "TTL = 1\n")
        plan = self.lane()
        self.assertEqual(plan["lane"], "standard")
        self.assertIn("touches a sensitive surface: app/auth/token.py", "; ".join(plan["reasons"]))

    def test_code_without_tests_is_standard(self):
        write(self.repo / "app/feature.py", "x = 1\n" * 6)
        self.assertEqual(self.lane()["lane"], "standard")
        write(self.repo / "tests/test_feature.py", "def test_x():\n    assert True\n")
        self.assertEqual(self.lane()["lane"], "quick")

    def test_large_change_is_deep(self):
        write(self.repo / "app/big.py", "x = 1\n" * 400)
        self.assertEqual(self.lane()["lane"], "deep")
        (self.repo / "app/big.py").unlink()
        for i in range(15):
            write(self.repo / f"app/m{i}.py", "x = 1\n")
        self.assertEqual(self.lane()["lane"], "deep")
        for i in range(15):
            (self.repo / f"app/m{i}.py").unlink()
        write(self.repo / "docs/book.md", "line\n" * 900)
        self.assertEqual(self.lane()["lane"], "standard", "docs alone are never deep")

    def test_honest_quick_commit_passes(self):
        write(self.repo / "docs/guide.md", "typo fixed\n")
        commit(self.repo, "docs(guide): quick - fix a typo")
        result = checker(self.repo, "--commits", "5")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_oversized_quick_commit_is_an_error(self):
        write(self.repo / "app/feature.py", "x = 1\n" * 60)
        commit(self.repo, "feat(app): quick - a whole feature")
        result = checker(self.repo, "--commits", "5")
        self.assertEqual(result.returncode, 1)
        self.assertIn("is marked quick but needs the standard lane", result.stdout)
        write(self.repo / "app/sized.py", "x = 1\n" * 45)
        write(self.repo / "tests/test_sized.py", "def test_sized():\n    assert True\n")
        commit(self.repo, "feat(app): quick - tested but too big")
        self.assertIn("47 changed lines > 40", checker(self.repo, "--commits", "1").stdout)
        write(self.repo / "app/auth/x.py", "y = 1\n")
        commit(self.repo, "fix(auth): quick - tiny")
        self.assertIn("touches a sensitive surface: app/auth/x.py", checker(self.repo, "--commits", "1").stdout)

    def configure(self, text):
        """Change the configuration in its own commit, so the change under test is not a config change."""
        self.config.write_text(self.config.read_text() + text)
        commit(self.repo, "chore(core): T1.1 - configure")

    def test_size_alone_makes_a_change_standard(self):
        write(self.repo / "app/a.py", "x = 1\n" * 41)
        write(self.repo / "tests/test_a.py", "def test_a():\n    assert True\n")
        self.assertEqual(self.lane()["lane"], "standard")
        (self.repo / "app/a.py").unlink()
        for i in range(5):
            write(self.repo / f"app/f{i}.py", "x = 1\n")
        self.assertEqual(self.lane()["lane"], "standard", "6 files > 5")

    def test_the_quick_line_limit_is_exact(self):
        write(self.repo / "tests/test_a.py", "def test_a():\n    assert True\n")
        write(self.repo / "app/a.py", "x = 1\n" * 38)
        self.assertEqual(self.lane()["lane"], "quick", "40 lines")
        write(self.repo / "app/a.py", "x = 1\n" * 39)
        self.assertEqual(self.lane()["lane"], "standard", "41 lines")

    def test_a_staged_move_into_a_sensitive_path_is_standard(self):
        write(self.repo / "app/helper.py", "def helper():\n    return 1\n")
        commit(self.repo, "feat(core): T1.1 - helper")
        (self.repo / "app/auth").mkdir()
        run(["git", "mv", "app/helper.py", "app/auth/helper.py"], cwd=self.repo, check=True)
        self.assertEqual(self.lane()["lane"], "standard")

    def test_an_unmeasurable_quick_commit_fails_the_audit(self):
        write(self.repo / "docs/guide.md", "note\n")
        commit(self.repo, "docs(guide): quick - note")
        sys.path.insert(0, str(KIT / "core" / "scripts"))
        from workflow_kit import checks, config
        errors, warnings = [], []
        with mock.patch.object(checks, "commit_size", return_value=None):
            checks.check_commits(self.repo, config.load_config(self.repo), 1, errors, warnings)
        self.assertTrue(any("could not measure its diff" in e for e in errors), errors)

    def test_a_txt_or_a_script_under_docs_is_not_prose(self):
        write(self.repo / "requirements.txt", "pkg\n" * 250)
        self.assertEqual(self.lane()["lane"], "standard")

    def test_changing_the_workflow_is_never_quick(self):
        self.config.write_text(self.config.read_text().replace('globs = ["**/auth/**"]', "globs = []"))
        plan = self.lane()
        self.assertEqual(plan["lane"], "standard")
        self.assertIn("changes the workflow itself: .agents/workflow.toml", "; ".join(plan["reasons"]))
        commit(self.repo, "chore(core): quick - loosen the rules")
        self.assertIn("is marked quick but needs the standard lane", checker(self.repo, "--commits", "1").stdout)

    def test_a_move_into_a_sensitive_path_is_caught(self):
        write(self.repo / "app/helper.py", "def helper():\n    return 1\n")
        write(self.repo / "tests/test_helper.py", "def test_helper():\n    assert True\n")
        commit(self.repo, "feat(app): quick - add a helper")
        self.assertEqual(checker(self.repo, "--commits", "1").returncode, 0)
        (self.repo / "app/auth").mkdir()
        run(["git", "mv", "app/helper.py", "app/auth/helper.py"], cwd=self.repo, check=True)
        commit(self.repo, "refactor(app): quick - move the helper")
        self.assertIn("touches a sensitive surface: app/auth/helper.py", checker(self.repo, "--commits", "1").stdout)

    def test_binary_files_are_never_quick(self):
        (self.repo / "app/blob.bin").write_bytes(b"\0\1\2" * 1000)
        self.assertEqual(self.lane()["lane"], "standard")
        commit(self.repo, "chore(app): quick - add a blob")
        self.assertIn("binary files", checker(self.repo, "--commits", "1").stdout)

    def test_a_quick_commit_cannot_cite_a_ticket_outside_the_backlog(self):
        write(self.repo / "docs/guide.md", "note\n")
        commit(self.repo, "docs(guide): quick - T9.9 follow-up")
        self.assertIn("cites T9.9, which is not in the backlog", checker(self.repo, "--commits", "1").stdout)

    def test_the_quick_lane_can_be_turned_off(self):
        self.configure("\n[lanes]\nquick_pattern = ''\n")
        write(self.repo / "docs/guide.md", "note\n")
        plan = self.lane()
        self.assertEqual(plan["lane"], "standard")
        self.assertIn("the quick lane is turned off", "; ".join(plan["reasons"]))

    def test_classify_refuses_an_invalid_configuration(self):
        self.config.write_text(self.config.read_text() + '\n[lanes]\nquick_max_lines = "abc"\ntest_globs = [1]\n')
        result = checker(self.repo, "classify")
        self.assertEqual(result.returncode, 1)
        self.assertIn("[lanes].quick_max_lines has an invalid value", result.stderr)
        self.assertIn("[lanes].test_globs must be a list of strings", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_lane_settings_are_validated(self):
        self.configure("\n[lanes]\nuntested_code_max_lines = 0\n")
        write(self.repo / "app/mid.py", "x = 1\n" * 3)
        self.assertEqual(self.lane()["lane"], "standard")
        self.config.write_text(self.config.read_text().replace("= 0", "= -2") + "nonsense = 1\nquick_pattern = '(['\n")
        result = checker(self.repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("[lanes].untested_code_max_lines has an invalid value", result.stdout)
        self.assertIn("unknown key «nonsense» in [lanes]", result.stdout)
        self.assertIn("[lanes].quick_pattern is not a valid regex", result.stdout)


if __name__ == "__main__":
    unittest.main()
