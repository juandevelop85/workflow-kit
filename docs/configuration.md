# `.agents/workflow.toml` reference

Every key has a default; a minimal file only needs `[gates].preset`. Unknown sections produce a
warning, invalid regular expressions an error. Switching a check or a gate off is allowed and is
**reported as a warning on every run**.

| Section / key | Default | Meaning |
| :--- | :--- | :--- |
| `[project].name` | | Project name (informational). |
| `[project].rules` | | Files the agents must read first. |
| `[project].security_model` | | The threat model read by the security reviewer. |
| `[project].language_policy` | | Free text: language of identifiers, comments, docs. |
| `[tickets].dir` | `docs/tickets` | Where tickets live. |
| `[tickets].backlog` | `<dir>/README.md` | The backlog table. |
| `[tickets].id_pattern` | `T\d+\.\d+` | Regex of a ticket id. |
| `[tickets].file_glob` | `T*.md` | Ticket file names. |
| `[tickets].header_status` | `^>\s*\*\*Status:\*\*\s*(.*)$` | The status line of a ticket. |
| `[tickets].done_requires_section` | `Acceptance Criteria` | A done ticket must have this `##` section (`""` disables). |
| `[tickets].done_min_criteria` | `1` | Items (`-`, `*`, `1.`) that section must list for the ticket to be done. |
| `[tickets.statuses]` | ✅ 🔄 ⏳ ⏸️ 📝 | Symbols for `done`, `in_progress`, `pending`, `deferred`, `proposed`. Compared without the emoji variation selector, so `⏸` equals `⏸️`. |
| `[commits].pattern` | `^[a-z]+\([a-z0-9_-]+\): (?:<id_pattern>) - .+` | Commit subject format (checked with `--commits N`); the default is built from `[tickets].id_pattern`. The ticket id a commit cites must be in the backlog. |
| `[commits].since` | | A ref: only commits after it are checked. Exempts, explicitly, the history from before the project adopted the kit. |
| `[commits].format_hint` | `<type>(<area>): <TID> - <title>` | Shown in the error message. |
| `[size].warn_lines` / `error_lines` | 800 / 1500 | Warn / fail above these. |
| `[size].include` / `exclude` | from the preset | Globs (`**` crosses directories). `.agents/` and `.claude/` are always excluded. |
| `[size].baseline` | `.agents/baseline.txt` | `<path> <max lines>` per line: acknowledged debt that may only shrink. |
| `[gates].preset` | `none` | `rust`, `node`, `python` or `none`. |
| `[gates.override.<name>]` | | `command = "…"` or `enabled = false`. |
| `[[gates.extra]]` | | `name` and `command` of an extra gate. |
| `[sensitive].globs` | `[]` | Paths that require a security review. |
| `[efficiency].light_max_lines` | `30` | A non-docs diff up to this size is self-reviewed, with no reviewer subagent. |
| `[efficiency].auditor_min_criteria` | `3` | `review-plan --ticket` adds `test-auditor` from this many acceptance criteria. |
| `[efficiency].gate_tail_lines` | `15` | Lines of a failing gate shown by `gates --run`. |
| `[efficiency].gate_timeout_seconds` | `1800` | A gate running longer is reported as failed. |
| `[efficiency].doc_globs` | `**/*.md`, `**/*.txt`, `docs/**` | A diff made only of these is "docs-only". |
| `[lanes].quick_max_lines` / `quick_max_files` | `40` / `5` | A change within both, with no sensitive path, can be quick. |
| `[lanes].quick_docs_max_lines` | `300` | The line limit of a quick change made only of prose (`[lanes].doc_globs`). |
| `[lanes].doc_globs` | `**/*.md`, `**/*.rst`, `**/*.adoc` | Prose for the lanes. Narrower than `[efficiency].doc_globs`: a `.txt` can be a dependency list. |
| `[lanes].process_globs` | `.agents/**`, `.claude/**`, `CLAUDE.md`, `AGENTS.md` | The workflow itself: a change here is at least standard, so no quick commit can loosen the rules. |
| `[lanes].untested_code_max_lines` | `5` | More lines of code than this, with no test file changed, make a change at least standard. |
| `[lanes].deep_min_lines` / `deep_min_files` | `400` / `15` | From either, a code change is deep (docs alone never are). |
| `[lanes].test_globs` | `tests/**`, `test/**`, `**/__tests__/**`, `**/test_*.py`, `**/*_test.*`, `**/*.test.*`, `**/*.spec.*` | What counts as a test file. |
| `[lanes].quick_pattern` | `^[a-z]+\([a-z0-9_-]+\): quick - .+` | Subject of a quick commit; `check --commits` verifies each one was within the quick limits. `""` turns the quick lane off. |
| `[checks].backlog` / `honest_closing` / `sizes` | `true` | Switch a check off (it is then reported on every run). |

## Subcommands

```bash
python3 .agents/scripts/workflow_check.py [check] [--commits N]   # exit 1 on any error
python3 .agents/scripts/workflow_check.py gates [--json]          # name<TAB>command per gate
python3 .agents/scripts/workflow_check.py sensitive [--base REF] [paths…]
python3 .agents/scripts/workflow_check.py context TID             # compact brief of one ticket
python3 .agents/scripts/workflow_check.py classify [--base REF] [--json]  # minimum lane of the change
python3 .agents/scripts/workflow_check.py review-plan [--ticket TID] [--base REF] [--json] [--write-diff]
python3 .agents/scripts/workflow_check.py fingerprint                # content hash of HEAD + working tree + untracked
python3 .agents/scripts/workflow_check.py gates --run [--tail N]  # PASS/FAIL per gate, full output in a log
```

Every subcommand takes `--root DIR` (default: the repository that contains the script); `--help`
lists them all.

- **Saving tokens** (see `[efficiency]`): `context` replaces reading the whole backlog and ticket,
  `review-plan` decides which review subagents are worth their cost for this diff, and `gates --run`
  keeps passing output out of the conversation.
- **Proportional ceremony** (see `[lanes]`): `classify` prints the minimum lane of the current change.
- **Review hand-off:** `review-plan --write-diff` writes `.agents/.cache/review/diff.patch` (what to
  review, with a header naming HEAD and the base) and `working.patch` (the part that applies on
  HEAD, for the test auditor's worktree); `fingerprint` hashes HEAD, the index, the working tree and
  the untracked files, so a change made there by an agent that can run code is visible (ignored files
and the inside of `.git` are not hashed).

Everything the checker writes goes under `.agents/.cache/`, which ignores itself in git; it refuses
to write through a symlink. Diffs never run the repository's external diff or textconv driver.
`gates --run` executes the commands of `workflow.toml` through the shell, exactly like running them
by hand: use it only on repositories you trust.

## Presets

A preset (`.agents/presets/<name>.toml`) is only a list of `[[gate]]` entries (`name`, `command`)
and the `[size]` globs to measure. It is selected with `[gates].preset`, which `install.py install
--stack <name>` writes for you. Add your own by dropping a file there; it is core, so a later
update may replace it: keep project-specific changes in `workflow.toml`.

| Preset | Gates (in order) | `[size].include` | `[size].exclude` |
| :--- | :--- | :--- | :--- |
| `rust` | `format`: `cargo fmt --all -- --check`<br>`lint`: `cargo clippy --workspace --all-targets -- -D warnings`<br>`test`: `cargo test --workspace` | `**/*.rs` | `**/target/**` |
| `node` | `lint`: `npm run lint --if-present`<br>`typecheck`: `npm run typecheck --if-present`<br>`test`: `npm test` | `**/*.js`, `**/*.jsx`, `**/*.ts`, `**/*.tsx`, `**/*.mjs`, `**/*.cjs` | `node_modules`, `dist`, `build`, `.next`, `coverage` |
| `python` | `lint`: `python3 -m ruff check .`<br>`format`: `python3 -m ruff format --check .`<br>`test`: `python3 -m pytest` | `**/*.py` | `.venv`, `venv`, `__pycache__`, `build`, `dist`, `.tox` |
| `none` | none | from `workflow.toml` | |

`python3 .agents/scripts/workflow_check.py gates` prints the gates actually resolved for the project.

### Using other tools

Override one gate, switch it off, or add another, without touching the preset:

```toml
[gates]
preset = "python"

[gates.override.lint]
command = "python3 -m flake8"

[gates.override.format]
enabled = false

[[gates.extra]]
name = "types"
command = "python3 -m mypy ."
```
