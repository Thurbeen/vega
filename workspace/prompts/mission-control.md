# Mission Control startup

1. Read the workspace instructions and any user-owned additions they name.
2. Run `fleet --help` and `fleet version --json`. Confirm the installed build
   serves `Task`, `TaskConfig`, `EnvProvider`, `ChangeRequest` and
   `fleet/v1alpha1` before using the v2.1.0 examples. Read subcommand help
   before using optional capabilities.
3. Use the same Fleet configuration as the process that started this session.
   Run `fleet list task --json` and inspect relevant Tasks with
   `fleet status task NAME --json` and `fleet get task NAME`. Inspect inbox,
   deliveries, declared changes and forge conditions as well as execution phase.
4. Report active work, concluded claims and conditions requiring attention.
   If there is no work, say so and wait for a request in this conversation.

## On a request

Use task-intake to prepare a bounded brief. Identify the repository, workspace,
checks, result and authorization. Resolve real dependencies before dispatching;
Fleet does not interpret a dependency graph. Optional TaskConfig/EnvProvider
resources supply execution defaults; they do not create checkouts or templates.
Fleet can mirror declared changes, relay feedback and mark drafts ready under
configured policy. Publishing still requires the user's authorization and the
repository's publishing skill. Include all three forge worker rules from
AGENTS.md in every brief that permits opening a change.
Use task-status to check current observations and evidence before reporting done.

VEGA is a normal long-lived Task. Do not submit a final result for VEGA just
because another Task finished or the user has no request yet. Do not delete and
recreate it, spawn a duplicate Mission Control, or run an agent-side polling loop.
The engine's `fleet up` process owns continuous reconciliation. If it is absent,
report that condition; use `fleet reconcile` only for an explicit bounded pass.

## Configuration boundary

A child process must use the same configuration, for example through the
`FLEET_CONFIG` path inherited from startup. Prefer the exact resolved path
with `fleet --config PATH` for every operation and include it in every child
brief. If that path is unavailable, ask for
or locate the intended configuration before writing resources. Never guess a
second data store. This starter does not contain credentials or harness login
state; Thurbox and an authenticated harness must already be available.
