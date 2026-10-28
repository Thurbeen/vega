# Bundle contract, schema 1

`starter.toml` declares `version`, `id`, `content_version`, `license` and `files`.
Consumers must reject unsupported versions, duplicate paths, absolute paths,
parent traversal, symlinks and missing assets. Read only the explicit allowlist.
The source repository is `https://github.com/Thurbeen/vega`; bundle builds must
record an exact checked commit, plus per-file hashes. Never resolve a floating
branch or fetch starter content during first-run initialization.

## Rendering

1. Place `workspace/` assets in the editable VEGA workspace. Include the MIT
   license with the distributed assets and preserve it in the installation.
2. Copy `config/fleet.toml` to the selected native-platform config location only
   on first creation. Config schema 1 resolves relative data paths against the
   config file's parent. `runtime.kind` is `thurbox`, not the fake test host.
3. Generate and persist a per-instance `runtime.keyPrefix` in place of template
   `fleet`. Independent installations must not claim one another's sessions.
   Fleet v2.2.0 also renders `starter.workspace`, `data.dir` and the shipped
   `[forge.readyPolicies]` tables (`checks`, `checks-and-bots`, `strict`). It
   selects no `draftPolicy` and configures no forge hosts or
   `runtime.repositories`; the operator, or VEGA through task-intake, maps
   repository URLs to existing source checkouts. An operator must
   configure authenticated hosts before declaring changes; ready policies alone
   do not enable forge access. Preserve existing user-owned config on update.
4. Parse `tasks/vega.json` as a JSON array and set its sole Task's
   `spec.workspace.dir` to the absolute installed workspace path. The template's
   `{{workspace}}` is a whole string placeholder, not a shell expression.
   Serialize the parsed value: raw text substitution corrupts Windows paths or
   paths containing quotes. Reject any unresolved placeholder.
5. Install the rendered array as `vega/task.json` relative to the bootstrap
   root selected by the engine. Its Task is `vega`, API `fleet/v1alpha1`, with
   harness `codex`, host `local` and dispatch enabled. Select any harness/model
   customization before initial creation; the stored Task spec is immutable
   except for dispatch and forge. Do not manufacture uid, status or finalizers.
6. Apply through the Task API and persist identity. Repeated startup must inspect
   and reconnect to the existing Task, including its session and effect receipts.
   Do not regenerate identity, erase the store or spawn on an unknown probe.

`fleet up` must give the VEGA session the resolved configuration path, via
`FLEET_CONFIG` or an equally explicit startup instruction. Nested `fleet` commands
must address that same store even from a different working directory. The
starter never contains an operator's absolute path, credentials or login state.

## Managed files and user files

Keep installation metadata outside user-edited instruction text: source commit,
content version, manifest and installed baseline hash per managed file.
On update, an unchanged baseline may be replaced. Preserve edited files and
surface a separate candidate/conflict for review. Private or unrelated files
must never be overwritten or deleted, even if a future starter uses that name.
Do not use an update as an opportunity to replace an existing config or alter an
immutable live Task spec. Failed/partial updates need a retryable engine-owned
record; content has no update executable.

## Ownership

Fleet implements config discovery, init/up, reconciliation, locking, identity,
recovery, update conflicts and prerequisite diagnostics. VEGA supplies only
licensed content and typed templates. There is no VEGA controller. Fleet v2.2.0
also serves TaskConfig, EnvProvider and ChangeRequest; the starter needs only its
initial Task. No starter prompt uses the retired Python queue API.
