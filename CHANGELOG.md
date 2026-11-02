# Changelog

## 0.1.0 (unreleased)

First extraction of the workflow framework as a product-agnostic kit: core (4 skills, 3 agents,
7 commands, the checker, 3 stack presets, templates), an installer with a manifest so that updating
never overwrites the project layer, and tests over fixtures for Rust, Node and Python.

Token economy: `workflow_check.py context` (compact ticket brief), `review-plan` (which review
subagents this diff deserves), `gates --run` (one line per gate, full output in a git-ignored log),
capped one-line-per-finding output for the three review agents, and a cheaper model for
`test-auditor`. Tunable in `[efficiency]`.

Dogfooding: the kit is developed with its own workflow (project layer in `.agents/`, backlog in
`docs/tickets/`, `tests/test_dogfood.py` runs the checker over the kit).

The checker is a package (`.agents/scripts/workflow_kit/`, no module over 400 lines); the entry
point `workflow_check.py` and its subcommands are unchanged.

Honest backlog: a done ticket needs a real criteria section with `done_min_criteria` items; statuses
ignore the emoji variation selector; duplicate ids, links to the wrong file and commits citing a
ticket outside the backlog are errors; `[commits].since` exempts pre-adoption history explicitly.
**Breaking:** the criteria heading must be exactly `## Acceptance Criteria` (a `###` heading or extra words no longer count).

Proportional ceremony (Organic Driven Development): `workflow_check.py classify` prints the minimum
lane of a change (quick, standard, deep) from its size, spread, sensitive paths, untested code,
binary files and changes to the workflow itself,
plus the questions that may raise it; the `change` skill and `/change` run only that lane's process;
`quick` commits need no ticket and are audited by `check --commits`. Tunable in `[lanes]`.

Review agents: `reviewer` and `security-reviewer` have no shell (read-only is enforced by their
tools, not requested in their prompt) and read the diff written by `review-plan --write-diff`;
`test-auditor` keeps a shell for mutation testing, works in a disposable worktree and is checked
with `workflow_check.py fingerprint` (a content hash) before and after. Cache writes refuse
symlinks, and diffs never run a repository's external diff or textconv driver.

Hardened before the first release against an untrusted target repository (path traversal through a
doctored manifest or through symlinks, execution of a script found in the target, configuration
injection through generator arguments); each attack is a regression test in `tests/test_security.py`.

Known limit: a repository's own git filters (`filter.<x>.clean`) still run when the checker diffs
(T1.7, pending).
