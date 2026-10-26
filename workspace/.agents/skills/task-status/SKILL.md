---
name: task-status
description: Inspect Task state and worker evidence in Fleet v2.1.0. Load for progress questions, completion checks, unknown state or recovery investigation.
license: MIT
---

# Report current Task state

Run `fleet version --json` and use the exact Mission Control configuration
for every operation, explicitly with `fleet --config PATH` or inherited
`FLEET_CONFIG`. These examples require Fleet v2.1.0 capabilities.

```text
fleet list task --json
fleet status task NAME --json
fleet get task NAME
```

Read phase, conditions, observedGeneration, brief receipt, session reference and
result together. A phase alone is not sufficient evidence. Compare observations
with the current spec generation, and the result's generation with the delivered
brief; stale observations stay stale.

| Observation | Report or action |
| --- | --- |
| Pending with dispatch false | Work has not been authorized to start. |
| Spawning or Spawned | Startup is in progress; inspect conditions and receipts. |
| Briefed | Brief delivery is recorded; completion is not yet recorded. |
| Stalled or NeedsAttention | Explain the recorded condition. Check the runtime before proposing recovery. |
| Unknown or disconnected runtime | State is unknown. Do not create a replacement blindly. |
| Concluded with a result | A worker recorded a claim. Check the result and artifact evidence. |
| Releasing | Deletion is waiting for session cleanup; do not bypass the finalizer. |

Inspect CLI errors and exit codes; never turn an unreadable store into an empty
queue. Do not poll in a tight agent loop or compete with the engine's manager.
A bounded `fleet reconcile --max-passes 10 --json` can advance an explicitly
requested manual check; it is not a background service.

## Execution, inbox and declared changes

Inspect `status.execution` for the frozen harness/host/model and source resource
identities. Resolved environment values stay in private launch snapshots, outside
resource reads. Inspect referenced defaults with `fleet get taskconfig NAME` and
`fleet get envprovider NAME`; passive resources have no lifecycle phase. Their
current specs may differ from a Task's frozen execution.

Read `fleet send --help` and `fleet declare --help`. `fleet send NAME "MESSAGE"`
queues a message; success means queued, not delivered. Inspect `status.inbox`,
`status.deliveries` and delivery conditions for receipts or failure. The controller
delivers oldest first to ready sessions, including retained Concluded sessions.
A missing concluded worker raises WorkerGone; it is never respawned for delivery.
Do not replace the inbox through apply or edit status directly.

`fleet declare NAME --change-request URL` ensures a ChangeRequest mirror and
appends a worker declaration. Inspect `status.declared`, `status.forge` and
`fleet get changerequest MIRROR` for observations, gaps and conditions. The
operator must configure the URL's forge host and authenticate its CLI first.
An arbitrary fact can be recorded with
`fleet declare NAME --json '{"kind":"Note","text":"Verified locally"}'`;
it concludes nothing. Neither declaration is a final result.

Forge feedback is relayed into the inbox. Ready transitions depend on configured
policy, worker completion and idle state; Fleet never merges a change. Missing
observations and stale heads are not proof that checks or review passed.
ChangeRequest mirrors outlive Tasks; deleting a Task does not delete its changes
or mirrors. Do not declare or conclude another worker's work on its behalf.

## Worker completion

Read `fleet result --help` and the Task's brief receipt. A worker records its own
answer once, with the generation in `status.brief.generation`, even if a later
dispatch or forge edit advanced `metadata.generation`:

```text
fleet result NAME --generation 1 --outcome shipped --summary "Verified result"
```

Replace the example generation and summary with actual evidence. Outcomes are
`shipped`, `stuck`, `failed` or `not-applicable`. Supply declared structured outputs
and authorized artifact URLs when required. Do not report another worker's result
for it. Fleet stores the claim; it is not proof that a PR, CI or deployment succeeded.
Forge observations provide separate evidence; inspect them when configured.
After reconciliation, Concluded keeps its session until deletion. Delete only
when the user authorizes cleanup and the conversation no longer needs it.
