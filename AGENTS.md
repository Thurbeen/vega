# VEGA source repository

This repository contains generic distributable starter content, not the Fleet
engine. Keep the bundle plain text, TOML and JSON. Do not add runtime code or
copy local operator configuration, runtime records, credentials or machine paths.

Read starter.toml and BOOTSTRAP.md before changing assets. Coordinate schema or
Task API changes with Fleet's bootstrap owner. Only allowlisted files ship.
Preserve the MIT license and attribution.

For a reported issue, write an end-to-end reproducer and see it fail for the
right reason before fixing. Required gate: set FLEET_BIN to a Fleet v2.1.0-compatible
executable, then run `uv run --no-project python -m unittest
discover -s tests -v` and `prek run --all-files`. Hooks run that same test.
Do not skip integration because a binary is missing; report the blocker.

Use the installed publish skill to publish. Require an independent exact-head
local review and answer all PR feedback. Squash merge only; workers do not merge.
No time, effort or completion estimates. Private customization belongs outside
this source repository. Skills under workspace/.agents/skills are the canonical
packages; do not maintain duplicate agent-specific copies.
