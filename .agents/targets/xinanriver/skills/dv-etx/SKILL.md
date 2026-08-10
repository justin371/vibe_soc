---
name: dv-etx
description: Safely dispatch XinAnRiver ETX workflows with fixed inputs and retrieve redacted Bazel/VCS evidence.
---

# XinAnRiver ETX

## Process

1. Resolve or verify the latest `main` SHA before dispatch.
2. Render the profile-defined workflow payload; reject targets, selectors,
   simulators, paths, or commands outside the profile.
3. Dispatch the fixed workflow from the approved automation repository/ref.
4. Let the runner create the isolated checkout and submit licensed work to
   `bsub`; the agent never opens an interactive ETX shell.
5. Download and validate the source-free artifact against the evidence schema.

## Completion

The run is complete only when its run ID, commit, target, selector, LSF job,
exit codes, and artifact verification result are recorded.
