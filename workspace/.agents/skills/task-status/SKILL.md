---
name: task-status
description: Inspect one Task's state and worker evidence, steer it through Fleet, and check a recorded result. Load for completion checks, steering, unknown state or recovery investigation; use status-digest for routine status.
license: MIT
---

# Report current Task state

Every `fleet` command reads `FLEET_CONFIG`. Routine status is the
status-digest board; open one Task only when a line needs a closer look:

```text
fleet status task NAME
fleet get task NAME
```

Summarize what you read in a line or two; never paste the resource.

Read phase, conditions, observedGeneration, brief receipt, session and result
together. A phase alone is not sufficient evidence. Compare observations with
the current spec generation, and the result's generation with the delivered
brief; stale observations stay stale.

Mission Control verifies the evidence relevant to the promised result. Do not redo
the worker's substantive assignment. Delegate an independent review or
diagnostic when verification itself requires substantive work.

| Observation | Report or action |
| --- | --- |
| Pending with dispatch false | Work has not been authorized to start. |
| `WorkspaceUnsupported` attention | The runtime cannot make one of the workspace URLs; nothing spawned. A corrected URL needs a new Task. |
| `TrustUnmapped` or `WorkspaceUntrusted` attention | The agent does not trust its workspace, or Fleet has no way to tell it to. Report the condition's message to the user; never answer a trust dialog yourself. |
| Spawned without a True `Briefed` condition | The brief is not confirmed delivered, so the work has not started. Never resend the brief or `fleet send` it. |
| Briefed | Brief delivery is recorded; completion is not yet recorded. |
| `BriefUndelivered` or `DeliveryQueued` attention | The text waits on a person, such as a dialog in the session. Report the condition's message to the user. |
| `Paused` condition True | The agent is stopped; Fleet resumes it for its next message or amendment. Not a failure. |
| Stalled or other NeedsAttention | Explain the recorded condition. Check the runtime before proposing recovery. |
| Unknown runtime answers | State is unknown. Do not create a replacement blindly. |
| Concluded with a result | A worker recorded a claim. Check the result and artifact evidence. |
| Releasing | Deletion is waiting for the session's release; do not bypass the finalizer. |

Inspect CLI errors and exit codes; never turn an unreadable store into an empty
queue. Never poll or wait in the foreground, and do not compete with the
engine's manager: changes reach you as Fleet messages in your inbox.

## Steering and the inbox

`fleet send NAME "MESSAGE"` queues a message in the Task's inbox; success means
queued, not delivered. Fleet delivers it, oldest first, when the session is
ready, even during a working turn, and records a receipt in
`status.deliveries`. A paused session is resumed to read it; a missing one
raises `WorkerGone` and is never respawned for a message. Send one prompt once:
a queued message is not lost, so never send it again as a fallback.

Steering is clarification, in-brief direction, a status request or a timely
update. It is not permission to perform the substantive assignment, edit the
worker's workspace or result, or impersonate the worker. Never type into a
worker's terminal, resend its brief or edit status.

`fleet send` to a Concluded session is conversation: it neither re-opens the
Task nor replaces its result. A follow-up on the same deliverable is a
`fleet amend` (see task-intake), which re-opens it until the worker records a
result for the new generation. A new substantive request requires a new Task.

## Declared changes

`fleet declare NAME --change-request URL` ensures a ChangeRequest mirror and
appends a worker declaration. Inspect `status.declared`, `status.forge` and
`fleet get changerequest MIRROR` for observations, gaps and conditions. An
arbitrary fact can be recorded with
`fleet declare NAME --json '{"kind":"Note","text":"Verified locally"}'`;
it concludes nothing. Neither declaration is a final result.

Forge feedback is relayed into the worker's inbox. Ready transitions depend on
the configured policy, worker completion and idle state; Fleet never merges a
change. Missing observations and stale heads are not proof that checks or review
passed. ChangeRequest mirrors outlive Tasks; deleting a Task does not delete
its changes or mirrors. Do not declare or conclude another worker's work on its
behalf.

## Worker completion

A worker records its own answer for the generation in `status.brief.generation`.
A delivered amendment advances it; a dispatch or forge edit advances only
`metadata.generation`. Fleet refuses a result while an amendment waits to be
delivered:

```text
fleet result NAME --generation 1 --outcome shipped --summary "Verified result"
```

Replace the example generation and summary with actual evidence. Outcomes are
`shipped`, `stuck`, `failed` or `not-applicable`. Supply declared structured outputs
and authorized artifact URLs when required. Do not report another worker's result
for it. Fleet stores the claim; it is not proof that a PR, CI or deployment succeeded.
For a user-authorized pull or merge request deliverable, verify a real declared
URL and the requested base. Verify everything required by the user or repository
for that delivery stage, including checks, CI and review. A local commit, an
undeclared change or blocked required gates do not satisfy that result. A
draft-only deliverable does not require later ready or merge gates unless
requested. Do not infer publication authorization for Tasks whose requested
result did not include it.

A Concluded Task keeps its session and workspace until deletion. Delete only
when the user authorizes cleanup and the conversation no longer needs it:
`fleet delete task NAME`. The runtime then removes the worktree and keeps the
branch; uncommitted work goes to `refs/fleet/preserved/...` in the repository.
Confirm the work is pushed or no longer needed first. A `file://` directory
stays as it is.
