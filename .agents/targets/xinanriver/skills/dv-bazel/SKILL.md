---
name: dv-bazel
description: Route XinAnRiver build, query, compile, and test requests through the legacy WORKSPACE/Bazel DV contract.
---

# XinAnRiver Bazel DV

## Process

1. Load `.agents/project_profile.json` and bind the requested operation to an
   exact target, selector, simulator, and commit.
2. Use the source-free map before broad source inspection.
3. Route licensed Bazel and simmer execution through the fixed ETX
   workflow; use `bsub` on SHICloud for the actual workload.
4. Preserve separate states for Bazel analysis, compile, simulation,
   regression, and coverage.
5. Return the evidence paths and the first diagnostic for any non-pass state.

## Completion

The result is complete only when the artifact binds the target, profile, SHA,
and execution identity, and the status is one of the profile-defined values.
