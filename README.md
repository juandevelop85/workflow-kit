# workflow-kit

A portable kit for **ticket-driven development with AI coding agents**: tickets as the contract,
a skill that runs them end to end, independent reviewer agents, and a checker that turns the written
rules into checks. It is stack-agnostic and product-agnostic.

> **The human governs, the agent executes, the repository remembers.**

- **Method:** [`docs/method.md`](docs/method.md)
- **Adopt it (one page):** [`docs/adoption.md`](docs/adoption.md)
- **Configuration reference:** [`docs/configuration.md`](docs/configuration.md)

## What is inside

```text
core/                 the installable, versioned core
  skills/             ticket-author, ticket-runner, quality-gate
  agents/             reviewer, test-auditor, security-reviewer
  commands/           /ticket-new /ticket-run /ticket-review /quality-gate /ticket-status /workflow-init
  scripts/            workflow_check.py (the checker), workflow_init.py (project-layer generator)
  presets/            rust, node, python
  templates/          ticket, backlog, rules, threat model, agent memory, config
install.py            install / update / status
tests/                the kit's own tests, with fixtures for three stacks
```

## Quick start

```bash
# 1. Install the core into your repository
python3 install.py install --target /path/to/your/repo --stack python

# 2. Check that it works
python3 /path/to/your/repo/.agents/scripts/workflow_check.py
```

Requires Python 3.11+ and git; the kit itself uses only the standard library. The quality gates,
however, run your stack's own tools (`cargo`, `npm`, `ruff` and `pytest`...), which must be installed
in the project.

### Commands

| Command | What it does |
| :--- | :--- |
| `install.py install --target DIR [--stack S] [--name N] [--force]` | Copies the core into `DIR/.agents/`, links it from `.claude/` and creates the project layer (never overwrites existing files). |
| `install.py update --target DIR [--force]` | Replaces core files you did not modify; reports the ones you edited as conflicts. |
| `install.py status --target DIR` | Shows the installed version and which core files you changed or are missing. |

### Options of `install`

| Option | Default | Meaning |
| :--- | :--- | :--- |
| `--target DIR` | required | Repository to install into. |
| `--stack rust\|node\|python\|none` | `none` | Stack preset. Sets `[gates].preset` in `.agents/workflow.toml`; see below. |
| `--name NAME` | directory name | Project name written to `workflow.toml`. |
| `--force` | off | Overwrite core files you modified locally. |

### What `--stack` does

It picks a **preset** (`core/presets/<stack>.toml`) that defines two things, and nothing else (skills,
agents and commands are the same for every stack):

1. **The quality gates** that `/quality-gate` runs.
2. **Which files count towards the size limit** (and which folders are ignored).

| Stack | Gates | Size is measured on | Ignored |
| :--- | :--- | :--- | :--- |
| `rust` | `cargo fmt --check`, `cargo clippy -D warnings`, `cargo test` | `*.rs` | `target/` |
| `node` | `npm run lint`, `npm run typecheck` (both only if the script exists), `npm test` | `*.js *.jsx *.ts *.tsx *.mjs *.cjs` | `node_modules/`, `dist/`, `build/`, `.next/`, `coverage/` |
| `python` | `ruff check`, `ruff format --check`, `pytest` | `*.py` | `.venv/`, `venv/`, `__pycache__/`, `build/`, `dist/`, `.tox/` |
| `none` | no gates | per `workflow.toml` | |

With `none` you can still use tickets and the checker, and define your own gates in `workflow.toml`.
Use other tools by overriding a gate there; see [`docs/configuration.md`](docs/configuration.md).

### After installing

1. Fill in `.agents/rules/project.md`, `.agents/security-model.md` and `[sensitive].globs` in
   `.agents/workflow.toml`: only you know them. See [`docs/adoption.md`](docs/adoption.md).
2. In Claude Code, work with tickets:

```text
/ticket-new <idea>     write a ticket
/ticket-run <ID>       implement it end to end (gates + independent review)
/ticket-review <ID>    review it again on demand
/ticket-status         see the backlog
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Status

Version in [`VERSION`](VERSION); changes in [`CHANGELOG.md`](CHANGELOG.md). **Not yet validated in a
real project of another stack**: the pilot is pending, and a parametrisation nobody asked for there
does not belong in the core. Support for coding agents other than Claude Code is **untested**.
No licence has been chosen yet.
