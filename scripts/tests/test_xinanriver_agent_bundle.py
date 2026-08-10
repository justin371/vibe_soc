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
    load_core_manifest,
    load_profile,
    summarize_evidence,
    validate_profile,
    workflow_inputs,
)


class XinAnRiverAgentBundleTests(unittest.TestCase):
    def test_profile_core_binding_is_exact(self):
        profile = json.loads((PROFILE_DIR / "profile.json").read_text(encoding="utf-8"))
        profile["core"]["version"] = "9.9.9"
        with tempfile.TemporaryDirectory() as temp:
            profile_dir = Path(temp)
            (profile_dir / "profile.json").write_text(
                json.dumps(profile), encoding="utf-8"
            )
            with self.assertRaises(generator.BundleError):
                generator.load_profile(profile_dir)

    def test_profile_and_workflow_contract(self):
        profile = load_profile(PROFILE_DIR / "profile.json")
        core = load_core_manifest()
        self.assertEqual(core["core_name"], "rtl-dv-agent-core")
        self.assertEqual(profile["core"]["version"], core["core_version"])
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
        self.assertEqual(inputs["execution_frontend"], "simmer")
        self.assertEqual(inputs["automation_ref"], "main")
        source_inputs = workflow_inputs(
            profile,
            "b1eec4211c323d8c5e64ba80e323cf6394b77399",
            project_branch="lw/claude-xinanriver-ai-tools",
        )
        self.assertEqual(source_inputs["project_branch"], "lw/claude-xinanriver-ai-tools")
        with self.assertRaises(ContractError):
            workflow_inputs(profile, "B1EEC4211C323D8C5E64BA80E323CF6394B77399")
        with self.assertRaises(ContractError):
            workflow_inputs(profile, "b1eec4211c323d8c5e64ba80e323cf6394b77399", project_branch="/bad")

    def test_generated_claude_codex_parity(self):
        profile = load_profile(PROFILE_DIR / "profile.json")
        roles = generator.load_roles(PROFILE_DIR, profile)
        skills = generator.load_skills(PROFILE_DIR)
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
                self.assertIn(f'"--server", "{server["name"]}"', codex_config)
            manifest = json.loads(
                (output / ".agents/agent-manifest.json").read_text()
            )
            mcp_manifest = json.loads(
                (output / ".agents/mcp-servers.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["core"], profile["core"])
            self.assertEqual(manifest["adapter"], profile["adapter"])
            self.assertEqual(manifest["projections"], ["claude", "codex", "mcp"])
            self.assertEqual(mcp_manifest["servers"], profile["mcp_servers"])
            self.assertTrue(
                (output / ".agents/targets/xinanriver/profile.json").is_file()
            )
            core_manifest = json.loads(
                (output / "agent_core/manifest.json").read_text(encoding="utf-8")
            )
            for module in core_manifest["runtime_modules"]:
                self.assertTrue((output / f"agent_core/{module}.py").is_file())
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
                for skill_name in role["skills"]:
                    self.assertIn(skills[skill_name].strip(), codex)

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
                    "profile_name": profile["profile_name"],
                    "bazel_query_partial": True,
                    "bazel_query_exit_code": 3,
                    "compile_exit_code": 0,
                    "lsf_job_id": "722071",
                    "execution_host": "sh-cloud17.rd.lgt.ai",
                    "project_branch": "main",
                    "execution_user": "lwang",
                    "lsf_queue": "syn",
                    "lsf_slots": 8,
                    "compile_mode": "simmer --no-run",
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
            for name in (
                "bazel-targets.json",
                "source-files.csv",
                "sv-dependencies.csv",
                "unresolved-edges.csv",
                "git-history.csv",
                "repo-map.html",
            ):
                (artifact / name).write_text("\n", encoding="utf-8")
            summary = summarize_evidence(
                profile,
                artifact,
                expected_project_branch="main",
                expected_project_sha="b1eec4211c323d8c5e64ba80e323cf6394b77399",
            )
            self.assertEqual(summary["overall"], "pass_with_partial_map")
            self.assertEqual(summary["compile"], "pass")
            self.assertEqual(summary["simulation"], "not_run")

    def test_factory_evidence_is_a_functional_pass(self):
        profile = load_profile(PROFILE_DIR / "profile.json")
        with tempfile.TemporaryDirectory() as temp:
            artifact = Path(temp)
            (artifact / "ai-bundle-verification.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "source_free_bundle": True,
                        "credential_scan": "passed",
                        "adapter": profile["adapter"]["name"],
                        "core_version": profile["core"]["version"],
                        "profile_name": profile["profile_name"],
                        "entry_target": profile["project"]["entry_target"],
                        "test_selector": profile["project"]["test_selector"],
                    }
                ),
                encoding="utf-8",
            )
            (artifact / "factory-summary.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "factory_component_unregistered": False,
                        "factory_test_not_found": False,
                        "simmer_exit_code": 0,
                        "simulator": "VCS",
                        "uvm_error_count": ["0"],
                        "uvm_fatal_count": ["0"],
                    }
                ),
                encoding="utf-8",
            )
            (artifact / "submission.txt").write_text(
                "\n".join(
                    [
                        "project_branch: lw/claude-xinanriver-ai-tools",
                        "project_commit: b1eec4211c323d8c5e64ba80e323cf6394b77399",
                        "test_selector: sys_tb:sys_iod_sanity_test@1",
                        "requested_host: sh-cloud17",
                        "execution_user: lwang",
                        "lsf_queue: syn",
                        "lsf_slots: 8",
                        "agent_bundle_status: validated",
                        "agent_bundle_ref: 876ab1603c568ed0df61998da2d1394468aa31e9",
                        "source_worktree_writes: none",
                        "payload_exit_code: 0",
                        "lsf_job_id: 722272",
                    ]
                ),
                encoding="utf-8",
            )
            (artifact / "lsf-exit-code.txt").write_text("0\n", encoding="utf-8")
            (artifact / "simmer-exit-code.txt").write_text("0\n", encoding="utf-8")
            (artifact / "command.txt").write_text("bazel simmer\n", encoding="utf-8")
            summary = summarize_evidence(
                profile,
                artifact,
                expected_project_branch="lw/claude-xinanriver-ai-tools",
                expected_project_sha="b1eec4211c323d8c5e64ba80e323cf6394b77399",
            )
            self.assertEqual(summary["overall"], "pass")
            self.assertEqual(summary["bazel_map"], "not_run")
            self.assertEqual(summary["simulation"], "pass")
            self.assertEqual(
                summary["commit_sha"],
                "b1eec4211c323d8c5e64ba80e323cf6394b77399",
            )
            self.assertEqual(summary["project_branch"], "lw/claude-xinanriver-ai-tools")

    def test_factory_commit_binding_is_required_when_requested(self):
        profile = load_profile(PROFILE_DIR / "profile.json")
        with tempfile.TemporaryDirectory() as temp:
            artifact = Path(temp)
            (artifact / "ai-bundle-verification.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "source_free_bundle": True,
                        "credential_scan": "passed",
                        "adapter": profile["adapter"]["name"],
                        "core_version": profile["core"]["version"],
                        "profile_name": profile["profile_name"],
                        "entry_target": profile["project"]["entry_target"],
                        "test_selector": profile["project"]["test_selector"],
                    }
                ),
                encoding="utf-8",
            )
            (artifact / "factory-summary.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "factory_component_unregistered": False,
                        "factory_test_not_found": False,
                        "simmer_exit_code": 0,
                        "simulator": "VCS",
                        "uvm_error_count": ["0"],
                        "uvm_fatal_count": ["0"],
                    }
                ),
                encoding="utf-8",
            )
            (artifact / "submission.txt").write_text(
                "\n".join(
                    [
                        "project_branch: main",
                        "project_commit: b1eec4211c323d8c5e64ba80e323cf6394b77399",
                        "test_selector: sys_tb:sys_iod_sanity_test@1",
                        "requested_host: sh-cloud17",
                        "execution_user: lwang",
                        "lsf_queue: syn",
                        "lsf_slots: 8",
                        "agent_bundle_status: validated",
                        "agent_bundle_ref: 876ab1603c568ed0df61998da2d1394468aa31e9",
                        "source_worktree_writes: none",
                        "payload_exit_code: 0",
                        "lsf_job_id: 722272",
                    ]
                ),
                encoding="utf-8",
            )
            (artifact / "lsf-exit-code.txt").write_text("0\n", encoding="utf-8")
            (artifact / "simmer-exit-code.txt").write_text("0\n", encoding="utf-8")
            (artifact / "command.txt").write_text("simmer\n", encoding="utf-8")
            summary = summarize_evidence(
                profile,
                artifact,
                expected_project_branch="main",
                expected_project_sha="0000000000000000000000000000000000000000",
            )
            self.assertEqual(summary["overall"], "fail")
            self.assertIn("project commit mismatch", summary["binding_errors"])

    def test_existing_root_contract_is_not_overwritten_implicitly(self):
        profile = load_profile(PROFILE_DIR / "profile.json")
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output / "AGENTS.md").write_text("owned by consumer\n", encoding="utf-8")
            with self.assertRaises(generator.BundleError):
                generator.run(PROFILE_DIR, output, write=True)

    def test_modified_generated_file_is_not_overwritten_implicitly(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            self.assertEqual(generator.run(PROFILE_DIR, output, write=True), 0)
            (output / ".mcp.json").write_text("consumer-owned\n", encoding="utf-8")
            with self.assertRaises(generator.BundleError):
                generator.run(PROFILE_DIR, output, write=True)

    def test_unregistered_generated_file_is_stale(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            self.assertEqual(generator.run(PROFILE_DIR, output, write=True), 0)
            stale = output / ".agents/agents/obsolete.md"
            stale.write_text("obsolete\n", encoding="utf-8")
            with self.assertRaises(generator.BundleError):
                generator.run(PROFILE_DIR, output, write=True)

    def test_generic_adapter_can_be_generated_without_project_names(self):
        core = load_core_manifest()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = root / "adapter"
            (adapter / "agents").mkdir(parents=True)
            (adapter / "skills/generic").mkdir(parents=True)
            (adapter / "runtime").mkdir(parents=True)
            profile = {
                "schema_version": 2,
                "core": {
                    "name": core["core_name"],
                    "api_version": core["core_api_version"],
                    "version": core["core_version"],
                },
                "adapter": {
                    "name": "generic_sample",
                    "display_name": "Generic Sample",
                    "kind": "rtl_dv",
                    "runtime": {
                        "contract_module": "generic_sample_dv_contract",
                        "mcp_module": "generic_sample_dv_mcp",
                    },
                },
                "profile_name": "generic-sample-dv",
                "project": {
                    "repository_key": "example/repo",
                    "default_branch": "main",
                    "build_system": "bazel",
                    "build_mode": "legacy_workspace",
                    "execution_frontend": "runner",
                    "target_kind": "label",
                    "selector_kind": "token",
                    "workspace_files": ["WORKSPACE"],
                    "entry_target": "target-main",
                    "test_selector": "test-main",
                    "simulator": "sim",
                },
                "execution": {
                    "automation_repository": "example/automation",
                    "automation_ref": "main",
                    "workflow": "validate.yml",
                    "runner_labels": ["self-hosted"],
                    "lsf": {"queue": "q", "slots": 1, "wall_minutes": 1, "user": "agent"},
                    "checkout_policy": "isolated_exact_commit",
                    "runner_policy": "github_runner_then_bsub",
                    "map_mode": "target",
                    "keep_workdir": False,
                },
                "evidence": {
                    "required_files": ["metadata.json", "verification.json", "compile.json"],
                    "factory_required_files": [
                        "bundle.json", "summary.json", "submission.txt", "lsf.txt", "frontend.txt", "command.txt"
                    ],
                    "status_values": ["pass", "pass_with_partial_map", "fail", "not_run"],
                    "partial_map_is_pass": False,
                    "source_free_artifact": True,
                    "credential_scan": "required",
                    "require_expected_project_branch": True,
                    "require_expected_project_sha": True,
                    "map_identity_fields": ["entry_target", "test_selector", "simulator"],
                    "artifact_files": {
                        "map": {
                            "metadata": "metadata.json",
                            "verification": "verification.json",
                            "compile_assessment": "compile.json",
                        },
                        "factory": {
                            "bundle": "bundle.json",
                            "summary": "summary.json",
                            "submission": "submission.txt",
                            "lsf_exit": "lsf.txt",
                            "frontend_exit": "frontend.txt",
                            "command": "command.txt",
                        },
                    },
                    "compile_schema": {
                        "completion_key": "complete",
                        "exit_code_key": "exit",
                        "binary_present_key": "binary",
                    },
                    "factory_schema": {
                        "passed_key": "passed",
                        "component_unregistered_key": "unregistered",
                        "test_not_found_key": "not_found",
                        "runtime_exit_key": "runtime_exit",
                        "error_count_key": "errors",
                        "fatal_count_key": "fatals",
                        "simulator_key": "simulator",
                    },
                },
                "safety": {
                    "approved_vip": "vip",
                    "protected_path_parts": ["vendor"],
                    "execution_host_pattern": "host[0-9]+",
                    "free_form_workflow_command": False,
                    "source_mr_merge": False,
                },
                "constraints": {"required_equals": {}},
                "mcp_servers": [
                    {
                        "name": "dv",
                        "script": "scripts/generic_sample_dv_mcp.py",
                        "tools": ["get_profile", "plan_target_run", "review_evidence"],
                        "default_enabled": True,
                        "startup_timeout_sec": 1,
                        "tool_timeout_sec": 1,
                    }
                ],
                "roles": ["owner"],
            }
            (adapter / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
            (adapter / "agents/owner.md").write_text(
                "---\nname: owner\ndescription: Own generic DV\nmcp_servers:\n  - dv\nskills:\n  - generic\n---\n\n# Owner\n",
                encoding="utf-8",
            )
            (adapter / "skills/generic/SKILL.md").write_text(
                "---\nname: generic\ndescription: Generic skill\n---\n\n# Generic skill\n",
                encoding="utf-8",
            )
            for module in ("generic_sample_dv_contract.py", "generic_sample_dv_mcp.py"):
                (adapter / "runtime" / module).write_text("# generic adapter runtime\n", encoding="utf-8")
            output = root / "output"
            self.assertEqual(generator.run(adapter, output, write=True), 0)
            manifest = json.loads(
                (output / ".agents/agent-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["adapter"]["name"], "generic_sample")
            self.assertTrue((output / ".agents/targets/generic_sample/profile.json").is_file())

            map_only = json.loads(json.dumps(profile))
            map_only["evidence"].pop("factory_required_files")
            map_only["evidence"].pop("factory_schema")
            map_only["evidence"]["artifact_files"].pop("factory")
            validate_profile(map_only)


if __name__ == "__main__":
    unittest.main()
