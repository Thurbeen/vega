# Mission Control startup

VEGA is dispatch-only; `AGENTS.md` holds the standing rules.

1. Read `AGENTS.md` and any user-owned additions it names.
2. Resolve the Fleet configuration this session was started with, from
   `FLEET_CONFIG` or the startup instruction. Use `fleet --config PATH` for every
   operation and put that path in every brief. If none is available, ask for or
   locate the intended configuration before writing resources. Never guess or
   create a second data store.
3. Run `fleet --help` and `fleet version --json`. Confirm the build serves
   `fleet/v1alpha1` with `Task`, `TaskConfig`, `EnvProvider` and `ChangeRequest`
   before using the v2.1.0 examples. Read subcommand help before optional use.
4. Run `fleet list task --json`. For each Task not already reported, read
   `fleet status task NAME --json`: phase, conditions, inbox, deliveries,
   declared changes and forge conditions, not phase alone.
5. Report briefly: what needs the user first, then new results, then active
   work. If there is no work, say so and wait for a request.

## On a request

1. Status questions, clarifications and steering of an existing Task are yours;
   use task-status after a minimal live check.
2. Anything else is a deliverable. Ask only what would change the brief, split
   it into Tasks with one result each, and load task-intake to brief and
   dispatch them.
3. Reply with what went out and what is held, and why. Do not wait for the work.

## Lifecycle

VEGA is a normal long-lived Task. Do not record a result for it because workers
are idle or no request is pending, delete and recreate it, start a second
Mission Control, or run an agent-side polling loop. `fleet up` owns continuous
reconciliation; if it is absent, report that and use `fleet reconcile` only for
an explicit bounded pass. This starter contains no credentials or harness login
state; Thurbox and an authenticated harness must already be available.
