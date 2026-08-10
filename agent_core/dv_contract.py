#!/usr/bin/env python3
"""Reusable, project-neutral RTL-DV profile and evidence contract."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import CORE_API_VERSION, CORE_NAME, CORE_VERSION


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+/@-]{0,127}$")
PROFILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+/-]{0,127}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")
TARGET_RE = re.compile(
    r"^(?:@[A-Za-z0-9._+/-]+)?//[A-Za-z0-9_./+~-]+(?::[A-Za-z0-9_./+~-]+)?$"
)
SELECTOR_RE = re.compile(r"^[A-Za-z0-9_./+~-]+:[A-Za-z0-9_./+@~-]+$")
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
ABSOLUTE_RE = re.compile(r"(?:^[A-Za-z]:[\\/])|(?:^/)")


class ContractError(ValueError):
    """Raised when a profile or evidence packet violates the core contract."""


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def _get_path(document: dict[str, Any], dotted_path: str) -> Any:
    current: Any = document
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _is_safe_ref(value: Any) -> bool:
    if not isinstance(value, str) or not REF_RE.fullmatch(value):
        return False
    return (
        ".." not in value
        and "//" not in value
        and "@{" not in value
        and not value.endswith((".", "/"))
        and not any(part in {".", ".."} for part in value.split("/"))
    )


def _require_string(mapping: dict[str, Any], key: str, errors: list[str]) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value or not TOKEN_RE.fullmatch(value):
        errors.append(f"{key} must be a non-empty safe token")
        return ""
    return value


def _require_string_list(
    mapping: dict[str, Any], key: str, errors: list[str]
) -> list[str]:
    value = mapping.get(key)
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and TOKEN_RE.fullmatch(item) for item in value
    ):
        errors.append(f"{key} must be a non-empty list of safe tokens")
        return []
    return list(value)


def _validate_core(core: Any, errors: list[str]) -> None:
    if not isinstance(core, dict):
        errors.append("core must be an object")
        return
    if core.get("name") != CORE_NAME:
        errors.append(f"core.name must be {CORE_NAME}")
    if core.get("api_version") != CORE_API_VERSION:
        errors.append(f"core.api_version must be {CORE_API_VERSION}")
    if not isinstance(core.get("version"), str) or not VERSION_RE.fullmatch(
        core["version"]
    ):
        errors.append("core.version must be a semantic version")


def validate_profile(profile: dict[str, Any]) -> None:
    """Validate the generic profile and its project-supplied constraints."""

    errors: list[str] = []
    if not isinstance(profile, dict):
        raise ContractError("profile must be an object")
    if profile.get("schema_version") != 2:
        errors.append("schema_version must be 2")
    _validate_core(profile.get("core"), errors)
    _require_string(profile, "profile_name", errors)

    adapter = profile.get("adapter")
    if not isinstance(adapter, dict):
        errors.append("adapter must be an object")
        adapter = {}
    _require_string(adapter, "name", errors)
    display_name = adapter.get("display_name")
    if (
        not isinstance(display_name, str)
        or not display_name.strip()
        or "\n" in display_name
        or "\r" in display_name
        or ABSOLUTE_RE.search(display_name)
    ):
        errors.append("adapter.display_name must be a non-empty display label")
    _require_string(adapter, "kind", errors)
    runtime = adapter.get("runtime")
    if not isinstance(runtime, dict):
        errors.append("adapter.runtime must be an object")
        runtime = {}
    _require_string(runtime, "contract_module", errors)
    _require_string(runtime, "mcp_module", errors)

    project = profile.get("project")
    if not isinstance(project, dict):
        errors.append("project must be an object")
        project = {}
    _require_string(project, "repository_key", errors)
    default_branch = project.get("default_branch")
    if not _is_safe_ref(default_branch):
        errors.append("project.default_branch must be a safe ref")
    for key in ("build_system", "build_mode", "execution_frontend", "simulator"):
        _require_string(project, key, errors)
    target_kind = _require_string(project, "target_kind", errors)
    if target_kind == "bazel_label":
        if not TARGET_RE.fullmatch(str(project.get("entry_target", ""))):
            errors.append("project.entry_target is not a safe Bazel label")
    else:
        _require_string(project, "entry_target", errors)
    selector_kind = _require_string(project, "selector_kind", errors)
    if selector_kind == "selector_pair":
        if not SELECTOR_RE.fullmatch(str(project.get("test_selector", ""))):
            errors.append("project.test_selector is not a safe selector")
    else:
        _require_string(project, "test_selector", errors)
    workspace_files = project.get("workspace_files", [])
    if not isinstance(workspace_files, list) or not all(
        isinstance(item, str) and item and "/" not in item and "\\" not in item
        for item in workspace_files
    ):
        errors.append("project.workspace_files must be file names")

    execution = profile.get("execution")
    if not isinstance(execution, dict):
        errors.append("execution must be an object")
        execution = {}
    _require_string(execution, "automation_repository", errors)
    _require_string(execution, "automation_ref", errors)
    _require_string(execution, "workflow", errors)
    labels = _require_string_list(execution, "runner_labels", errors)
    if labels and len(set(labels)) != len(labels):
        errors.append("execution.runner_labels must not contain duplicates")
    lsf = execution.get("lsf")
    if not isinstance(lsf, dict):
        errors.append("execution.lsf must be an object")
        lsf = {}
    _require_string(lsf, "queue", errors)
    for key in ("slots", "wall_minutes"):
        value = lsf.get(key)
        if not isinstance(value, int) or value <= 0:
            errors.append(f"execution.lsf.{key} must be a positive integer")
    for key in ("checkout_policy", "runner_policy"):
        _require_string(execution, key, errors)
    _require_string(execution, "map_mode", errors)

    evidence = profile.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("evidence must be an object")
        evidence = {}
    required_file_sets: dict[str, set[str]] = {}
    for key in ("required_files", "factory_required_files"):
        value = evidence.get(key)
        if key == "factory_required_files" and value is None:
            continue
        if not isinstance(value, list) or not value or not all(
            isinstance(item, str) and item and not ABSOLUTE_RE.search(item)
            for item in value
        ):
            errors.append(f"evidence.{key} must be a non-empty relative file list")
        else:
            required_file_sets[key] = set(value)
    statuses = evidence.get("status_values")
    required_statuses = {"pass", "fail", "not_run"}
    if evidence.get("partial_map_is_pass") is False:
        required_statuses.add("pass_with_partial_map")
    if not isinstance(statuses, list) or not required_statuses.issubset(statuses):
        errors.append(
            "evidence.status_values must include " + ", ".join(sorted(required_statuses))
        )
    if evidence.get("partial_map_is_pass") is not False:
        errors.append("partial map must not be promoted to pass")
    if evidence.get("source_free_artifact") is not True:
        errors.append("evidence.source_free_artifact must be true")
    _require_string(evidence, "credential_scan", errors)
    for key in ("require_expected_project_branch", "require_expected_project_sha"):
        if not isinstance(evidence.get(key), bool):
            errors.append(f"evidence.{key} must be boolean")
    identity_fields = evidence.get("map_identity_fields")
    if not isinstance(identity_fields, list) or not identity_fields or not all(
        isinstance(item, str) and TOKEN_RE.fullmatch(item) for item in identity_fields
    ):
        errors.append("evidence.map_identity_fields must be a non-empty safe field list")
    elif len(set(identity_fields)) != len(identity_fields):
        errors.append("evidence.map_identity_fields must not contain duplicates")
    elif not set(identity_fields) <= {"entry_target", "test_selector", "simulator"}:
        errors.append("evidence.map_identity_fields contains an unsupported field")
    artifact_files = evidence.get("artifact_files")
    if not isinstance(artifact_files, dict):
        errors.append("evidence.artifact_files must be an object")
    else:
        artifact_requirements = {
            "map": ("metadata", "verification", "compile_assessment", "required_files"),
        }
        factory_files_configured = "factory" in artifact_files
        if factory_files_configured:
            if "factory_required_files" not in required_file_sets:
                errors.append("evidence.factory_required_files is required for factory evidence")
            artifact_requirements["factory"] = (
                "bundle",
                "summary",
                "submission",
                "lsf_exit",
                "frontend_exit",
                "command",
                "factory_required_files",
            )
        elif "factory_required_files" in evidence or "factory_schema" in evidence:
            errors.append(
                "factory_required_files and factory_schema require evidence.artifact_files.factory"
            )
        for group, keys in artifact_requirements.items():
            values = artifact_files.get(group)
            if not isinstance(values, dict):
                errors.append(f"evidence.artifact_files.{group} must be an object")
                continue
            file_set = required_file_sets.get(keys[-1], set())
            for key in keys[:-1]:
                value = values.get(key)
                if (
                    not isinstance(value, str)
                    or not value
                    or ABSOLUTE_RE.search(value)
                    or value not in file_set
                ):
                    errors.append(
                        f"evidence.artifact_files.{group}.{key} must name a required file"
                    )
    compile_schema = evidence.get("compile_schema")
    if not isinstance(compile_schema, dict):
        errors.append("evidence.compile_schema must be an object")
    else:
        for key in ("completion_key", "exit_code_key", "binary_present_key"):
            _require_string(compile_schema, key, errors)
    factory_schema = evidence.get("factory_schema")
    if factory_schema is not None and not isinstance(factory_schema, dict):
        errors.append("evidence.factory_schema must be an object")
    elif isinstance(factory_schema, dict):
        for key in (
            "passed_key",
            "component_unregistered_key",
            "test_not_found_key",
            "runtime_exit_key",
            "error_count_key",
            "fatal_count_key",
            "simulator_key",
        ):
            _require_string(factory_schema, key, errors)

    safety = profile.get("safety")
    if not isinstance(safety, dict):
        errors.append("safety must be an object")
        safety = {}
    _require_string(safety, "approved_vip", errors)
    host_pattern = safety.get("execution_host_pattern")
    if not isinstance(host_pattern, str) or not host_pattern:
        errors.append("safety.execution_host_pattern is required")
    else:
        try:
            re.compile(host_pattern)
        except re.error:
            errors.append("safety.execution_host_pattern is invalid")
    protected = _require_string_list(safety, "protected_path_parts", errors)
    if protected and len(set(protected)) != len(protected):
        errors.append("safety.protected_path_parts must not contain duplicates")
    if safety.get("free_form_workflow_command") is not False:
        errors.append("free-form workflow commands must be disabled")
    if safety.get("source_mr_merge") is not False:
        errors.append("source MR merge must remain disabled")

    servers = profile.get("mcp_servers")
    if not isinstance(servers, list) or not servers:
        errors.append("mcp_servers must be a non-empty list")
    else:
        names: list[str] = []
        allowed_tools = {"get_profile", "plan_target_run", "review_evidence"}
        for index, server in enumerate(servers):
            if not isinstance(server, dict):
                errors.append(f"mcp_servers[{index}] must be an object")
                continue
            name = _require_string(server, "name", errors)
            names.append(name)
            script = server.get("script")
            if (
                not isinstance(script, str)
                or not script
                or ABSOLUTE_RE.search(script)
                or ".." in script.split("/")
                or "\\" in script
            ):
                errors.append(f"mcp_servers[{index}].script must be relative")
            tools = server.get("tools")
            if (
                not isinstance(tools, list)
                or not tools
                or "get_profile" not in tools
                or not all(isinstance(tool, str) and tool in allowed_tools for tool in tools)
            ):
                errors.append(
                    f"mcp_servers[{index}].tools must include get_profile and use known tools"
                )
            for key in ("startup_timeout_sec", "tool_timeout_sec"):
                value = server.get(key)
                if not isinstance(value, int) or value <= 0:
                    errors.append(f"mcp_servers[{index}].{key} must be positive")
            if not isinstance(server.get("default_enabled"), bool):
                errors.append(f"mcp_servers[{index}].default_enabled must be boolean")
        if len(names) != len(set(names)):
            errors.append("mcp_servers names must be unique")

    roles = profile.get("roles")
    if not isinstance(roles, list) or not roles or not all(
        isinstance(item, str) and TOKEN_RE.fullmatch(item) for item in roles
    ):
        errors.append("roles must be a non-empty list of safe names")
    elif len(roles) != len(set(roles)):
        errors.append("roles must not contain duplicates")

    constraints = profile.get("constraints", {})
    if not isinstance(constraints, dict):
        errors.append("constraints must be an object")
        constraints = {}
    required_equals = constraints.get("required_equals", {})
    if not isinstance(required_equals, dict):
        errors.append("constraints.required_equals must be an object")
    else:
        for dotted_path, expected in required_equals.items():
            if not isinstance(dotted_path, str) or not dotted_path:
                errors.append("constraint path must be a non-empty string")
            elif _get_path(profile, dotted_path) != expected:
                errors.append(f"constraint mismatch: {dotted_path}")

    for value in _walk_strings(profile):
        if ABSOLUTE_RE.search(value) and not value.startswith("//"):
            errors.append(f"profile contains an absolute path: {value}")
            break
    if errors:
        raise ContractError("; ".join(errors))


def load_core_manifest(path: Path | None = None) -> dict[str, Any]:
    path = path or Path(__file__).resolve().parent / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read core manifest: {path}") from exc
    if (
        manifest.get("core_name") != CORE_NAME
        or manifest.get("core_api_version") != CORE_API_VERSION
        or manifest.get("core_version") != CORE_VERSION
    ):
        raise ContractError("core manifest does not match the runtime")
    if manifest.get("bundle_manifest_version") != 1:
        raise ContractError("unsupported core bundle manifest version")
    modules = manifest.get("runtime_modules")
    if not isinstance(modules, list) or not modules or not all(
        isinstance(name, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
        for name in modules
    ):
        raise ContractError("core runtime module manifest is invalid")
    return manifest


def load_profile(path: Path | None = None) -> dict[str, Any]:
    path = path or Path(__file__).resolve().parents[1] / ".agents" / "project_profile.json"
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read profile: {path}") from exc
    validate_profile(profile)
    core_manifest = load_core_manifest()
    expected_core = {
        "name": core_manifest["core_name"],
        "api_version": core_manifest["core_api_version"],
        "version": core_manifest["core_version"],
    }
    if profile["core"] != expected_core:
        raise ContractError("profile core metadata does not match runtime")
    return profile


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
    project = profile["project"]
    if project_branch is None:
        project_branch = project["default_branch"]
    if not _is_safe_ref(project_branch):
        raise ContractError("project_branch is not safe")
    if map_profile is None:
        map_profile = f"{project['execution_frontend']}-target-{project_sha[:8]}"
    if not PROFILE_RE.fullmatch(map_profile):
        raise ContractError("map_profile is not safe")
    execution = profile["execution"]
    lsf = execution["lsf"]
    return {
        "profile_name": profile["profile_name"],
        "core": profile["core"],
        "adapter": profile["adapter"]["name"],
        "project_branch": project_branch,
        "expected_project_sha": project_sha,
        "map_mode": execution["map_mode"],
        "entry_target": project["entry_target"],
        "test_selector": project["test_selector"],
        "execution_frontend": project["execution_frontend"],
        "simulator": project["simulator"],
        "map_profile": map_profile,
        "keep_workdir": execution.get("keep_workdir", False),
        "automation_repository": execution["automation_repository"],
        "automation_ref": execution["automation_ref"],
        "workflow": execution["workflow"],
        "runner_labels": list(execution["runner_labels"]),
        "lsf_queue": lsf["queue"],
        "lsf_slots": lsf["slots"],
        "lsf_wall_minutes": lsf["wall_minutes"],
    }


def _read_json(artifact_dir: Path, name: str) -> dict[str, Any]:
    path = artifact_dir / name
    if not path.is_file():
        raise ContractError(f"missing evidence file: {name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid evidence JSON: {name}") from exc
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
    except (OSError, ValueError) as exc:
        raise ContractError(f"invalid exit code: {name}") from exc


def _all_zero(value: Any) -> bool:
    values = value if isinstance(value, list) else [value]
    return bool(values) and all(str(item) == "0" for item in values)


def _check_expected(
    binding_errors: list[str],
    actual: Any,
    expected: Any,
    label: str,
) -> None:
    if actual != expected:
        binding_errors.append(f"{label} mismatch")


def _record_missing_files(
    binding_errors: list[str], artifact_dir: Path, names: list[str]
) -> None:
    for name in names:
        if not (artifact_dir / name).is_file():
            binding_errors.append(f"missing evidence file: {name}")


def _summarize_factory_evidence(
    profile: dict[str, Any],
    artifact_dir: Path,
    *,
    expected_project_branch: str | None = None,
    expected_project_sha: str | None = None,
) -> dict[str, Any]:
    evidence = profile["evidence"]
    factory_files = evidence["artifact_files"]["factory"]
    bundle = _read_json(artifact_dir, factory_files["bundle"])
    factory = _read_json(artifact_dir, factory_files["summary"])
    submission = _read_key_value_file(artifact_dir, factory_files["submission"])
    frontend_exit_code = _read_exit_code(artifact_dir, factory_files["frontend_exit"])
    lsf_exit_code = _read_exit_code(artifact_dir, factory_files["lsf_exit"])
    command_path = artifact_dir / factory_files["command"]
    if not command_path.is_file():
        raise ContractError(f"missing evidence file: {factory_files['command']}")
    try:
        command_text = command_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ContractError(
            f"cannot read evidence file: {factory_files['command']}"
        ) from exc
    project = profile["project"]
    binding_errors: list[str] = []
    _record_missing_files(binding_errors, artifact_dir, evidence["factory_required_files"])
    if evidence["require_expected_project_branch"] and expected_project_branch is None:
        binding_errors.append("expected project branch is required")
    if evidence["require_expected_project_sha"] and expected_project_sha is None:
        binding_errors.append("expected project SHA is required")
    _check_expected(binding_errors, bundle.get("status"), "passed", "bundle status")
    _check_expected(binding_errors, bundle.get("source_free_bundle"), True, "bundle source policy")
    _check_expected(binding_errors, bundle.get("credential_scan"), "passed", "bundle credential scan")
    _check_expected(binding_errors, bundle.get("adapter"), profile["adapter"]["name"], "bundle adapter")
    _check_expected(binding_errors, bundle.get("core_version"), profile["core"]["version"], "bundle core version")
    _check_expected(binding_errors, bundle.get("profile_name"), profile["profile_name"], "bundle profile")
    _check_expected(binding_errors, bundle.get("entry_target"), project["entry_target"], "bundle entry target")
    _check_expected(binding_errors, bundle.get("test_selector"), project["test_selector"], "bundle test selector")
    _check_expected(binding_errors, submission.get("agent_bundle_status"), "validated", "agent bundle status")
    project_branch = submission.get("project_branch", "")
    if not _is_safe_ref(project_branch):
        binding_errors.append("project branch is not safe")
    if expected_project_branch is not None:
        if not _is_safe_ref(expected_project_branch):
            binding_errors.append("expected project branch is not safe")
        else:
            _check_expected(binding_errors, project_branch, expected_project_branch, "project branch")
    project_commit = submission.get("project_commit", "")
    if not SHA_RE.fullmatch(project_commit):
        binding_errors.append("project commit is not a full lowercase SHA")
    if expected_project_sha is not None:
        if not SHA_RE.fullmatch(expected_project_sha):
            binding_errors.append("expected project SHA is not a full lowercase SHA")
        else:
            _check_expected(binding_errors, project_commit, expected_project_sha, "project commit")
    _check_expected(binding_errors, submission.get("test_selector"), project["test_selector"], "test selector")
    _check_expected(binding_errors, submission.get("source_worktree_writes"), "none", "source checkout writes")
    if not SHA_RE.fullmatch(submission.get("agent_bundle_ref", "")):
        binding_errors.append("agent bundle ref is not a full lowercase SHA")
    host_pattern = profile["safety"]["execution_host_pattern"]
    if not re.fullmatch(host_pattern, submission.get("requested_host", "")):
        binding_errors.append("requested host is not approved")
    lsf = profile["execution"]["lsf"]
    _check_expected(binding_errors, submission.get("lsf_queue"), lsf["queue"], "LSF queue")
    _check_expected(binding_errors, submission.get("lsf_slots"), str(lsf["slots"]), "LSF slots")
    expected_user = lsf.get("user")
    if expected_user is not None:
        _check_expected(
            binding_errors, submission.get("execution_user"), expected_user, "execution user"
        )
    if not re.fullmatch(r"[0-9]+", submission.get("lsf_job_id", "")):
        binding_errors.append("LSF job ID is missing or invalid")
    payload_exit_code = submission.get("payload_exit_code")
    if payload_exit_code is None:
        binding_errors.append("payload exit code is missing")
    elif payload_exit_code != "0":
        binding_errors.append("payload exit code is not zero")
    frontend = project["execution_frontend"]
    if not re.search(
        rf"(?<![A-Za-z0-9_]){re.escape(frontend)}(?![A-Za-z0-9_])", command_text
    ):
        binding_errors.append("execution frontend is not present in command")

    factory_schema = evidence.get("factory_schema", {})
    passed_key = factory_schema["passed_key"]
    component_key = factory_schema["component_unregistered_key"]
    test_key = factory_schema["test_not_found_key"]
    runtime_exit_key = factory_schema["runtime_exit_key"]
    error_key = factory_schema["error_count_key"]
    fatal_key = factory_schema["fatal_count_key"]
    simulator_key = factory_schema["simulator_key"]
    _check_expected(
        binding_errors,
        factory.get(simulator_key),
        project["simulator"],
        "factory simulator",
    )
    factory_ok = (
        factory.get(passed_key) is True
        and factory.get(component_key) is False
        and factory.get(test_key) is False
        and factory.get(runtime_exit_key) == 0
        and _all_zero(factory.get(error_key))
        and _all_zero(factory.get(fatal_key))
        and lsf_exit_code == 0
        and frontend_exit_code == 0
        and not binding_errors
    )
    return {
        "overall": "pass" if factory_ok else "fail",
        "evidence_kind": "factory_validation",
        "profile_name": profile["profile_name"],
        "adapter": profile["adapter"]["name"],
        "core_version": profile["core"]["version"],
        "bazel_map": "not_run",
        "compile": "pass" if frontend_exit_code == 0 and not binding_errors else "fail",
        "simulation": "pass" if factory_ok else "fail",
        "coverage": "not_run",
        "binding_errors": binding_errors,
        "commit_sha": project_commit,
        "project_branch": project_branch,
        "agent_bundle_ref": submission.get("agent_bundle_ref"),
        "entry_target": project["entry_target"],
        "test_selector": submission.get("test_selector"),
        "simulator": project["simulator"],
        "lsf_job_id": submission.get("lsf_job_id"),
        "execution_host": submission.get("requested_host"),
        "lsf_exit_code": lsf_exit_code,
        "execution_frontend_exit_code": frontend_exit_code,
        "uvm_error_count": factory.get(error_key),
        "uvm_fatal_count": factory.get(fatal_key),
    }


def summarize_evidence(
    profile: dict[str, Any],
    artifact_dir: Path,
    *,
    expected_project_branch: str | None = None,
    expected_project_sha: str | None = None,
) -> dict[str, Any]:
    validate_profile(profile)
    factory_files = profile["evidence"]["artifact_files"].get("factory", {})
    factory_summary = factory_files.get("summary")
    if isinstance(factory_summary, str) and (artifact_dir / factory_summary).is_file():
        return _summarize_factory_evidence(
            profile,
            artifact_dir,
            expected_project_branch=expected_project_branch,
            expected_project_sha=expected_project_sha,
        )
    map_files = profile["evidence"]["artifact_files"]["map"]
    metadata = _read_json(artifact_dir, map_files["metadata"])
    verification = _read_json(artifact_dir, map_files["verification"])
    compile_assessment = _read_json(artifact_dir, map_files["compile_assessment"])
    execution = metadata.get("execution", {})
    project = profile["project"]
    evidence = profile["evidence"]
    binding_errors: list[str] = []
    if evidence["require_expected_project_branch"] and expected_project_branch is None:
        binding_errors.append("expected project branch is required")
    if evidence["require_expected_project_sha"] and expected_project_sha is None:
        binding_errors.append("expected project SHA is required")
    if not isinstance(execution, dict):
        binding_errors.append("metadata.execution is not an object")
        execution = {}
    _record_missing_files(binding_errors, artifact_dir, evidence["required_files"])
    for key in evidence["map_identity_fields"]:
        actual = execution.get(key)
        if actual is None:
            actual = verification.get(key)
        if actual is None:
            actual = metadata.get(key)
        if actual is None:
            binding_errors.append(f"missing map identity field: {key}")
            continue
        expected = {
            "entry_target": project["entry_target"],
            "test_selector": project["test_selector"],
            "simulator": project["simulator"],
        }.get(key)
        if expected is None:
            binding_errors.append(f"unsupported map identity field: {key}")
        else:
            _check_expected(binding_errors, actual, expected, f"map identity {key}")
    metadata_commit = metadata.get("commit_sha")
    if not SHA_RE.fullmatch(str(metadata_commit or "")):
        binding_errors.append("metadata commit is not a full lowercase SHA")
    if expected_project_sha is not None:
        _check_expected(binding_errors, metadata_commit, expected_project_sha, "metadata commit")
    project_branch = execution.get("project_branch")
    if project_branch is None:
        binding_errors.append("missing execution.project_branch")
        project_branch = ""
    elif not _is_safe_ref(project_branch):
        binding_errors.append("execution.project_branch is not safe")
    if expected_project_branch is not None:
        _check_expected(binding_errors, project_branch, expected_project_branch, "execution.project_branch")
    host_pattern = profile["safety"]["execution_host_pattern"]
    execution_host = execution.get("execution_host")
    if not isinstance(execution_host, str) or not re.fullmatch(
        host_pattern, execution_host
    ):
        binding_errors.append("execution host is not approved")
    lsf = profile["execution"]["lsf"]
    _check_expected(binding_errors, execution.get("lsf_queue"), lsf["queue"], "LSF queue")
    _check_expected(binding_errors, execution.get("lsf_slots"), lsf["slots"], "LSF slots")
    expected_user = lsf.get("user")
    if expected_user is not None:
        _check_expected(
            binding_errors, execution.get("execution_user"), expected_user, "execution user"
        )
    if not re.fullmatch(r"[0-9]+", str(execution.get("lsf_job_id", ""))):
        binding_errors.append("LSF job ID is missing or invalid")
    frontend = project["execution_frontend"]
    compile_mode = execution.get("compile_mode")
    if not isinstance(compile_mode, str) or not re.match(
        rf"^{re.escape(frontend)}(?:\s|$)", compile_mode
    ):
        binding_errors.append("execution frontend is not approved")
    if verification.get("status") != "passed":
        binding_errors.append("verification status is not passed")
    if verification.get("credential_scan") != "passed":
        binding_errors.append("credential scan did not pass")
    if verification.get("source_free_artifact") is not True:
        binding_errors.append("artifact is not source-free")

    compile_cfg = profile["evidence"].get("compile_schema", {})
    completion_key = compile_cfg["completion_key"]
    exit_key = compile_cfg["exit_code_key"]
    binary_key = compile_cfg["binary_present_key"]
    compile_ok = (
        compile_assessment.get(completion_key) is True
        and compile_assessment.get(exit_key) == 0
        and compile_assessment.get(binary_key) is True
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
        "evidence_kind": "target_map",
        "profile_name": profile["profile_name"],
        "adapter": profile["adapter"]["name"],
        "core_version": profile["core"]["version"],
        "bazel_map": "partial" if query_partial else "complete",
        "compile": "pass" if compile_ok and not binding_errors else "fail",
        "simulation": "not_run",
        "coverage": "not_run",
        "binding_errors": binding_errors,
        "commit_sha": metadata_commit,
        "project_branch": project_branch,
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
        "adapter": profile["adapter"]["name"],
        "core": profile["core"],
        "entry_target": profile["project"]["entry_target"],
        "test_selector": profile["project"]["test_selector"],
        "execution_frontend": profile["project"]["execution_frontend"],
        "simulator": profile["project"]["simulator"],
        "workflow": profile["execution"]["workflow"],
        "mcp_servers": tuple(server["name"] for server in profile["mcp_servers"]),
        "roles": tuple(profile["roles"]),
    }
