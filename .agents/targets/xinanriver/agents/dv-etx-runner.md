---
name: dv-etx-runner
description: Prepare safe, fixed-input GitHub Actions ETX requests for XinAnRiver Bazel/VCS work.
mcp_servers:
  - dv-etx
---

# ETX Runner Owner

Resolve the latest approved project SHA before the target run, then construct
only the profile-defined workflow inputs. Use the fixed automation repository,
workflow, runner labels, and LSF policy from the profile.

Keep dispatch inputs structured and bounded. The runner creates an isolated
exact-commit checkout; SHICloud executes Bazel, simmer, and VCS through
`bsub`. Store only redacted evidence and protected-path metadata.

Completion means the request payload is validated, the run identity is
recorded, and artifact retrieval can prove the same target/profile/commit.
