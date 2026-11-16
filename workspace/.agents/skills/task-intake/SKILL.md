---
name: task-intake
description: Dispatch every substantive requested deliverable as a bounded Task that reports back into Mission Control's inbox. Load whenever a user requests work or asks Mission Control to start a worker.
license: MIT
---

# Create a Task

VEGA is dispatch-only: every substantive requested deliverable belongs to a
worker Task, however short, read-only or urgent. A request without a repository
still gets one owner, a concrete result and a workspace of its own.
Acknowledgement, clarification, dispatch itself and routine status need no Task.

Every `fleet` command reads `FLEET_CONFIG`. Read `fleet --help` or a
subcommand's help only when a command is refused.

## Prepare

Confirm the repository when one exists, the intended result, the permissions
and the checks. Read the status digest first: a follow-up on a live or
concluded Task's deliverable is an amendment, and another Task may already work
in the same repository (see Follow-ups and overlapping work). Read only the
repository instructions needed to brief the worker. Choose a unique lowercase
DNS-like Task name that the Board has not seen either, since milestones are
keyed by name: pick another when
`fleet event list --correlation NAME --after N --limit 1 --json` lists an event,
with N 0. An `expired` answer means listing again with N one below its
`oldest`; `Board/shared not found` is no conflict, but report it.

Record the user's ordering and limits on the Tasks, not in your memory:

- Serial work: create every Task in the lane now. Dispatch the first; create
  each later one with `dispatch` false and label `vega.fleet.dev/after` naming
  its predecessor. Parallel lanes are Tasks without `after`. Skipped work gets
  no Task.
- Limits such as `draft-only no-merge`: label `vega.fleet.dev/limits` and state
  them in the brief.
- A decision only the user can make before the work starts: create the Task
  with `dispatch` false and label `vega.fleet.dev/needs`, then ask.
- Label `vega.fleet.dev/request` with the request in a few words.

status-digest shows these labels and how to change them.

## Workspace

`spec.workspace` is a list of URLs. The runtime makes one directory per URL
before the session starts; the worker starts in the first.

```text
git+https://forge.example/acme/app.git        repository, default branch
  └─ branch <task name>.<task uid>            cut by the runtime, never by you
       └─ worktree for this Task alone        the worker works and commits here
```

- A repository is a `git+` URL. For a Task on this machine, prefer the
  repository's local checkout when `private/INSTRUCTIONS.md` maps it to one:
  write `git+file:///abs/checkout`. Otherwise write `git+https://…`, or
  `git+ssh://…`. A local checkout skips the clone: the runtime fetches its
  `origin` and cuts the Task's branch in it, where the branch stays.
- The base is the URL's `#ref`, else the remote's default branch as a fetch
  just before shows it; an unreachable remote leaves the refs already there. On a `git+file` URL a ref names the checkout's own
  branch first, which may be stale: write `#origin/main` for the upstream's.
  `?branch=NAME` names the branch, only when the user asks for one. Never
  clone, add a worktree or prepare a checkout yourself.
- A mapped checkout has a working tree and its `origin` is the repository on
  the forge; a bare or missing one falls back to `git+https`. Its path stays in
  the manifest: never put it in public content.
- Several URLs give one directory each under the same Task. Say in the brief
  which repository each part of the work belongs to.
- Work with no repository: ask the user for a repository, or for an existing
  absolute directory, written `file:///abs/dir`. Fleet uses that directory as it
  is and isolates nothing, so never give one to two live Tasks.
- Deleting the Task removes its worktree. The branch stays, and uncommitted
  work goes to `refs/fleet/preserved/<key>/<name>` in the repository. Brief
  workers to push, declare or record anything others need before they record
  their result.

A Task waiting with `WorkspaceUnsupported` named a URL its runtime cannot make:
fix the URL in a new Task.

## Manifest

Write the manifest with a JSON serializer to `dispatch/NAME.json` in this
workspace, replacing every example value, and never echo the brief in a reply.
The file is only input to `fleet apply`, which reads JSON; Fleet keeps the
Task, so the file is safe to delete.

- The two `gateway.fleet.dev/parent` labels make Fleet relay the worker's
  Questions, declared changes and result into VEGA's own inbox, which is how
  Mission Control hears back without waiting. `VEGA_UID` is
  `fleet get task vega | jq -r .metadata.uid`.
- `harness` is Task `vega`'s `spec.harness` unless the user or the repository
  asks for another.
- `env.FLEET_CONFIG` is the value of your own `FLEET_CONFIG`, so the worker's
  `fleet` commands reach this store.
- Omit `host` to run on this machine. Another place is `<runtime>/<place>`,
  from `fleet runtime places`, only when the user asks for it.

```json
{
  "apiVersion": "fleet/v1alpha1",
  "kind": "Task",
  "metadata": {
    "name": "inspect-project",
    "labels": {
      "gateway.fleet.dev/parent": "vega",
      "gateway.fleet.dev/parent-uid": "VEGA_UID",
      "vega.fleet.dev/request": "inspect the project",
      "vega.fleet.dev/limits": "no-publish"
    }
  },
  "spec": {
    "harness": "codex",
    "brief": "Inspect the repository instructions and report the requested finding. Run its required checks. Do not publish without authorization. Publish each milestone to the shared Board, best effort: fleet event publish --type task.MILESTONE --subject acme/app --correlation inspect-project --key inspect-project-MILESTONE --data '{}'. Ask Mission Control by declaring a Question and wait for the answer in your inbox. Record the result through fleet result using the generation of the delivered brief.",
    "workspace": ["git+https://forge.example/acme/app.git"],
    "env": {"FLEET_CONFIG": "/path/from/your/FLEET_CONFIG"},
    "dispatch": false
  }
}
```

Every brief names the concrete result, the checks, the limits, and how to ask:
`fleet declare NAME --json '{"kind":"Question","id":"q1","text":"..."}'`, then
wait for the answer in the inbox. For a reported issue, the brief requires a
failing end-to-end reproducer first, and an implementation brief requires the
repository's tests and publishing gate. Every brief also carries the Board
milestones lines below.

## Board milestones

Workers publish their milestones to the `shared` Board, which status-digest
reads as the timeline. Copy these lines into every brief, with NAME the Task
and SUBJECT its repository or area:

```text
Publish each milestone to the shared Board, best effort: a failed publish never blocks the work.
MILESTONE is started, question, pr.opened, ci.green or result; add -2, -3 to the key when one repeats.
Data is {} or small, such as {"url":"…"} or {"outcome":"shipped"}; never secrets or brief text.
fleet event publish --type task.MILESTONE --subject SUBJECT --correlation NAME --key NAME-MILESTONE --data '{}'
```

A publish retried under its key appends nothing. An event is the worker's
claim: Questions, changes and results still reach you through Fleet.

## Forge worker brief

When opening a change is authorized, put these rules in the brief:
open every change as a draft; run `fleet declare TASK --change-request URL`
immediately after opening it; end every forge post with `<!-- fleet:worker <task uid> -->`
on its own line, the uid from `fleet get task TASK`. Name the repository's
publishing skill, or the installed publish skill if it has none. A Task does not
authorize publication, merging or deployment, and workers do not merge.

Fleet follows a change only on a forge listed under `[forge.hosts]` in the
config; it refuses to declare any other. Report that to the user; never edit
the config yourself.

A pull or merge request deliverable is done only once the real change URL is
declared and the base, checks, CI and review required by the user or repository
for that delivery stage pass; a local commit or a blocked required gate is not
completion. A draft-only deliverable may conclude after its declared URL and
draft-stage gates while Fleet keeps following the change. Do not impose
publication on Tasks whose requested result does not include it. Declaring
concludes nothing; feedback reaches the worker's inbox, and Fleet follows only
declared changes.

## Shared defaults

A TaskConfig holds defaults several Tasks share, and an EnvProvider supplies
environment values. Both are JSON resources applied like a Task: the provider,
then the config, then the Task.

```json
{
  "apiVersion": "fleet/v1alpha1",
  "kind": "EnvProvider",
  "metadata": {"name": "project-env"},
  "spec": {"data": {"PROJECT_MODE": "review"}}
}
```

```json
{
  "apiVersion": "fleet/v1alpha1",
  "kind": "TaskConfig",
  "metadata": {"name": "reviewer"},
  "spec": {
    "harness": "codex",
    "envFrom": [{"name": "project-env"}],
    "env": {"PROJECT_MODE": "careful"}
  }
}
```

A Task names it with `"configRef": {"name": "reviewer"}`; its own fields win.
Fleet freezes the resolved values before the first launch, so a later edit
affects only later Tasks. Literal values are readable by anyone who reads the
store: keep credentials in the user's own sources, and read Fleet's TaskConfig
and EnvProvider documentation before going beyond these examples.

## Apply and dispatch

1. Check `fleet get task NAME` first. If it exists, inspect it; never reuse a
   name for a different request. Only exit code 3 means not found.
2. Run `fleet apply -f dispatch/NAME.json --create-only` to create the
   suspended Task.
3. When its prerequisites are met, the work is authorized and it is not held,
   set only `spec.dispatch` to `true` in that file and run
   `fleet apply -f dispatch/NAME.json`.
4. Reply at once with the `Dispatched:` line. Never wait for the spawn, poll
   `fleet list` or read the result in the same turn: the running `fleet up`
   reconciles it and Fleet delivers the worker's messages into your session.

If the engine, authentication, resources or another prerequisite blocks dispatch,
report that exact blocker and create a bounded recovery Task when possible. If no
dispatch is possible, say so plainly. Never take over the requested assignment
inline or claim that it started.

## Follow-ups and overlapping work

The digest's `ws:` fields show which Tasks share a repository.

- More context, an added ask or constraint, or a correction for an existing
  Task's deliverable is an amendment, not a new Task:

  ```sh
  fleet amend NAME --text "Also cover the migration notes." --reason "the user asked"
  ```

  The worker keeps its session, worktree, branch and declared changes. A
  delivered amendment re-opens a Concluded Task, and the worker's next result
  names the new generation. Fleet refuses an amend for a Stalled or deleting
  Task or a full inbox. It accepts one while the worker is gone, but it waits
  for a session Fleet never respawns, so follow up on a Task with
  `attention:WorkerGone` with a new Task instead.
  A retry passes `--if-generation N`, where N is `metadata.generation` read
  before the first try; exit code 5 means the Task moved on, so re-read it
  rather than assume the amend landed. Update the Task's `limits` label when
  the user changes them.
- Amendments only add. A wrong brief, or another deliverable, repository,
  harness or place, needs a new Task. `fleet send` is conversation: it changes
  no contract and re-opens nothing.
- Live Tasks on one repository get separate worktrees and branches but can
  conflict when merged. When their work overlaps, hold the later one `after`
  the earlier, or ask the user; otherwise run them in parallel.

Only `dispatch`, `forge` and labels change on an existing Task. Do not supply
status, uid or generation on create. Setting dispatch false does not stop an
already spawned session. Do not delete another worker's Task as a retry
strategy or treat an unknown runtime answer as permission to spawn a
replacement. A held Task that never spawned may be deleted and recreated when
its brief must change.
