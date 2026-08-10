# XinAnRiver AI-tool parity

The integration has three layers:

```text
agent_core/                         reusable, versioned DV contract/runtime
    +
.agents/targets/xinanriver/         XinAnRiver adapter: profile/roles/skills
    +
.claude/ .codex/ .mcp.json          generated client projections
```

`.agents/targets/xinanriver/` is the canonical XinAnRiver adapter. It keeps the
consumer's legacy WORKSPACE/Bazel model and points licensed execution at the
private ETX workflow. The reusable `agent_core/` package contains no
XinAnRiver target, repository path, or licensed endpoint, so it can later be
extracted into an independently versioned repository.

| Capability | Claude Code | Codex | Shared source/evidence |
| --- | --- | --- | --- |
| Role contract | `.claude/agents/*.md` | `.codex/agents/*.toml` | `.agents/targets/xinanriver/agents/*.md` |
| Skills | `.claude/skills/*/SKILL.md` | role instructions embed the same skill bodies + MCP | `.agents/targets/xinanriver/skills/*` |
| Tool registry | `.mcp.json` | `.codex/config.toml` | `profile.json` `mcp_servers` |
| Target execution | fixed ETX workflow inputs | fixed ETX workflow inputs | `project` + `execution` |
| Result review | `dv-evidence` MCP | `dv-evidence` MCP | `runtime/xinanriver_dv_contract.py` |
| Core/runtime version | generated entrypoint | generated entrypoint | `agent_core/manifest.json` + `profile.core` |

The generator writes a self-contained bundle, including the adapter source, into
an isolated output directory:

```text
python3 scripts/generate_target_agent_bundle.py \
  --profile-dir .agents/targets/xinanriver \
  --output-dir <XinAnRiver-worktree> --write
```

Run the same command with `--check` after generation. The generated adapters
share role names, descriptions, instruction bodies, skill references, MCP
server names, target, selector, execution frontend, and evidence meanings.
The generated manifest includes the MCP tool signature and managed-file hashes;
each MCP server exposes only its assigned tools. A partial Bazel map remains
`pass_with_partial_map`; it never becomes a full pass.

The functional ETX factory packet is reviewed separately from a map packet:
`ai-bundle-verification.json`, `factory-summary.json`, `submission.txt`, exit
codes, and `command.txt`. A passing factory simulation reports
`bazel_map=not_run` when no repo map was requested; it does not silently claim
full Bazel closure or coverage.

The bundle contains no credentials or fixed absolute filesystem paths. The
generator writes `.agents/agent-manifest.json` with the core version, adapter,
profile digest, and managed generated paths. It refuses implicit overwrites of
an existing consumer `AGENTS.md`/`CLAUDE.md` and detects stale generated files.
The ETX automation repository remains the execution control plane; source
changes to XinAnRiver require a separately approved isolated branch/MR
operation.
