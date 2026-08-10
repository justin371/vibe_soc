#!/usr/bin/env python3
"""Pure validation and evidence helpers for the portable XinAnRiver bundle."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TARGET_RE = re.compile(r"^//[A-Za-z0-9_./+-]+:[A-Za-z0-9_./+-]+$")
SELECTOR_RE = re.compile(r"^[A-Za-z0-9_./+-]+:[A-Za-z0-9_./+@-]+$")
PROFILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+/-]{0,127}$")
ABSOLUTE_RE = re.compile(r"(?:^[A-Za-z]:[\\/])|(?:^/)")


class ContractError(ValueError):
    """Raised when a profile or evidence packet violates the contract."""


def load_profile(path: Path | None = None) -> dict[str, Any]:
    path = path or Path(__file__).resolve().parents[1] / "project_profile.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    validate_profile(profile)
    return profile


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def validate_profile(profile: dict[str, Any]) -> None:
    errors: list[str] = []
    if profile.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    project = profile.get("project")
    execution = profile.get("execution")
    evidence = profile.get("evidence")
    safety = profile.get("safety")
    if not isinstance(project, dict):
        errors.append("project must be an object")
        project = {}
    if not isinstance(execution, dict):
        errors.append("execution must be an object")
        execution = {}
    if not isinstance(evidence, dict):
        errors.append("evidence must be an object")
        evidence = {}
    if not isinstance(safety, dict):
        errors.append("safety must be an object")
        safety = {}

    if not project.get("repository_key"):
        errors.append("project.repository_key is required")
    if project.get("default_branch") != "main":
        errors.append("project.default_branch must be main")
    if project.get("build_system") != "bazel":
        errors.append("project.build_system must be bazel")
    if project.get("bazel_mode") != "legacy_workspace":
        errors.append("project.bazel_mode must be legacy_workspace")
    if not TARGET_RE.fullmatch(str(project.get("entry_target", ""))):
        errors.append("project.entry_target is not a safe Bazel label")
    if not SELECTOR_RE.fullmatch(str(project.get("test_selector", ""))):
        errors.append("project.test_selector is not a safe simmer selector")
    if project.get("simulator") != "VCS":
        errors.append("project.simulator must be VCS")

    if not execution.get("automation_repository"):
        errors.append("execution.automation_repository is required")
    if not execution.get("workflow"):
        errors.append("execution.workflow is required")
    labels = execution.get("runner_labels")
    if labels != ["self-hosted", "linux", "x64", "etx-vcs"]:
        errors.append("execution.runner_labels must be the approved ETX labels")
    lsf = execution.get("lsf")
    if not isinstance(lsf, dict) or lsf.get("queue") != "syn" or lsf.get("slots") != 8:
        errors.append("execution.lsf must use queue syn and 8 slots")
    if execution.get("checkout_policy") != "isolated_exact_commit":
        errors.append("execution.checkout_policy must be isolated_exact_commit")
    if execution.get("runner_policy") != "github_runner_then_bsub":
        errors.append("execution.runner_policy must be github_runner_then_bsub")

    required_files = evidence.get("required_files")
    if not isinstance(required_files, list) or "verification.json" not in required_files:
        errors.append("evidence.required_files must include verification.json")
    if evidence.get("partial_map_is_pass") is not False:
        errors.append("partial map must not be promoted to pass")
    if safety.get("approved_vip") != "vip_vcs_svt_pkg":
        errors.append("safety.approved_vip must be vip_vcs_svt_pkg")
    if safety.get("free_form_workflow_command") is not False:
        errors.append("free-form workflow commands must be disabled")

    for value in _walk_strings(profile):
        if ABSOLUTE_RE.search(value) and not value.startswith("//"):
            errors.append(f"profile contains an absolute path: {value}")
            break
    if errors:
        raise ContractError("; ".join(errors))


def workflow_inputs(
    profile: dict[str, Any], project_sha: str, *, map_profile: str | None = None
) -> dict[str, Any]:
    validate_profile(profile)
    if not SHA_RE.fullmatch(project_sha):
        raise ContractError("project_sha must be a full lowercase Git SHA")
    if map_profile is None:
        map_profile = f"vcs-simmer-compile-main-adapt-{project_sha[:8]}"
    if not PROFILE_RE.fullmatch(map_profile):
        raise ContractError("map_profile is not safe")
    project = profile["project"]
    return {
        "project_branch": project["default_branch"],
        "expected_project_sha": project_sha,
        "map_mode": "target",
        "entry_target": project["entry_target"],
        "test_selector": project["test_selector"],
        "map_profile": map_profile,
        "keep_workdir": False,
    }


def _read_json(artifact_dir: Path, name: str) -> dict[str, Any]:
    path = artifact_dir / name
    if not path.is_file():
        raise ContractError(f"missing evidence file: {name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractError(f"evidence file is not an object: {name}")
    return value


def summarize_evidence(profile: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    validate_profile(profile)
    metadata = _read_json(artifact_dir, "metadata.json")
    verification = _read_json(artifact_dir, "verification.json")
    compile_assessment = _read_json(artifact_dir, "compile-assessment.json")
    execution = metadata.get("execution", {})
    project = profile["project"]
    binding_errors = []
    for key, expected in (
        ("entry_target", project["entry_target"]),
        ("test_selector", project["test_selector"]),
        ("simulator", project["simulator"]),
    ):
        if execution.get(key) != expected:
            binding_errors.append(f"execution.{key} mismatch")
    if verification.get("status") != "passed":
        binding_errors.append("verification status is not passed")
    if verification.get("credential_scan") != "passed":
        binding_errors.append("credential scan did not pass")
    if verification.get("source_free_artifact") is not True:
        binding_errors.append("artifact is not source-free")

    compile_ok = (
        compile_assessment.get("vcs_compile_completed") is True
        and compile_assessment.get("simmer_exit_code") == 0
        and compile_assessment.get("simv_present") is True
    )
    query_partial = execution.get("bazel_query_partial") is True
    if binding_errors or not compile_ok:
        overall = "fail"
    elif query_partial:
        overall = "pass_with_partial_map"
    else:
        overall = "pass"
    return {
        "overall": overall,
        "bazel_map": "partial" if query_partial else "complete",
        "compile": "pass" if compile_ok else "fail",
        "simulation": "not_run",
        "coverage": "not_run",
        "binding_errors": binding_errors,
        "commit_sha": metadata.get("commit_sha"),
        "entry_target": execution.get("entry_target"),
        "test_selector": execution.get("test_selector"),
        "simulator": execution.get("simulator"),
        "lsf_job_id": execution.get("lsf_job_id"),
        "execution_host": execution.get("execution_host"),
        "manifest_count": execution.get("manifest_count"),
        "query_exit_code": execution.get("bazel_query_exit_code"),
        "compile_exit_code": execution.get("compile_exit_code"),
    }


def parity_signature(profile: dict[str, Any]) -> dict[str, Any]:
    validate_profile(profile)
    return {
        "profile_name": profile["profile_name"],
        "entry_target": profile["project"]["entry_target"],
        "test_selector": profile["project"]["test_selector"],
        "simulator": profile["project"]["simulator"],
        "workflow": profile["execution"]["workflow"],
        "mcp_servers": tuple(server["name"] for server in profile["mcp_servers"]),
        "roles": tuple(profile["roles"]),
    }
