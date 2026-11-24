---
name: task-intake
description: Dispatch every substantive requested deliverable as a bounded Task that reports back into Mission Control's inbox. Load whenever a user requests work or asks Mission Control to start a worker.
license: MIT
---

# Create a Task

VEGA is dispatch-only: every substantive requested deliverable belongs to a
worker Task, however short, read-only or urgent. A request without a repository
still gets one owner, a concrete result and a workspace of its own.

## Prepare

Confirm the repository, the intended result, the permissions and the checks.
A follow-up on an existing Task's deliverable is an amendment (see Follow-ups).
Find the Tasks whose workspace, declared change or labels hold a text, such
as a repository path:

```sh
fleet list task --json | jq -r --arg q TEXT '.[] | select(.metadata.name != "vega") | select([(.spec.workspace // [])[], ((.status.declared // [])[] | .url // empty), ((.metadata.labels // {})[])] | any(contains($q))) | "\(.metadata.name) \(.status.phase // "-")"'
```

Choose a unique lowercase DNS-like name. Record order and limits on the
Tasks, not in your memory:

- Serial work, or heavy work one machine should run one at a time: create
  every Task now, the later ones held with `vega.fleet.dev/after` naming the
  predecessor. Fleet has no per-place concurrency cap; never cap with
  `fleet pause`, which a message undoes.
- A decision only the user can make first: hold the Task with
  `vega.fleet.dev/needs`, then ask.
- A recurring request is a Fleet CronTask, whose `historyLimit` deletes old
  runs. Its Tasks cannot carry the parent labels, so they report to no one;
  read Fleet's CronTask docs before writing one.

status-digest shows how to set a label.

## Workspace

`spec.workspace` is a list of URLs. The runtime makes one directory per URL
and a branch `<name>.<uid>` before the session starts; the worker starts in
the first. Never clone, add a worktree or prepare a checkout yourself.

- For a repository on this machine, prefer its local checkout when
  `private/INSTRUCTIONS.md` maps it to one: `git+file:///abs/checkout`, whose
  `origin` is the forge repository. The runtime fetches `origin` and cuts the
  branch there. A ref there names the checkout's own branch first, which may
  be stale: write `#origin/main` for the upstream's. Never put that path in
  public content.
- Otherwise write `git+https://…` or `git+ssh://…`. The base is the URL's
  `#ref`, else the remote's default branch. `?branch=NAME` only when the user
  asks for one.
- Several URLs give one directory each; say which part goes where.
- No repository: ask for one, or for an existing directory, `file:///abs/dir`.
  Fleet isolates nothing there, so never give it to two live Tasks.

A Task waiting with `WorkspaceUnsupported` named a URL its runtime cannot make:
fix the URL in a new Task.

## Brief and manifest

Write only the task-specific brief, as plain text, to `dispatch/NAME.txt`: the
concrete result, the repository and its checks, and the limits, including
whether opening a change is authorized. Never echo it in a reply. The build
below appends `briefs/worker.md` (how to ask, report and publish) and, when it
exists, the local `private/worker-rules.md`, such as machine build limits.
Never repeat those rules in the brief. The build needs bash or zsh; without
one, write the same manifest with a JSON serializer.

```sh
jq -n --arg name NAME --arg request "REQUEST" --arg limits "LIMITS" --argjson dispatch DISPATCH --rawfile brief dispatch/NAME.txt --rawfile rules briefs/worker.md --arg local "$(cat private/worker-rules.md 2>/dev/null)" --argjson vega "$(fleet get task vega)" '{apiVersion: "fleet/v1alpha1", kind: "Task", metadata: {name: $name, labels: {"gateway.fleet.dev/parent": "vega", "gateway.fleet.dev/parent-uid": $vega.metadata.uid, "vega.fleet.dev/request": $request, "vega.fleet.dev/limits": $limits}}, spec: {harness: $vega.spec.harness, env: {FLEET_CONFIG: $ENV.FLEET_CONFIG}, brief: ([$brief, ($rules + $local | gsub("TASK"; $name))] | join("")), workspace: $ARGS.positional, dispatch: $dispatch}}' --args URL > dispatch/NAME.json
```

`REQUEST` is the request in a few words, `LIMITS` the user's limits, such as
`draft-only no-merge`. `DISPATCH` is `true` unless the Task is held. `URL` is
one or more workspace URLs. The parent labels make Fleet relay the worker's
Questions and result into your inbox. Change `harness` or add `host`
(`<runtime>/<place>` from `fleet runtime places`) in the file only when the
user asks.

## Apply

1. If `fleet get task NAME` exits 0, the name is taken: inspect it, never
   reuse it for a different request. Only exit code 3 means not found.
2. `fleet apply -f dispatch/NAME.json --create-only`.
3. Reply at once with the `Dispatched:` line. Never wait for the spawn or
   poll: Fleet delivers the worker's messages into your session.

If the engine or a prerequisite blocks dispatch, report that exact blocker.
Never take over the assignment inline or claim that it started.

Fleet follows a change only on a forge listed under `[forge.hosts]` in the
config and refuses to declare any other. Report that to the user; never edit
the config yourself.

## Follow-ups

More context, an added ask or a correction for an existing Task's deliverable
is an amendment, not a new Task:

```sh
fleet amend NAME --text "Also cover the migration notes." --reason "the user asked"
```

The worker keeps its session, worktree, branch and changes; a delivered
amendment re-opens a Concluded Task. Fleet refuses one for a Stalled or
deleting Task or a full inbox. A Task with `attention:WorkerGone` is never
respawned: follow up with a new Task. A retry passes `--if-generation N`, N
read from `metadata.generation` before the first try; exit code 5 means the
Task moved on, so re-read it. Update the `limits` label when the user changes
them.

A wrong brief, or another deliverable, repository, harness or place, needs a
new Task. `fleet send` is conversation: it changes no contract. Live Tasks on
one repository can conflict when merged: when their work overlaps, hold the
later one `after` the earlier, or ask the user.

Only `dispatch`, `forge` and labels change on an existing Task. Setting
dispatch false does not stop a spawned session. Never delete another
worker's Task as a retry. A held Task that never spawned may be deleted and
recreated when its brief must change.
