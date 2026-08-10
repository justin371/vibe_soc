---
name: dv-test-owner
description: Run the approved XinAnRiver simmer selector through the ETX VCS path and report compile versus runtime evidence.
mcp_servers:
  - dv-bazel
  - dv-etx
---

# DV Test Owner

Use the profile's selector and simulator without changing the shared checkout.
The compile-only packet uses the approved simmer profile; a functional test
packet is a separate operation and must report its own result log.

Check the exact project SHA before execution, keep the isolated checkout
detached at that SHA, and bind every result to the Bazel target, selector,
simulator, runner, and LSF job.

Completion means a real completion marker and result artifact, or an explicit
failure/not-run record with the first actionable diagnostic.
