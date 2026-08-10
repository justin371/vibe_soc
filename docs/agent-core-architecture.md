# RTL-DV AI agent architecture

## Goal

Keep the AI agent implementation independently evolvable while making each
RTL-DV repository follow its real build and validation flow. A project should
not fork evidence semantics or duplicate Claude/Codex behavior when its target
or runner details change.

## Ownership boundaries

| Layer | Owns | Must not own |
| --- | --- | --- |
| `agent_core/` | profile schema, safe refs, workflow payload rendering, evidence binding, MCP tool partitioning, bundle manifest, core version | project names, target labels, repository paths, runner hostnames, VIP names |
| `.agents/targets/<project>/` | project profile, Bazel target/selector, runner policy, roles, skills, thin runtime adapter, user guide inputs | copied core logic, client-specific projections |
| `.claude/`, `.codex/`, `.mcp.json` | generated Claude/Codex/client projections | hand-edited source contracts |
| ETX automation repository | runner checkout, isolated source branch, bsub submission, redacted artifacts | project agent policy and client prompts |

## Runtime contract

The profile is schema version 2 and pins:

- `core.name`, `core.api_version`, and `core.version`;
- adapter identity and thin runtime module names;
- build authority, execution frontend, entry target, selector, and exact-commit policy;
- workflow, runner labels, queue, slots, and wall time;
- artifact files, compile/factory field mappings, status meanings, and safety constraints.

`workflow_inputs()` renders a plan only. It never dispatches a workflow or
accepts a free-form command. `summarize_evidence()` can require both the
expected source branch and exact source SHA, and checks bundle identity,
target/selector, source-free policy, runner identity, LSF job, exit codes, and
runtime error counts before returning `pass`.

## Client parity

The generator consumes only the adapter profile, canonical role/skill files,
and the pinned core. It produces:

- Claude role and skill projections;
- Codex role instructions with the same body, MCP assignment, and skill references;
- per-server MCP launch arguments;
- a manifest containing the profile digest, MCP signature, managed paths, and
  content hashes for overwrite checks;
- a self-contained copy of the canonical adapter under
  `.agents/targets/<project>/`.

Claude and Codex are not independent implementations. A behavior change is
made once in the canonical role/skill/core source and then checked through both
projections.

## Future standalone core repository

The current `agent_core/` directory is deliberately self-contained. A future
core repository can be imported by subtree, vendor pin, package distribution,
or a reviewed checkout. A consumer adapter records the imported core version;
the generator refuses a profile/runtime core mismatch. Core API changes should
be versioned and accompanied by fixture artifacts for both map and functional
validation evidence.

## XinAnRiver adapter

XinAnRiver remains the first deep adapter. Its legacy WORKSPACE/Bazel target and
simmer selector remain authoritative. The adapter binds them to the approved
ETX workflow and keeps map, compile, simulation, regression, and coverage as
separate evidence states. Future repositories with the same flow can reuse the
core and generator while supplying only their own profile and contracts.
