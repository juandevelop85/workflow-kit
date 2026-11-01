# workflow-kit · Guide for coding agents

This repository is the workflow kit, and it uses its own workflow.

- **Tickets:** `docs/tickets/`. The backlog is `docs/tickets/README.md`.
- **Rules:** `.agents/rules/project.md`. Read it before working.
- **Configuration:** `.agents/workflow.toml`.
- **The product** lives in `core/`; `.agents/` links to it, so edit `core/`, never `.agents/`.

## Commands

- `/ticket-new <idea>`, `/ticket-run <ID>`, `/ticket-review [ID]`, `/quality-gate`, `/ticket-status`.
- Gates: `python3 .agents/scripts/workflow_check.py gates --run`.
- Rules: `python3 .agents/scripts/workflow_check.py --commits 20`.
