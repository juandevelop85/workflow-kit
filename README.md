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
python3 install.py install --target /path/to/your/repo --stack python
python3 /path/to/your/repo/.agents/scripts/workflow_check.py
```

Requires Python 3.11+ and git. Standard library only.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Status

Version in [`VERSION`](VERSION); changes in [`CHANGELOG.md`](CHANGELOG.md). **Not yet validated in a
real project of another stack**: the pilot is pending, and a parametrisation nobody asked for there
does not belong in the core. Support for coding agents other than Claude Code is **untested**.
No licence has been chosen yet.
