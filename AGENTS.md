# VEGA source repository

This repository is VEGA, a Mission Control Task for Fleet v3: its installers,
its Task template and the workspace its agent reads. It is not the Fleet
engine. Keep the content plain text, JSON and the two install scripts; never
copy local operator configuration, Fleet stores, credentials or machine paths.

Check every Fleet claim against Fleet v3's code and docs (`docs/fleet/` in
Thurbeen/thurbox). A place is `<runtime>/<place>`. `install.sh` and
`install.ps1` do the same steps; change both together.

For a reported issue, write an end-to-end reproducer and see it fail for the
right reason before fixing. Required gate: set FLEET_BIN to a Fleet v3 binary
and have `jq` installed, then run `uv run --no-project python -m unittest
discover -s tests -v` and `prek run --all-files`. Hooks run that same test.
Do not skip integration because a binary is missing; report the blocker.

Use the installed publish skill to publish. Require an independent exact-head
local review and answer all PR feedback. Squash merge only; workers do not merge.
No time, effort or completion estimates. Skills under workspace/.agents/skills
are the canonical packages; do not keep agent-specific copies.
