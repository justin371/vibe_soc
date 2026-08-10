---
name: dv-evidence
description: Normalize XinAnRiver Bazel, simmer, VCS, and ETX artifacts into an auditable result state.
---

# XinAnRiver Evidence

For target-map/compile evidence, read `metadata.json`, `verification.json`,
and `compile-assessment.json` together. For the functional ETX factory path,
read `ai-bundle-verification.json`, `factory-summary.json`, `submission.txt`,
the two exit-code files, and `command.txt` together. Verify exact commit,
target, selector, profile, simulator, source-free policy, credential scan,
LSF completion, and test completion markers.

Use these meanings:

- `pass`: requested stage passed with complete required evidence;
- `pass_with_partial_map`: compile passed while Bazel closure is partial;
- `fail`: a required stage or verifier failed;
- `not_run`: the stage was outside the requested scope.

The factory packet may be a full functional simulation pass even when a repo
map was not requested; report `bazel_map=not_run` explicitly. Never promote a
partial map, compile-only result, or missing test to a full DV pass.
