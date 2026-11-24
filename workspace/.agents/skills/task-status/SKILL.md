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
| `BriefUndelivered` attention | The brief waits on a person, such as a dialog in the session. Report the condition's message to the user. |
| `DeliveryUnconfirmed`, `DeliveryFailed` or `DeliveryQueued` attention | Fleet gave up on the inbox entry the condition names and never sends it again. Once its cause is cleared, `fleet send NAME --retry KEY` queues a copy; `fleet send NAME --drop KEY` removes one no longer needed. Never retype it with a plain `fleet send`. |
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

## Checking a result

A child's result reaches your inbox once per generation; report it once, as
one `Done:` line. Later news on the same Task changes nothing unless it changes
the outcome. A summary over 4 000 bytes arrives as its size and
`fleet get task NAME`; read only `.status.result.summary`.

A result is the worker's claim for the generation in `status.brief.generation`;
it is not proof. Verify the evidence the promised result needs, never redo the
work. For a pull or merge request deliverable, check `status.declared` for the
real URL, then `fleet status changerequest MIRROR` for the requested base and
the checks, CI and review required for that stage; a draft-only deliverable
needs no ready or merge gates. A local commit, an undeclared change or a
blocked required gate does not satisfy it. Fleet never merges; mirrors outlive
Tasks. Never declare or record a result for another worker.

## Cleanup

A Concluded Task keeps its session and worktree, and their disk, until it is
deleted. Delete only with the user's consent, given once as a standing
preference or for these Tasks: a Task whose result was reported, with no
`ask:` or `attention:`, whose declared changes are merged or closed, and whose
work is pushed or no longer needed. These are the candidates:

```sh
fleet list task --json | jq -r '.[] | select(.status.phase == "Concluded") | .metadata.name'
```

`fleet delete task NAME` then removes the worktree and keeps the branch;
uncommitted work goes to `refs/fleet/preserved/...` in the repository. A
`file://` directory stays as it is. ChangeRequest mirrors outlive the Task.
