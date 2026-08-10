---
name: dv-evidence
description: Normalize XinAnRiver Bazel, simmer, VCS, and ETX artifacts into an auditable result state.
---

# XinAnRiver Evidence

Read `metadata.json`, `verification.json`, and `compile-assessment.json`
together. Verify exact commit, target, profile, simulator, source-free policy,
credential scan, and completion markers.

Use these meanings:

- `pass`: requested stage passed with complete required evidence;
- `pass_with_partial_map`: compile passed while Bazel closure is partial;
- `fail`: a required stage or verifier failed;
- `not_run`: the stage was outside the requested scope.

Never promote a partial map, compile-only result, or missing test to a full DV
pass.
