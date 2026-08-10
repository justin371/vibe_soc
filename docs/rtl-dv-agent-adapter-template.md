# RTL-DV adapter template

For a later project whose flow is equivalent to XinAnRiver, keep the reusable
core and replace only the adapter:

```text
.agents/targets/<project>/
  profile.json                 # project facts and execution constraints
  agents/*.md                  # role contracts with mcp_servers/skills
  skills/*/SKILL.md            # project workflow contracts
  runtime/<project>_dv_contract.py
  runtime/<project>_dv_mcp.py
```

The profile must pin the imported core:

```json
{
  "schema_version": 2,
  "core": {
    "name": "rtl-dv-agent-core",
    "api_version": 1,
    "version": "0.3.0"
  },
  "adapter": {
    "name": "project_name",
    "display_name": "Project Name",
    "kind": "rtl_dv",
    "runtime": {
      "contract_module": "project_name_dv_contract",
      "mcp_module": "project_name_dv_mcp"
    }
  }
}
```

The remaining `project`, `execution`, `evidence`, `safety`, and `constraints`
fields should describe the consumer's actual Bazel/simmer/ETX flow. Do not
copy XinAnRiver's target, branch, queue, runner host, VIP, or repository key.
The `evidence` section must also declare the map/factory artifact file mapping,
the required identity fields, and whether callers must provide the exact
validated branch and commit before an artifact can pass.

Generate and validate the projections with:

```bash
make target-agent-bundle \
  AGENT_PROFILE_DIR=.agents/targets/<project> \
  AGENT_BUNDLE_OUTPUT=tmp/<project>-agent-bundle
make target-agent-check \
  AGENT_PROFILE_DIR=.agents/targets/<project> \
  AGENT_BUNDLE_OUTPUT=tmp/<project>-agent-bundle
```

Only core contract changes belong in `agent_core/`. A project-only change
belongs in the adapter. This keeps the core independently versionable and
makes the generated Claude and Codex behavior remain aligned.
