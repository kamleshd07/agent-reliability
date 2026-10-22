# Repository preservation and baseline

Original primary checkouts were read/fetched only. Their tracked/untracked Git status listings were captured
before work and compared byte-for-byte afterwards; no pre-existing modification was overwritten, cleaned,
stashed or copied onto the feature branch. External evidence retains the original listings.

| Checkout | Original local head | Tracked modifications | Untracked files | Final comparison |
|---|---|---:|---:|---|
| agent-reliability | 7aa6883b6dcc5ae171f40fae570e8ee80fe88a68 | 14 | 33 | unchanged |
| agent-reliability-platform | d606293ee9ce0b2641a928fbb99f2b7ab6fe6d0c | 28 | 158 | unchanged |

New SDK worktree `gentlity-s3-sdk`, branch `session3/p30-automatic-instrumentation`, starts from freshly fetched
SDK origin/main b65374d0b2aaed2d06c563f738ca840e840956b9. Published v1.3.0 and merged platform PR62/64 were
verified through GitHub. No Session2 worktree was reused. Current platform main805b9c718f370aea784143359a7d6e8b62ea81b2
was archived read-only into external test evidence for model/fixture checks; original platform files are unchanged.
No existing worktree or database cluster was removed. No platform service or PostgreSQL process was started.
Only SDK feature-branch changes are proposed. No merge/release/deployment or AWS/IAM/EC2/Cognito operation.
