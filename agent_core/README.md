# RTL-DV agent core

`agent_core/` is the reusable part of the Claude Code/Codex DV integration.
It owns the profile schema, safe workflow-input rendering, evidence binding,
MCP tool separation, and generated-bundle manifest. It must not contain a
project name, a repository path, a target label, a simulator-specific command,
or a licensed tool endpoint.

Each consumer supplies a project adapter under:

```text
.agents/targets/<project>/
  profile.json
  agents/*.md
  skills/*/SKILL.md
  runtime/<project>_dv_contract.py
  runtime/<project>_dv_mcp.py
```

The adapter wrappers are intentionally thin. They import this package and
provide the project profile; they do not fork the contract or evidence logic.
The bundle generator copies this directory into the consumer repository so a
future standalone core repository can be imported, vendored, or pinned by
`core_version` without changing the project adapter contract.

Compatibility rules:

- `core_api_version` changes only with a deliberate contract migration.
- `core_version` may evolve independently of a project profile.
- A profile records the core name/version it was generated and validated with.
- Claude and Codex are projections; neither client output is a source of truth.
