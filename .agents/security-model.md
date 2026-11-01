# workflow-kit · Threat model

## What we protect

The repository where the kit is installed (its files outside `.agents/`, its git configuration) and
the machine of the person who runs `install.py`, `workflow_init.py` or `workflow_check.py`.

## Who attacks and what they control

A hostile **target repository**: its manifest, symlinks, `workflow.toml`, ticket files and git
configuration. Arguments of the generator typed by a person who copied them from elsewhere.

## Trust boundaries

- `install.py update/status` read the target's manifest: every path is validated (`safe_dest`).
- `workflow_init.py` writes files from CLI arguments: every value is escaped or validated.
- `workflow_check.py` runs git with `core.fsmonitor` off; `gates --run` executes the commands of the
  project's own `workflow.toml` through the shell, like a Makefile: it is run only on trusted repos.

## Surfaces that always need a security review

Mirror of `[sensitive].globs`: the installer and the generator (they write into the target), the
presets (they define shell commands) and the review agents (their tool list is their sandbox).
