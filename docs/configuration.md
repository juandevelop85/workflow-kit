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
| `[tickets].done_requires_section` | `Acceptance Criteria` | A done ticket must contain it (`""` disables). |
| `[tickets.statuses]` | ✅ 🔄 ⏳ ⏸️ 📝 | Symbols for `done`, `in_progress`, `pending`, `deferred`, `proposed`. |
| `[commits].pattern` | `^[a-z]+\([a-z0-9_-]+\): T\d+\.\d+ - .+` | Commit subject format (checked with `--commits N`). |
| `[commits].format_hint` | `<type>(<area>): <TID> - <title>` | Shown in the error message. |
| `[size].warn_lines` / `error_lines` | 800 / 1500 | Warn / fail above these. |
| `[size].include` / `exclude` | from the preset | Globs (`**` crosses directories). `.agents/` and `.claude/` are always excluded. |
| `[size].baseline` | `.agents/baseline.txt` | `<path> <max lines>` per line: acknowledged debt that may only shrink. |
| `[gates].preset` | `none` | `rust`, `node`, `python` or `none`. |
| `[gates.override.<name>]` | | `command = "…"` or `enabled = false`. |
| `[[gates.extra]]` | | `name` and `command` of an extra gate. |
| `[sensitive].globs` | `[]` | Paths that require a security review. |
| `[checks].backlog` / `honest_closing` / `sizes` | `true` | Switch a check off (it is then reported on every run). |

## Subcommands

```bash
python3 .agents/scripts/workflow_check.py [check] [--commits N]   # exit 1 on any error
python3 .agents/scripts/workflow_check.py gates [--json]          # name<TAB>command per gate
python3 .agents/scripts/workflow_check.py sensitive [--base REF] [paths…]
```

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
