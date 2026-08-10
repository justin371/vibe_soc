# XinAnRiver AI-tool parity

`.agents/targets/xinanriver/` is the portable canonical profile derived from
the reusable `vibe_soc` agent/MCP generation pattern. It keeps the consumer's
legacy WORKSPACE/Bazel model and points licensed execution at the private ETX
workflow.

| Capability | Claude Code | Codex | Shared source/evidence |
| --- | --- | --- | --- |
| Role contract | `.claude/agents/*.md` | `.codex/agents/*.toml` | `.agents/targets/xinanriver/agents/*.md` |
| Skills | `.claude/skills/*/SKILL.md` | role instructions + MCP | `.agents/targets/xinanriver/skills/*` |
| Tool registry | `.mcp.json` | `.codex/config.toml` | `profile.json` `mcp_servers` |
| Target execution | fixed ETX workflow inputs | fixed ETX workflow inputs | `project` + `execution` |
| Result review | `dv-evidence` MCP | `dv-evidence` MCP | `runtime/xinanriver_dv_contract.py` |

The generator writes a bundle into an isolated output directory:

```text
python3 scripts/generate_target_agent_bundle.py \
  --profile-dir .agents/targets/xinanriver \
  --output-dir <XinAnRiver-worktree> --write
```

Run the same command with `--check` after generation. The generated adapters
share role names, descriptions, instruction bodies, MCP server names, target,
selector, simulator, and evidence meanings. A partial Bazel map remains
`pass_with_partial_map`; it never becomes a full pass.

The bundle contains no credentials or fixed absolute filesystem paths. The
ETX automation repository remains the execution control plane; source changes
to XinAnRiver require a separately approved isolated branch/MR operation.
