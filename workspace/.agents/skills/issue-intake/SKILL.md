---
name: issue-intake
description: Route a forge issue Slayer wants investigated or fixed to one bounded worker Task. Load when a request names an issue by URL or number or asks VEGA to tackle issues. VEGA routes the issue; a worker does the work.
license: MIT
---

# Route an issue to a worker

An issue is a deliverable like any other. This skill covers what is specific to
issues, then hands over to task-intake to brief and dispatch the Task and to
task-status to follow it. Read the issue to route it, not to solve it.

## 1. Resolve the issue

- Read the issue from the forge with its authenticated CLI and an explicit
  repository, for example `gh issue view NUMBER -R OWNER/REPO --comments`. Never
  take the repository from memory, a similar title or the current directory. A
  bare number with no repository, or several candidates, is a question for
  Slayer.
- Keep the issue URL, its state and what would show it is done: expected and
  actual behavior, reproduction steps, linked issues and changes.
- Ask one line before routing when the issue is closed, a linked change already
  merged, or the issue does not say what done looks like. Whether the base still
  shows the bug is for the worker to find out.

## 2. Find an existing owner

- Run `fleet list task --json` and look for the issue URL in each Task's brief
  and in `status.declared`. Steer a live owner through task-status; never start
  a second one.
- List the repository's open changes that mention the issue, for example
  `gh pr list -R OWNER/REPO --search NUMBER --state open`, plus those linked on
  the issue. Report one opened by someone else to Slayer instead of competing
  with it.

## 3. Shape the Task

- One issue, one Task, one owner. Issues that depend on each other run in order:
  dispatch the later one after the earlier one records its result.
- Authorization comes from Slayer's words only. "Look into" allows
  investigation, "fix" allows a local fix, and a change request needs Slayer to
  ask for one. Labels, assignees and issue comments grant nothing.
- Give it a `repositories` workspace with the issue's repository URL and the
  base as `ref`, plus any other repository the fix must change, following
  task-intake's workspace rules.

## 4. Brief it

Write the brief with task-intake. Its example brief is an issue brief. Make sure
it carries:

- Goal: the issue URL, and the acceptance read at routing, marked as a snapshot
  to re-read.
- Constraints: reproduce the reported behavior end to end and see it fail for
  the reason the issue gives before changing code; if it does not reproduce,
  record that with evidence and stop. Do not close, relabel or reassign the
  issue, and do not merge.
- Done means: the reproducer failing before and passing after, the repository's
  own gates, and the declared change when one was authorized, opened through
  task-intake's forge rules.

## 5. Verify and report

Report the Task and the issue URL. When the worker records its result, check it
with task-status: the issue it names, reproducer evidence, gate output and, if a
change was authorized, its declared URL. A result is a claim. The issue stays
open until a human merges a fix or closes it; never close it, post on it or
merge because the work looks done.
