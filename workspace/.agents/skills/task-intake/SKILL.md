---
name: task-intake
description: Create or dispatch bounded work as a Task in Fleet v2.1.0. Load when a user requests new work or asks Mission Control to start a worker.
license: MIT
---

# Create a Task

Read workspace and target-repository instructions first. Run `fleet apply --help`
and `fleet version --json`; this skill targets `fleet/v1alpha1`, kind `Task`.
Use the same configuration as Mission Control, never a guessed default store.
Every command below assumes that exact path in `FLEET_CONFIG`; use
`fleet --config PATH` explicitly when inheritance is uncertain. Include the
resolved path in each child brief and require it for every Fleet operation.

## Prepare

Confirm the request's repository, intended result, necessary permissions and
checks. Prepare a separate existing absolute workspace directory on the target
host. A Task does not create a checkout or isolate files for you. Read the
repository's instructions to choose the harness; verify it is installed and
already authenticated. Choose a unique lowercase DNS-like Task name.

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
    "workspace": {"dir": "/absolute/path/to/prepared-workspace"},
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

Declaration requires a delivered brief and configured forge host, and ensures a
ChangeRequest mirror while recording the declaration on the Task. It does not
conclude the Task. Follow feedback through its inbox; a result does not end forge
following or release the session. Fleet follows only declared changes, never
marks ready a change opened ready, and relays unmarked posts back as feedback.

## Optional execution defaults (Fleet v2.1.0)

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
    "workspace": {"dir": "/absolute/path/to/prepared-workspace"},
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

Only `dispatch` and `forge` are mutable in an existing Task spec. A new request
needs a new Task. Do not supply status, uid, generation or ownerReferences on create.
Setting dispatch false does not stop an already spawned session. Do not delete
another worker's Task as a retry strategy or treat an ambiguous runtime probe as
permission to spawn a replacement.
