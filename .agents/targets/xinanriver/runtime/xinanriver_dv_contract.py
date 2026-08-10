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
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
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
    factory_files = evidence.get("factory_required_files")
    if not isinstance(factory_files, list) or "factory-summary.json" not in factory_files:
        errors.append(
            "evidence.factory_required_files must include factory-summary.json"
        )
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
    profile: dict[str, Any],
    project_sha: str,
    *,
    project_branch: str | None = None,
    map_profile: str | None = None,
) -> dict[str, Any]:
    validate_profile(profile)
    if not SHA_RE.fullmatch(project_sha):
        raise ContractError("project_sha must be a full lowercase Git SHA")
    if project_branch is None:
        project_branch = profile["project"]["default_branch"]
    if not BRANCH_RE.fullmatch(project_branch):
        raise ContractError("project_branch is not safe")
    if map_profile is None:
        map_profile = f"vcs-simmer-compile-main-adapt-{project_sha[:8]}"
    if not PROFILE_RE.fullmatch(map_profile):
        raise ContractError("map_profile is not safe")
    project = profile["project"]
    return {
        "project_branch": project_branch,
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


def _read_key_value_file(artifact_dir: Path, name: str) -> dict[str, str]:
    path = artifact_dir / name
    if not path.is_file():
        raise ContractError(f"missing evidence file: {name}")
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        result[key] = value
    return result


def _read_exit_code(artifact_dir: Path, name: str) -> int:
    path = artifact_dir / name
    if not path.is_file():
        raise ContractError(f"missing evidence file: {name}")
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError as exc:
        raise ContractError(f"invalid exit code: {name}") from exc


def _all_zero(value: Any) -> bool:
    values = value if isinstance(value, list) else [value]
    return bool(values) and all(str(item) == "0" for item in values)


def _summarize_factory_evidence(
    profile: dict[str, Any],
    artifact_dir: Path,
    *,
    expected_project_branch: str | None = None,
) -> dict[str, Any]:
    bundle = _read_json(artifact_dir, "ai-bundle-verification.json")
    factory = _read_json(artifact_dir, "factory-summary.json")
    submission = _read_key_value_file(artifact_dir, "submission.txt")
    lsf_exit_code = _read_exit_code(artifact_dir, "lsf-exit-code.txt")
    simmer_exit_code = _read_exit_code(artifact_dir, "simmer-exit-code.txt")
    project = profile["project"]
    binding_errors: list[str] = []
    if bundle.get("status") != "passed":
        binding_errors.append("AI bundle verification did not pass")
    if bundle.get("source_free_bundle") is not True:
        binding_errors.append("AI bundle is not source-free")
    if submission.get("agent_bundle_status") != "validated":
        binding_errors.append("agent bundle was not validated in the isolated clone")
    project_branch = submission.get("project_branch", "")
    if not BRANCH_RE.fullmatch(project_branch):
        binding_errors.append("project branch is not safe")
    if expected_project_branch is not None:
        if not BRANCH_RE.fullmatch(expected_project_branch):
            binding_errors.append("expected project branch is not safe")
        elif project_branch != expected_project_branch:
            binding_errors.append("project branch mismatch")
    if submission.get("test_selector") != project["test_selector"]:
        binding_errors.append("test selector mismatch")
    if submission.get("source_worktree_writes") != "none":
        binding_errors.append("source checkout was written")
    if not SHA_RE.fullmatch(submission.get("project_commit", "")):
        binding_errors.append("project commit is not a full lowercase SHA")
    if not SHA_RE.fullmatch(submission.get("agent_bundle_ref", "")):
        binding_errors.append("agent bundle ref is not a full lowercase SHA")
    if not re.fullmatch(r"sh-cloud[0-9]+", submission.get("requested_host", "")):
        binding_errors.append("requested host is not an approved SHICloud host")

    factory_ok = (
        factory.get("passed") is True
        and factory.get("factory_component_unregistered") is False
        and factory.get("factory_test_not_found") is False
        and factory.get("simmer_exit_code") == 0
        and _all_zero(factory.get("uvm_error_count"))
        and _all_zero(factory.get("uvm_fatal_count"))
        and lsf_exit_code == 0
        and simmer_exit_code == 0
    )
    overall = "pass" if factory_ok and not binding_errors else "fail"
    return {
        "overall": overall,
        "evidence_kind": "factory_validation",
        "bazel_map": "not_run",
        "compile": "pass" if simmer_exit_code == 0 else "fail",
        "simulation": "pass" if factory_ok else "fail",
        "coverage": "not_run",
        "binding_errors": binding_errors,
        "commit_sha": submission.get("project_commit"),
        "project_branch": project_branch,
        "vibe_soc_ref": submission.get("agent_bundle_ref"),
        "entry_target": project["entry_target"],
        "test_selector": submission.get("test_selector"),
        "simulator": project["simulator"],
        "lsf_job_id": submission.get("lsf_job_id"),
        "execution_host": submission.get("requested_host"),
        "lsf_exit_code": lsf_exit_code,
        "simmer_exit_code": simmer_exit_code,
        "uvm_error_count": factory.get("uvm_error_count"),
        "uvm_fatal_count": factory.get("uvm_fatal_count"),
    }


def summarize_evidence(
    profile: dict[str, Any],
    artifact_dir: Path,
    *,
    expected_project_branch: str | None = None,
) -> dict[str, Any]:
    validate_profile(profile)
    if (artifact_dir / "factory-summary.json").is_file():
        return _summarize_factory_evidence(
            profile,
            artifact_dir,
            expected_project_branch=expected_project_branch,
        )
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
        "project_branch": execution.get("project_branch", project["default_branch"]),
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
