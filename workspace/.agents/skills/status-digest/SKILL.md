---
name: status-digest
description: One short line per live Task or Task that needs the user, read from Fleet, and the labels that record order and pending decisions. Load for any status question, at session start and after a clear.
license: MIT
---

# Status digest

Fleet holds Mission Control's state. Read it with this one command, which needs
`jq`, and work from its lines. Do not dump raw JSON or keep a copy elsewhere.

```sh
fleet list task --json | jq -r '.[] | select(.metadata.name != "vega") | (.status // {}) as $s | (.metadata.labels // {}) as $l | ((.spec.amendments // []) | map(.generation) | max // 0) as $g | [([($s.declared // [])[] | select(.kind == "Question") | .id] - (($s.answered // {}) | keys) | .[] | "ask:\(.)"), ($l["vega.fleet.dev/needs"] // "" | select(. != "") | "needs:\(.)"), (($s.conditions // [])[] | select(.type == "NeedsAttention" and .status == "True") | "attention:\(.reason)")] as $you | select($s.phase != "Concluded" or ($you | length) > 0 or ($s.result.generation // 0) < $g) | [.metadata.name, (if .spec.dispatch then $s.phase // "Pending" else "held" end), ($l["vega.fleet.dev/after"] // "" | select(. != "") | "after:\(.)"), (if ($s.result.generation // $g) < $g then "amended" else empty end), $you[]] | join(" ")'
```

A finished Task, Concluded with nothing pending, has no line: its result was
reported when it reached your inbox. No lines means "Nothing running."

| Field | Meaning |
| --- | --- |
| `held` | `dispatch` is false: queued `after` another, or waiting on the user. |
| `after:` | Dispatch this Task when the named one concludes. |
| `amended` | An amendment waits for the worker's answer. |
| `ask:ID` | A worker Question not yet answered: `fleet send NAME --answers ID TEXT`. |
| `needs:` | A decision waiting on the user. |
| `attention:` | A `NeedsAttention` reason; see task-status. |

A user answer for a held Task goes into its labels or a new Task, never only
into this conversation. Set or replace a label; an empty value clears it:

```sh
fleet label task NAME "vega.fleet.dev/needs=choose a base branch"
```

Release a held Task only when its `after` Task concluded with a verified
`shipped` result and nothing is needed; any other outcome goes to the user:

```sh
fleet get task NAME | jq '.spec.dispatch = true | .metadata.labels |= del(.["vega.fleet.dev/after"], .["vega.fleet.dev/needs"]) | del(.status)' | fleet apply -f -
```
