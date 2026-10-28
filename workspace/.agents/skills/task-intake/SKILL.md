---
name: task-intake
description: Brief and dispatch every substantive requested deliverable as a bounded Task in Fleet v2.1.0. Load whenever Slayer requests work or asks Mission Control to start a worker.
license: MIT
---

# Brief and dispatch a Task

VEGA is dispatch-only; `AGENTS.md` says what goes to a worker. This skill turns
a request into a worker brief and a `fleet/v1alpha1` Task. Run
`fleet apply --help` and `fleet version --json` first. Every command uses
Mission Control's exact configuration, `fleet --config PATH`, never a guessed
default store, and every brief repeats that path.

## 1. Shape the work

Name the concrete result, the repository and base if any, the checks that prove
it and exactly what Slayer authorized. Give each Task one result and one
owner. Prepare a separate existing absolute workspace on the target host: a Task
does not create a checkout or isolate files. Work without a repository still
gets an isolated directory holding only its inputs and outputs. Read only the
target repository instructions needed to pick the harness and the checks, and
verify that harness is installed and authenticated. Choose a unique lowercase
DNS-like Task name.

## 2. Write the brief

The worker shares no context with you or with other workers and reads its brief
once. Write it from scratch under these five headings, in order:

| Heading | Contents |
| --- | --- |
| `## Request` | Slayer's words, quoted verbatim, so the worker can check your reading against the source. |
| `## Goal` | The outcome, plus each task-specific fact the worker cannot read from the repository: repository, base or commit, prepared workspace, state seen at routing marked as a snapshot to confirm. |
| `## Constraints` | What it must not do, each with the failure it prevents, and the authorization limit. |
| `## Coordination` | Other Tasks it could collide with or wait on, and what to do about each; `None.` when there are none. |
| `## Done means` | The artifact and checks that end the Task, then the exact Fleet commands to record its result. |

- Keep every measured fact: commits, URLs, paths, counts, exact errors and the
  past failure behind a constraint. Cut persuasion and background the worker
  cannot act on.
- Do not retype standing policy the worker already reads: the target
  repository's instructions and gate, or Slayer's global agent rules. Tell it
  which files to read; a retyped copy drifts.
- Coordination holds only what the worker can act on. Your queue, other users'
  work and the order of later Tasks stay with you.
- Select the harness and model in the Task spec or a TaskConfig, not in prose.
- For an implementation, require the repository's tests and gate in Done means;
  for a reported bug, a failing end-to-end reproducer before the fix. For a
  review, name the exact commit and base and the outcome rule.
- Include the forge rules below only when opening a change is authorized.

Example brief for an authorized draft pull request:

```markdown
## Request
"Logins from the mobile app land on the home page instead of where they started. Fix it and open a draft PR."

## Goal
Make a mobile login return to the page it started from. The prepared worktree is /absolute/path/to/prepared-workspace, branch fix-login-redirect from the repository's main branch. At routing, the issue says the `next` parameter is lost on the mobile sign-in route; confirm current behavior before relying on it.

## Constraints
- Write a failing end-to-end reproducer before changing code, so the fix is shown to cover the reported route.
- Change only redirect handling; report other defects found instead of fixing them.
- A draft pull request is authorized. Marking it ready, merging and deploying are not.

## Coordination
None.

## Done means
The repository's required checks pass and a draft pull request holds the reproducer and fix. Open it as a draft, declare it at once with `fleet --config /absolute/path/to/fleet.toml declare fix-login-redirect --change-request URL`, and end every forge post with `<!-- fleet:worker <task uid> -->` on its own line, taking the uid from `fleet --config /absolute/path/to/fleet.toml get task fix-login-redirect`. Then record your result with that Task's `status.brief.generation`: `fleet --config /absolute/path/to/fleet.toml result fix-login-redirect --generation GENERATION --outcome OUTCOME --summary SUMMARY --artifact URL`.
```

Serialize the brief into the Task with a JSON serializer, never by hand:

```json
{
  "apiVersion": "fleet/v1alpha1",
  "kind": "Task",
  "metadata": {"name": "fix-login-redirect"},
  "spec": {
    "harness": "codex",
    "host": "local",
    "brief": "<the brief above>",
    "workspace": {"dir": "/absolute/path/to/prepared-workspace"},
    "dispatch": false
  }
}
```

## 3. Changes on a forge

When opening a change is authorized, the brief requires three rules: open every
change as a draft; run `fleet declare TASK --change-request URL` immediately
after opening it; end every forge post with `<!-- fleet:worker <task uid> -->`
on its own line, the uid from `fleet get task TASK`. Fleet follows only declared
changes, never marks ready a change opened ready, and relays an unmarked post
back as feedback. Name the repository's publishing skill, or the installed
publish skill if it has none. Workers do not merge.

A pull or merge request deliverable is done only with a real declared URL on the
requested base and the checks, CI and review required by Slayer or the repository
for that delivery stage; a local commit or blocked gate is not completion. A
draft-only deliverable may conclude after its declared URL and draft-stage gates
while Fleet keeps following the change. Declaration needs a delivered brief and a
configured forge host; it does not conclude the Task, and a result does not end
forge following: feedback arrives through the inbox. Do not add publication to
Tasks whose requested result does not include it.

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
    "brief": "## Request\n\"Review the open parser change.\"\n\n## Goal\nReview the commit checked out in the prepared workspace against its base.\n\n## Constraints\nReview only: do not edit, push or post.\n\n## Coordination\nNone.\n\n## Done means\nFindings with file and line, recorded with `fleet --config /absolute/path/to/fleet.toml result configured-review --generation GENERATION --outcome OUTCOME --summary SUMMARY`.",
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

If the engine, authentication, resources or another prerequisite blocks dispatch,
report that exact blocker and create a bounded recovery Task when possible. If no
dispatch is possible, say so plainly. Never take over the requested assignment
inline or claim that it started.

Only `dispatch` and `forge` are mutable in an existing Task spec. A new request
needs a new Task. Do not supply status, uid, generation or ownerReferences on create.
Setting dispatch false does not stop an already spawned session. Do not delete
another worker's Task as a retry strategy or treat an ambiguous runtime probe as
permission to spawn a replacement.
