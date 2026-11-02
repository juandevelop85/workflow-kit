"""T1.6: review agents that cannot change files; the diff is handed to them."""
import os
import unittest

from helpers import TempDirMixin, checker, commit, fixture_repo, init_git, run
from test_workflow_check import write


class ReviewDiff(TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.repo = fixture_repo("python", self.tmp)

    def test_review_plan_writes_the_diff_for_reviewers(self):
        repo = self.repo
        init_git(repo)
        write(repo / "app/main.py", "print('old')\n")
        commit(repo, "feat(core): T1.1 - first")
        write(repo / "app/main.py", "print('new')\n")
        write(repo / "app/added.py", "ADDED = True\n")
        out = checker(repo, "review-plan", "--write-diff").stdout
        self.assertIn("diff for the reviewers: .agents/.cache/review/diff.patch", out)
        patch = (repo / ".agents/.cache/review/diff.patch").read_text()
        self.assertIn("-print('old')", patch)
        self.assertIn("+print('new')", patch)
        self.assertIn("+ADDED = True", patch, "untracked files are part of the diff")


    def test_write_diff_refuses_a_symlinked_cache(self):
        init_git(self.repo)
        commit(self.repo, "feat(core): T1.1 - first")
        outside = self.tmp / "victim.txt"
        outside.write_text("precious\n")
        review = self.repo / ".agents/.cache/review"
        review.mkdir(parents=True)
        os.symlink(outside, review / "diff.patch")
        result = checker(self.repo, "review-plan", "--write-diff")
        self.assertEqual(result.returncode, 1)
        self.assertIn("refusing to write", result.stderr)
        self.assertEqual(outside.read_text(), "precious\n")
        for leftover in review.iterdir():
            leftover.unlink()
        review.rmdir()
        os.symlink(self.tmp, review)
        self.assertIn("refusing to write through a symlink", checker(self.repo, "review-plan", "--write-diff").stderr)

    def test_write_diff_never_runs_an_external_diff(self):
        init_git(self.repo)
        write(self.repo / "app/main.py", "a = 1\n")
        commit(self.repo, "feat(core): T1.1 - first")
        marker = self.tmp / "ran"
        run(["git", "config", "diff.external", f"touch {marker} #"], cwd=self.repo, check=True)
        write(self.repo / "app/main.py", "a = 2\n")
        checker(self.repo, "review-plan", "--write-diff")
        self.assertFalse(marker.exists(), "the repository's diff.external ran")
        self.assertIn("+a = 2", (self.repo / ".agents/.cache/review/diff.patch").read_text())

    def test_write_diff_covers_base_names_binaries_and_no_commits(self):
        init_git(self.repo)
        write(self.repo / "app/staged.py", "STAGED = 1\n")
        run(["git", "add", "app/staged.py"], cwd=self.repo, check=True)
        checker(self.repo, "review-plan", "--write-diff")
        self.assertIn("+STAGED = 1", (self.repo / ".agents/.cache/review/diff.patch").read_text(), "no commits yet")
        commit(self.repo, "feat(core): T1.1 - first")
        base = run(["git", "rev-parse", "HEAD"], cwd=self.repo).stdout.strip()
        write(self.repo / "app/committed.py", "COMMITTED = 1\n")
        commit(self.repo, "feat(core): T1.2 - second")
        write(self.repo / "app/é.py", "ACCENT = 1\n")
        (self.repo / "app/blob.bin").write_bytes(b"\0\1\2")
        checker(self.repo, "review-plan", "--write-diff", "--base", base)
        patch = (self.repo / ".agents/.cache/review/diff.patch").read_text()
        self.assertIn("+COMMITTED = 1", patch, "--base")
        self.assertIn("+ACCENT = 1", patch, "a non-ASCII name")
        self.assertIn("GIT binary patch", patch)
        working = (self.repo / ".agents/.cache/review/working.patch").read_text()
        self.assertNotIn("COMMITTED", working, "the working patch applies on HEAD")
        wt = self.tmp / "wt"
        run(["git", "worktree", "add", "--detach", str(wt), "HEAD"], cwd=self.repo, check=True)
        applied = run(["git", "-C", str(wt), "apply", "--binary", str(self.repo / ".agents/.cache/review/working.patch")])
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual((wt / "app/blob.bin").read_bytes(), b"\0\1\2")

    def test_fingerprint_sees_a_further_edit(self):
        init_git(self.repo)
        write(self.repo / "app/main.py", "a = 1\n")
        commit(self.repo, "feat(core): T1.1 - first")
        write(self.repo / "app/main.py", "a = 2\n")
        before = checker(self.repo, "fingerprint").stdout.strip()
        self.assertEqual(checker(self.repo, "fingerprint").stdout.strip(), before, "stable")
        status = run(["git", "status", "--porcelain"], cwd=self.repo).stdout
        write(self.repo / "app/main.py", "a = 3\n")
        self.assertEqual(run(["git", "status", "--porcelain"], cwd=self.repo).stdout, status, "git status is blind")
        self.assertNotEqual(checker(self.repo, "fingerprint").stdout.strip(), before)

    def test_write_diff_never_runs_a_textconv_driver(self):
        init_git(self.repo)
        write(self.repo / ".gitattributes", "*.py diff=evil\n")
        write(self.repo / "app/main.py", "a = 1\n")
        commit(self.repo, "feat(core): T1.1 - first")
        marker = self.tmp / "ran"
        run(["git", "config", "diff.evil.textconv", f"sh -c 'touch {marker}; cat \"$0\"'"], cwd=self.repo, check=True)
        write(self.repo / "app/main.py", "a = 2\n")
        checker(self.repo, "review-plan", "--write-diff")
        checker(self.repo, "fingerprint")
        self.assertFalse(marker.exists(), "the repository's textconv driver ran")

    def test_write_diff_handles_symlinks_large_files_and_unquoted_names(self):
        init_git(self.repo)
        commit(self.repo, "feat(core): T1.1 - first")
        secret = self.tmp / "secret.txt"
        secret.write_text("TOP SECRET\n")
        os.symlink(secret, self.repo / "app/link")
        os.symlink(self.tmp, self.repo / "app/linkdir")
        (self.repo / "app/huge.txt").write_text("x" * 1_000_001)
        write(self.repo / "app/é.py", "ACCENT = 1\n")
        checker(self.repo, "review-plan", "--write-diff")
        patch = (self.repo / ".agents/.cache/review/diff.patch").read_text()
        self.assertIn(f"+{secret}", patch, "an untracked symlink shows its target")
        self.assertNotIn("TOP SECRET", patch, "never the target's content")
        self.assertIn("# untracked symlink app/linkdir ->", patch)
        self.assertIn("# skipped untracked app/huge.txt: over 1000000 bytes", patch)
        self.assertNotIn("xxxxxxxxxx", patch)
        self.assertIn("diff --git a/app/é.py b/app/é.py", patch, "names are not quoted")

    def test_fingerprint_sees_staging(self):
        init_git(self.repo)
        write(self.repo / "app/main.py", "a = 1\n")
        commit(self.repo, "feat(core): T1.1 - first")
        write(self.repo / "app/main.py", "a = 2\n")
        before = checker(self.repo, "fingerprint").stdout.strip()
        run(["git", "add", "app/main.py"], cwd=self.repo, check=True)
        self.assertNotEqual(checker(self.repo, "fingerprint").stdout.strip(), before)

    def test_an_option_is_not_a_base(self):
        init_git(self.repo)
        commit(self.repo, "feat(core): T1.1 - first")
        result = checker(self.repo, "review-plan", "--base=--output=/tmp/x")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--base must be a git ref", result.stderr)


if __name__ == "__main__":
    unittest.main()
