# Adopting the kit in a project (one page)

You need Python 3.11+ and git. Nothing else is installed.

## 1. Install

From a clone of this kit:

```bash
python3 install.py install --target /path/to/your/repo --stack rust   # rust | node | python | none
```

This copies the **core** into `.agents/`, links it from `.claude/`, and creates the **project layer**
(only files that do not exist yet; it never overwrites):

| File | Purpose |
| :--- | :--- |
| `.agents/workflow.toml` | The configuration: tickets, commits, sizes, gates, sensitive surfaces |
| `.agents/rules/project.md` | Your rules and conventions (skeleton) |
| `.agents/security-model.md` | Your threat model (skeleton) |
| `.agents/baseline.txt` | Size debt you acknowledge (empty) |
| `docs/tickets/README.md` | The backlog |
| `CLAUDE.md`, `AGENTS.md` | Agent memory and guide |

## 2. Fill in what only you can

1. `.agents/rules/project.md`: the architecture and the conventions. The agents read it first.
2. `.agents/security-model.md`: what you protect and who attacks it.
3. `[sensitive].globs` in `.agents/workflow.toml`: the paths that must go through a security review.

## 3. Check it

```bash
python3 .agents/scripts/workflow_check.py          # backlog, closing, sizes
python3 .agents/scripts/workflow_check.py gates    # the gates it resolved for your stack
```

Existing history: `--commits N` checks that each commit cites a ticket of the backlog (a `quick`
commit cites none and is audited against the quick limits instead), so commits
from before the adoption would fail. Set `[commits].since = "<last commit before the kit>"` to
exempt them explicitly (CI needs the full history for that ref: `fetch-depth: 0`).

A fresh install passes with no errors. Run the gates yourself once to see they work for your project;
override a command in `workflow.toml` if your project uses other tools.

## 4. Work

In Claude Code, start any change with `/change <what>`: it classifies the change and runs only the
process its lane needs (a quick change needs no ticket). For planned work: `/ticket-new <idea>`, then
`/ticket-run <ID>`. Other agents can read `AGENTS.md` and
the files in `.agents/` directly; support for tools other than Claude Code has **not** been tested.

## 5. Update

```bash
python3 install.py update --target /path/to/your/repo
```

Core files you did not modify are replaced; any you edited are reported as conflicts and kept
(`--force` overwrites them). Your rules, configuration, threat model, baseline and tickets are never
touched. `python3 install.py status --target …` shows the installed version and what you changed.

## Security notes

- `install` and `update` refuse to write outside `.agents/` of the target: a symlinked `.agents`, a
  symlink in its subdirectories, absolute or `..` paths and doctored manifest entries are rejected
  or ignored. `install` always runs the kit's own `workflow_init.py`, never a copy found in the
  target.
- Values you pass to the generator (`--name`, `--language-policy`, `--tickets-dir`, `--id-prefix`)
  are validated or escaped, so they cannot add configuration.
- The checker writes only under `.agents/.cache/` and refuses to write through a symlink; its diffs
  never run a repository's external diff or textconv driver. The exception is `gates --run`, which
  executes the gate commands of `workflow.toml` through the shell: run it only on trusted
  repositories.
- **What is not protected:** the checker runs `git` and evaluates regular expressions from
  `workflow.toml` on the repository it is pointed at. It disables `core.fsmonitor`, but a hostile
  repository can still carry other configuration (a git `filter.<x>.clean` still runs on diff:
  T1.7 in the kit's backlog), and a pathological regular expression in its
  `workflow.toml` can make a check slow. Run the checker, like any tool that runs `git`, on
  repositories you trust. The core you install is code your agents will run: review a new kit
  version before updating.
