#!/usr/bin/env python3
"""License-free parity and contract tests for the XinAnRiver bundle."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR = ROOT / ".agents/targets/xinanriver"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(PROFILE_DIR / "runtime"))

import generate_target_agent_bundle as generator  # noqa: E402
from xinanriver_dv_contract import (  # noqa: E402
    ContractError,
    load_profile,
    summarize_evidence,
    workflow_inputs,
)


class XinAnRiverAgentBundleTests(unittest.TestCase):
    def test_profile_and_workflow_contract(self):
        profile = load_profile(PROFILE_DIR / "profile.json")
        inputs = workflow_inputs(
            profile, "b1eec4211c323d8c5e64ba80e323cf6394b77399"
        )
        self.assertEqual(inputs["project_branch"], "main")
        self.assertEqual(
            inputs["entry_target"],
            "//hw/dv/project_benches/sys/tb/tests:sys_iod_sanity_test",
        )
        self.assertEqual(inputs["test_selector"], "sys_tb:sys_iod_sanity_test@1")
        self.assertEqual(inputs["map_mode"], "target")
        with self.assertRaises(ContractError):
            workflow_inputs(profile, "B1EEC4211C323D8C5E64BA80E323CF6394B77399")

    def test_generated_claude_codex_parity(self):
        profile = load_profile(PROFILE_DIR / "profile.json")
        roles = generator.load_roles(PROFILE_DIR, profile)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            self.assertEqual(generator.run(PROFILE_DIR, output, write=True), 0)
            self.assertEqual(generator.run(PROFILE_DIR, output, write=False), 0)
            claude_servers = json.loads((output / ".mcp.json").read_text())[
                "mcpServers"
            ]
            codex_config = (output / ".codex/config.toml").read_text()
            self.assertEqual(
                set(claude_servers), {server["name"] for server in profile["mcp_servers"]}
            )
            for server in profile["mcp_servers"]:
                self.assertIn(f"[mcp_servers.{server['name']}]", codex_config)
            for role in roles:
                claude = (output / ".claude/agents" / f"{role['name']}.md").read_text()
                codex = (output / ".codex/agents" / f"{role['name']}.toml").read_text()
                self.assertIn(role["description"], claude)
                self.assertIn(role["description"], codex)
                self.assertIn(role["body"].strip(), claude)
                self.assertIn(role["body"].strip(), codex)
                self.assertIn(
                    f"# MCP servers: {', '.join(role['mcp_servers'])}", codex
                )

    def test_evidence_partial_is_not_full_pass(self):
        profile = load_profile(PROFILE_DIR / "profile.json")
        with tempfile.TemporaryDirectory() as temp:
            artifact = Path(temp)
            metadata = {
                "commit_sha": "b1eec4211c323d8c5e64ba80e323cf6394b77399",
                "execution": {
                    "entry_target": profile["project"]["entry_target"],
                    "test_selector": profile["project"]["test_selector"],
                    "simulator": "VCS",
                    "bazel_query_partial": True,
                    "bazel_query_exit_code": 3,
                    "compile_exit_code": 0,
                    "lsf_job_id": "722071",
                    "execution_host": "sh-cloud17.rd.lgt.ai",
                    "manifest_count": 57,
                },
            }
            verification = {
                "status": "passed",
                "credential_scan": "passed",
                "source_free_artifact": True,
            }
            compile_assessment = {
                "vcs_compile_completed": True,
                "simmer_exit_code": 0,
                "simv_present": True,
            }
            for name, value in (
                ("metadata.json", metadata),
                ("verification.json", verification),
                ("compile-assessment.json", compile_assessment),
            ):
                (artifact / name).write_text(json.dumps(value), encoding="utf-8")
            summary = summarize_evidence(profile, artifact)
            self.assertEqual(summary["overall"], "pass_with_partial_map")
            self.assertEqual(summary["compile"], "pass")
            self.assertEqual(summary["simulation"], "not_run")


if __name__ == "__main__":
    unittest.main()
