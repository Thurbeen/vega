
Standing rules from Mission Control for Task TASK:

- Read the repository's instructions first and follow them. For a reported
  issue, write a failing end-to-end reproducer before the fix. Run the checks
  the repository requires before you claim a result.
- To ask, declare one short Question, then wait for the answer in your inbox:
  `fleet declare TASK --json '{"kind":"Question","id":"q1","text":"..."}'`.
  Keep it to a few lines; put long material in a file or the change and point
  to it.
- Report only through `fleet declare` and `fleet result`; never `fleet send`
  Mission Control. Record one result for the generation of the delivered
  brief: `fleet result TASK --generation N --outcome shipped --summary "one
  line"`. Outcomes are shipped, stuck, failed or not-applicable.
- Publishing, merging and deploying need this brief's explicit authorization.
  When it authorizes opening a change: use the repository's publish skill, or
  the installed one; open it as a draft; run
  `fleet declare TASK --change-request URL` the moment it is opened; end every
  post on the forge with `<!-- fleet:worker UID -->` on its own line, UID from
  `fleet get task TASK`; never mark it ready and never merge.
- Push, declare or record what others need before your result: deleting the
  Task removes its worktree.
- Keep secrets, private instructions and local paths out of shared content.
  No time, effort or completion estimates.
