---
name: task-intake
description: Dispatch every substantive requested deliverable as a bounded Task in Fleet v2.2.1. Load whenever a user requests work or asks Mission Control to start a worker.
license: MIT
---

# Create a Task

VEGA is dispatch-only: every substantive requested deliverable belongs to a
worker Task, including design/planning/RFCs, implementation, bug fixing, tests,
research/investigation, reviews/audits, writing/reports/visual artifacts,
operational changes, maintenance, cleanup and other work. Shortness, read-only
scope, convenience or urgency is not an exception. A request without a repository
still gets one owner, a concrete result and an isolated workspace, which is a
`dir` only when the user explicitly asks for it.
Acknowledgement, clarification, dispatch itself and routine reporting of recorded
Task or change-request status do not need recursive Tasks.

Read workspace and target-repository instructions first. Run `fleet apply --help`
and `fleet version --json`; this skill targets `fleet/v1alpha1`, kind `Task`.
Use the same configuration as Mission Control, never a guessed default store.
Every command below assumes that exact path in `FLEET_CONFIG`; use
`fleet --config PATH` explicitly when inheritance is uncertain. Include the
resolved path in each child brief and require it for every Fleet operation.

## Prepare

Confirm the request's repository when one exists, intended result, necessary
permissions and checks. Retain the user's requested serial order, permitted
parallel lanes, skipped work and publication/merge/deploy limits in briefs and
follow-up steering. Read only the repository instructions necessary to choose
and brief the harness; verify it is installed and already authenticated. Choose
a unique lowercase DNS-like Task name.

Give each Task its own workspace, in exactly one of two forms:

- `{"repositories": [{"name", "url", "ref"}]}` for every Task. The runtime
  owns the checkout: it materializes the repositories for this Task alone, on a
  branch it names, and cleans them up when the Task's session is deleted. Never
  clone, add a worktree or prepare a checkout yourself, and never name a branch
  in the spec; Fleet has no branch, base, worktree or cleanup field.
  - Use the exact URL mapped in the Mission Control config's
    `runtime.repositories`, for example the canonical
    `https://github.com/OWNER/REPO`; Fleet matches it byte for byte, with no
    `.git` or SSH normalization. An unmapped URL fails the spawn (`SpawnRetry`,
    naming `runtime.repositories`), so add the mapping yourself before
    dispatching, never a checkout or a directory in its place:
    1. Find an existing source checkout on the target host whose `origin` is that
       URL (`git -C PATH remote get-url origin`) and which has no branch named
       after `runtime.keyPrefix`. If there is none, several, or the mapping needs
       anything else, ask the user and wait.
    2. Write a candidate copy of the config that adds
       `"URL" = "/absolute/source/path"` under `[runtime.repositories]` and
       changes nothing else. Check it against a new empty scratch directory
       outside Fleet's data, which opens the runtime the way `fleet up` does
       without touching the live store:
       `fleet --config CANDIDATE --data-dir EMPTY_DIR reconcile --max-passes 1 --json`.
       Only when it exits 0, keep the old config as a backup and put the
       candidate in its place; then remove the scratch directory. A
       `fleet list` passing proves nothing: it does not open the runtime.
    3. A running `fleet up` re-reads `runtime.repositories` before each sweep,
       so the mapping applies without a restart. A Task dispatched before it
       waits in Pending with `NeedsAttention`/`RepositoryUnmapped` and spawns
       within about 30 seconds of the mapping. An invalid edit leaves the last
       valid mapping in force. Other config settings still need a restart:
       leave those to the user, and never stop the engine yourself.
  - `ref` is optional and opaque to Fleet. Thurbox uses it as the base of a
    worktree created in the mapped source checkout, and it does not fetch, so
    name a remote-tracking ref such as `origin/main` and have the worker confirm
    its base against the forge before relying on it.
  - The first repository is the primary. With one repository the worker starts
    in its worktree; with several, Thurbox starts it in a directory holding one
    entry per repository, named after each source checkout's directory. Say in
    the brief which repository each part of the work belongs to.
  - The runtime's cleanup applies when the Task is deleted: with Thurbox's
    default `delete` it removes its worktrees, its branch and any unpushed
    commits. Brief workers to push, declare or record anything that must
    survive before they record their result.
- `{"dir": PATH}` only when the user explicitly asks for that exception, for
  example for work that has no repository: an existing absolute directory on the
  target host, outside Fleet's data directory and outside this workspace.
  Fleet neither creates nor isolates it, so never share one between live Tasks.
  Put only the Task's inputs and outputs in it; the worker makes any checkout it
  needs. Without that request, ask the user for a repository or a `dir`
  exception.
  Existing `dir` Tasks finish in place; their specs are immutable, so never
  rewrite or move them.

Write a JSON file using the following shape, replacing every example value.
Use a JSON serializer for values containing quotes, slashes or newlines.

```json
{
  "apiVersion": "fleet/v1alpha1",
  "kind": "Task",
  "metadata": {"name": "inspect-project"},
  "spec": {
    "harness": "codex",
    "host": "local",
    "brief": "Inspect the repository instructions and report the requested finding. Run its required checks. Do not publish without authorization. Record the result through fleet result using the generation of the delivered brief.",
    "workspace": {"repositories": [
      {"name": "app", "url": "https://forge.example/acme/app", "ref": "origin/main"}
    ]},
    "dispatch": false
  }
}
```

## Forge worker brief

When opening a change is authorized, include these rules in the brief and keep
these rules yourself: open every change as a draft; run
`fleet declare TASK --change-request URL` immediately after opening it; end every
forge post with `<!-- fleet:worker <task uid> -->` on its own line, obtaining the
uid from `fleet get task TASK`. Use the repository's publishing skill, or the
installed publish skill if the repository has none. Creating a Task does not
authorize publication, merging or deployment. Workers do not merge.

When an authorized deliverable is a pull or merge request, the worker is not
done until it has produced and declared the real change URL. Verify the requested
base plus the checks, CI and review evidence required by the user or repository
for that delivery stage; a local commit or blocked required gate is not completion.
A draft-only deliverable may conclude after the declared URL and its required
draft-stage gates, while Fleet continues following the change separately. Do not
impose publication on design, research, status or other Tasks whose requested
result does not include it.

Declaration requires a delivered brief and configured forge host, and ensures a
ChangeRequest mirror while recording the declaration on the Task. It does not
conclude the Task. Follow feedback through its inbox; a result does not end forge
following or release the session. Fleet follows only declared changes, never
marks ready a change opened ready, and relays unmarked posts back as feedback.

## Optional execution defaults

Keep the simple Task above unless reusable defaults are useful. TaskConfig and
EnvProvider are passive JSON resources, applied into the same store, separate
from native TOML. There is no `[taskConfig]` or `[envProvider]` TOML section.
Apply a provider, then its config, then the Task, for example:

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

```json
{
  "apiVersion": "fleet/v1alpha1",
  "kind": "Task",
  "metadata": {"name": "configured-review"},
  "spec": {
    "configRef": {"name": "reviewer"},
    "env": {"PROJECT_MODE": "focused"},
    "brief": "Review the repository instructions and report findings. Do not publish. Record your result with the delivered brief generation.",
    "workspace": {"repositories": [
      {"name": "app", "url": "https://forge.example/acme/app", "ref": "origin/main"}
    ]},
    "dispatch": false
  }
}
```

TaskConfig supports harness, host, model, ordered `envFrom` and string `env`.
Brief, workspace and outputs belong to each Task. Explicit Task execution fields
override defaults; `model: null` disables inheritance and explicit `host: "local"`
overrides a remote default. Model selection requires a matching native
`runtime.modelEnv` harness mapping; do not invent a Codex variable.

EnvProvider supports string `data` and ordered `sources`. A file source uses
`{"type":"file","path":"/absolute/private/env.json"}`. A command source uses
`type: "command"`, absolute `program`, optional `args`, absolute `cwd` and
`timeoutMs` from 1 through 15000. Both run/read on the manager, even for remote
Tasks; no implicit shell, PATH lookup or tilde expansion. Commands require a
manager lease above 20000 ms. Use only trusted helpers: FakeRuntime still runs
explicit provider commands.

File contents and command stdout must be one UTF-8 JSON object of string values,
at most 64 KiB. Environment names match `[A-Za-z_][A-Za-z0-9_]*`; case collisions
within a map and NUL values are refused. Later maps override case variants.
Precedence, lowest to highest: provider data, provider sources in order,
TaskConfig envFrom in order, TaskConfig env, Task env, runtime model selection.
Merged key/value bytes are also bounded to 64 KiB.

Literal env/data and source definitions are visible in resource reads; keep
credentials external and private. Successful resolution freezes privately
before launch; later config/provider edits affect future resolutions only.
Missing or invalid references/sources block launch observably; fix the input
and reconcile. Do not remove a frozen launch snapshot to refresh credentials.
Snapshots are plaintext: protect the store and backups. No background refresh
occurs. Config/provider specs are mutable; frozen Task execution is unchanged.

## Apply and dispatch

1. Check `fleet get task NAME` before applying. If it already exists, inspect
   it; never reuse a name for a different request. A failed read is not evidence
   that the Task is absent unless it explicitly reports not found.
2. Run `fleet apply -f task.json --json` to create the suspended Task.
3. When its prerequisites are satisfied and work is authorized, set only
   `spec.dispatch` to `true` in that same file and apply it again.
4. The engine's running `fleet up` reconciles it. For a deliberately bounded
   manual run, use `fleet reconcile --max-passes 10 --json`.
5. Use task-status to read the recorded result and verify the evidence.

If the engine, authentication, resources or another prerequisite blocks dispatch,
report that exact blocker and create a bounded recovery Task when possible. If no
dispatch is possible, say so plainly. Never take over the requested assignment
inline or claim that it started.

Only `dispatch` and `forge` are mutable in an existing Task spec. A new request
needs a new Task. Do not supply status, uid, generation or ownerReferences on create.
Setting dispatch false does not stop an already spawned session. Do not delete
another worker's Task as a retry strategy or treat an ambiguous runtime probe as
permission to spawn a replacement.
