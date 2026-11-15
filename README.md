# VEGA

VEGA is a Mission Control for [Fleet](https://github.com/Thurbeen/thurbox/tree/main/docs/fleet):
one Fleet Task whose agent only dispatches work to worker Tasks, follows them
and reports back. It is instructions, prompts and three agent skills; Fleet
runs it like any other Task.

## Install

You need Fleet v3 (with thurbox, or the fleet-only install), `jq`, and a
coding agent on PATH that you have logged in to. Then:

```sh
git clone https://github.com/Thurbeen/vega
cd vega
./install.sh
```

On Windows, in PowerShell 7: `./install.ps1`.

The installer:

1. checks that `fleet` is Fleet v3 and that `jq` is on PATH;
2. runs `fleet init` when there is no Fleet config yet; an existing one is kept;
3. picks the agent: `--harness NAME`, else the first one `fleet doctor` finds
   on PATH;
4. adds `[forge.hosts]` for `github.com` and `gitlab.com` when the config has
   none and `gh` or `glab` is on PATH, so workers can declare their changes;
5. applies the Task `vega`, which works in this checkout's `workspace/`.

It installs into `--config PATH`, else `FLEET_CONFIG`, else Fleet's per-user
config. Run it again at any time: it changes only what is missing.

Talk to VEGA in thurbox, where it is the session `vega`, or queue a message
with `fleet send vega "MESSAGE"`. Fleet must be running: thurbox starts
`fleet up`; with the fleet-only install, run `fleet up` yourself.

Update with `git pull`: VEGA reads its instructions from this checkout.
Uninstall with `./install.sh --uninstall` (`./install.ps1 -Uninstall`). It
deletes the Task `vega`; its workers and this checkout stay. To change the
agent, uninstall, then install with another `--harness`.

## How it works

```text
you ──request──▶ VEGA ──fleet apply (parent labels)──▶ Fleet ──▶ worker Task
 ▲                ▲                                       │       (own worktree)
 └──reply─────────┴──── Questions, changes, results ◀─────┘
```

- **Dispatch-only.** Every deliverable, however small, runs in a worker Task
  with its own workspace. VEGA routes, steers, checks recorded evidence and
  reports. Its rules are in [workspace/AGENTS.md](workspace/AGENTS.md).
- **Never waits.** Workers carry `gateway.fleet.dev/parent` labels, so Fleet
  relays their Questions, declared changes and results into VEGA's inbox.
- **Fleet is the memory.** Order, limits and pending decisions are
  `vega.fleet.dev/*` labels on the Tasks; held work has `dispatch` false. A
  cleared or restarted VEGA rebuilds its state from the
  [status digest](workspace/.agents/skills/status-digest/SKILL.md).
- **Workspaces are URLs.** A worker names `git+https://…` repositories; the
  runtime cuts a worktree on the branch `<task name>.<task uid>` from the URL's
  `#ref` or the remote's default branch. Deleting the Task keeps the branch and
  commits uncommitted work to `refs/fleet/preserved/…`. See
  [task-intake](workspace/.agents/skills/task-intake/SKILL.md).
- **Forge work.** An authorized worker opens a draft, declares it with
  `fleet declare TASK --change-request URL` and ends every post with
  `<!-- fleet:worker <task uid> -->`. Fleet follows the change and never
  merges. A Task grants no permission to publish.

## Files

| Path | What it is |
| --- | --- |
| `install.sh`, `install.ps1` | Install or uninstall VEGA |
| `tasks/vega.json` | The Task the installer applies, once it sets the agent, workspace and config |
| `workspace/AGENTS.md` | VEGA's rules |
| `workspace/prompts/mission-control.md` | Start-up, each turn, replies and re-hydration |
| `workspace/.agents/skills/task-intake/SKILL.md` | Create and dispatch a worker Task |
| `workspace/.agents/skills/task-status/SKILL.md` | One Task's state, steering and result checks |
| `workspace/.agents/skills/status-digest/SKILL.md` | One line per Task, and the labels that hold order and limits |

The skills are standard `SKILL.md` packages; `npx skills add . --list` lists
them. Installing the skills alone creates no Task.

Keep personal additions in `workspace/CUSTOM.md` or
`workspace/private/INSTRUCTIONS.md`; git ignores both. Never commit
credentials, Fleet stores or personal config here.

## Tests

Contributors need Python 3.11 or newer, `uv`, `jq` and a Fleet v3 binary:

```sh
FLEET_BIN=/path/to/fleet uv run --no-project python -m unittest discover -s tests -v
prek run --all-files
```

The tests install VEGA with both installers into a sandboxed HOME and a store
on Fleet's fake runtime, so no agent starts. The PowerShell tests run when
`pwsh` is on PATH. Then they run the commands the guidance ships: workers
report into VEGA's inbox, the digest rebuilds state, follow-ups amend, and
every example resource applies. They cannot prove a model obeys the prose.

## License

MIT, copyright 2026 Thurbeen.
