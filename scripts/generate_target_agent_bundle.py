#!/usr/bin/env python3
"""Generate Claude Code and Codex projections from one RTL-DV adapter.

The reusable ``agent_core`` package owns generation support and the runtime
contract. A project contributes only a profile, role/skill contracts, and a
thin runtime adapter under ``.agents/targets/<project>``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / ".agents/targets/xinanriver"
CORE_DIR = ROOT / "agent_core"
BUNDLE_MANIFEST_VERSION = 1
SECRET_RE = re.compile(
    r"(?i)(?:gh[opsu]_[A-Za-z0-9_]{12,}|glpat-[A-Za-z0-9_-]{12,}|"
    r"(?:token|password|secret)\s*[=:])"
)
ABSOLUTE_RE = re.compile(r"(?:^[A-Za-z]:[\\/])|(?:^/(?:nfs|home|workspace)/)")
ROOT_DOCS = {"AGENTS.md", "CLAUDE.md"}
MANAGED_ROOTS = (
    ".agents/",
    ".claude/",
    ".codex/",
    "agent_core/",
    "scripts/",
)


class BundleError(ValueError):
    """Raised when an adapter cannot produce a safe bundle."""


def _core_import_path() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def parse_contract(path: Path) -> tuple[str, str, list[str], list[str], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise BundleError(f"{path}: missing frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise BundleError(f"{path}: unterminated frontmatter")
    frontmatter = text[4:end]
    body = text[end + 5 :].strip() + "\n"
    name = ""
    description = ""
    lists: dict[str, list[str]] = {"mcp_servers": [], "skills": []}
    active_list: str | None = None
    for raw_line in frontmatter.splitlines():
        line = raw_line.strip()
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
            active_list = None
        elif line.startswith("description:"):
            description = line.split(":", 1)[1].strip()
            active_list = None
        elif line.endswith(":") and line[:-1] in lists:
            active_list = line[:-1]
        elif active_list and line.startswith("-"):
            lists[active_list].append(line[1:].strip())
        elif line:
            active_list = None
    if not name or not description or path.stem != name:
        raise BundleError(f"{path}: invalid role metadata")
    return name, description, lists["mcp_servers"], lists["skills"], body


def load_profile(profile_dir: Path) -> dict[str, Any]:
    _core_import_path()
    from agent_core.dv_contract import load_core_manifest, validate_profile

    try:
        profile = json.loads((profile_dir / "profile.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError(f"cannot read profile: {profile_dir / 'profile.json'}") from exc
    validate_profile(profile)
    core_manifest = load_core_manifest()
    expected_core = {
        "name": core_manifest["core_name"],
        "api_version": core_manifest["core_api_version"],
        "version": core_manifest["core_version"],
    }
    if profile.get("core") != expected_core:
        raise BundleError("profile core metadata does not match the bundled runtime")
    return profile


def load_core_files() -> dict[str, str]:
    manifest_path = CORE_DIR / "manifest.json"
    try:
        core_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError(f"cannot read core manifest: {manifest_path}") from exc
    runtime_modules = core_manifest.get("runtime_modules")
    if not isinstance(runtime_modules, list) or not runtime_modules or not all(
        isinstance(name, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
        for name in runtime_modules
    ):
        raise BundleError("core manifest runtime_modules must be safe module names")
    required = ("__init__.py", "manifest.json", "README.md") + tuple(
        f"{name}.py" for name in runtime_modules
    )
    if len(set(required)) != len(required):
        raise BundleError("core manifest runtime_modules contain duplicates")
    files: dict[str, str] = {}
    for name in required:
        path = CORE_DIR / name
        if not path.is_file():
            raise BundleError(f"missing reusable core file: {path}")
        files[name] = path.read_text(encoding="utf-8")
    _core_import_path()
    from agent_core.dv_contract import load_core_manifest

    load_core_manifest(CORE_DIR / "manifest.json")
    return files


def load_roles(profile_dir: Path, profile: dict[str, Any]) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = []
    expected_names = profile["roles"]
    server_names = {item["name"] for item in profile["mcp_servers"]}
    agents_dir = profile_dir / "agents"
    actual_names = {path.stem for path in agents_dir.glob("*.md")}
    if actual_names != set(expected_names):
        missing = sorted(set(expected_names) - actual_names)
        extra = sorted(actual_names - set(expected_names))
        raise BundleError(
            f"canonical role/profile mismatch: missing={missing}, extra={extra}"
        )
    skill_names = {
        path.name
        for path in (profile_dir / "skills").iterdir()
        if path.is_dir()
    }
    for name in expected_names:
        path = profile_dir / "agents" / f"{name}.md"
        if not path.is_file():
            raise BundleError(f"missing canonical role: {path}")
        role_name, description, mcp_servers, skills, body = parse_contract(path)
        unknown_servers = sorted(set(mcp_servers) - server_names)
        unknown_skills = sorted(set(skills) - skill_names)
        if unknown_servers:
            raise BundleError(f"{path}: unknown MCP servers: {unknown_servers}")
        if unknown_skills:
            raise BundleError(f"{path}: unknown skills: {unknown_skills}")
        roles.append(
            {
                "name": role_name,
                "description": description,
                "mcp_servers": tuple(mcp_servers),
                "skills": tuple(skills),
                "body": body,
                "source": path,
            }
        )
    if [role["name"] for role in roles] != expected_names:
        raise BundleError("profile role order does not match canonical role files")
    return roles


def load_skills(profile_dir: Path) -> dict[str, str]:
    skills: dict[str, str] = {}
    skill_root = profile_dir / "skills"
    if not skill_root.is_dir():
        raise BundleError(f"missing canonical skill directory: {skill_root}")
    for skill_dir in sorted(skill_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        source = skill_dir / "SKILL.md"
        if not source.is_file():
            raise BundleError(f"skill directory lacks SKILL.md: {skill_dir}")
        skills[skill_dir.name] = source.read_text(encoding="utf-8")
    if not skills:
        raise BundleError("adapter must provide at least one skill")
    return skills


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_codex_role(role: dict[str, Any], skills: dict[str, str]) -> str:
    body = role["body"]
    if "'''" in body:
        raise BundleError(f"role body contains unsupported TOML delimiter: {role['name']}")
    skill_note = ", ".join(role["skills"]) or "none"
    skill_bodies: list[str] = []
    for skill_name in role["skills"]:
        skill_body = skills[skill_name].rstrip()
        if "'''" in skill_body:
            raise BundleError(f"skill body contains unsupported TOML delimiter: {skill_name}")
        skill_bodies.append(f"\n## Skill contract: {skill_name}\n\n{skill_body}")
    return (
        f"name = {toml_string(role['name'])}\n"
        f"description = {toml_string(role['description'])}\n"
        "developer_instructions = '''\n"
        f"{body.rstrip()}\n"
        f"{''.join(skill_bodies)}\n"
        "'''\n"
        f"# MCP servers: {', '.join(role['mcp_servers'])}\n"
        f"# Skill contracts: {skill_note}\n"
    )


def render_agents_md(profile: dict[str, Any]) -> str:
    project = profile["project"]
    execution = profile["execution"]
    adapter = profile["adapter"]
    core = profile["core"]
    return f"""# {adapter['display_name']} DV agent contract

This file is generated from the project adapter and the reusable
`{core['name']}` core. The adapter owns project facts; the core owns safe
workflow-input and evidence semantics.

- Adapter: `{adapter['name']}`
- Core: `{core['name']}@{core['version']}`
- Entry target: `{project['entry_target']}`
- Test selector: `{project['test_selector']}`
- Build authority: `{project['build_system']} / {project['build_mode']}`
- Execution frontend: `{project['execution_frontend']}`
- Execution: `{execution['automation_repository']} / {execution['workflow']}`
- Runner policy: isolated exact commit, then the profile-defined execution host

Use the source-free map first. Keep analysis, compile, simulation, regression,
and coverage as separate evidence stages. Claude Code and Codex files are
projections; edit only the canonical adapter or reusable core.
"""


def render_claude_md(profile: dict[str, Any]) -> str:
    adapter = profile["adapter"]
    core = profile["core"]
    return f"""# {adapter['display_name']} DV agent entrypoint

Read `AGENTS.md` and `.agents/project_profile.json` before DV work. Load the
smallest matching role and skill. Use the fixed profile workflow and preserve
the evidence state distinctions defined by the `{core['name']}` core.

The `.claude/` files are generated projections. Edit canonical adapter files
under `.agents/targets/{adapter['name']}/` or the pinned `agent_core/` package,
then regenerate them.
"""


def render_mcp_manifest(profile: dict[str, Any]) -> str:
    return json.dumps(
        {
            "schema_version": 2,
            "core": profile["core"],
            "adapter": profile["adapter"]["name"],
            "launcher": "python3",
            "client_prefix": "",
            "servers": profile["mcp_servers"],
        },
        indent=2,
        ensure_ascii=False,
    ) + "\n"


def _mcp_args(server: dict[str, Any]) -> list[str]:
    return [
        server["script"],
        "--server",
        server["name"],
        "--profile",
        ".agents/project_profile.json",
    ]


def render_claude_mcp(profile: dict[str, Any]) -> str:
    servers = {
        server["name"]: {
            "type": "stdio",
            "command": "python3",
            "args": _mcp_args(server),
            "enabled": server["default_enabled"],
        }
        for server in profile["mcp_servers"]
    }
    return json.dumps({"mcpServers": servers}, indent=2, ensure_ascii=False) + "\n"


def render_codex_config(profile: dict[str, Any]) -> str:
    lines = [
        "# Generated from the canonical adapter/profile and agent_core.",
        "",
    ]
    for server in profile["mcp_servers"]:
        lines.extend(
            [
                f"[mcp_servers.{server['name']}]",
                f"enabled = {str(server['default_enabled']).lower()}",
                'command = "python3"',
                f"args = {json.dumps(_mcp_args(server), ensure_ascii=False)}",
                f"startup_timeout_sec = {server['startup_timeout_sec']}",
                f"tool_timeout_sec = {server['tool_timeout_sec']}",
                "",
            ]
        )
    return "\n".join(lines)


def _profile_digest(profile: dict[str, Any]) -> str:
    payload = json.dumps(profile, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _safe_relative(value: str) -> bool:
    path = Path(value)
    return not path.is_absolute() and not any(part in {"", ".", ".."} for part in path.parts)


def render_agent_manifest(
    profile: dict[str, Any],
    roles: list[dict[str, Any]],
    skills: dict[str, str],
    managed_hashes: dict[str, str],
) -> str:
    mcp_signature = [
        {
            "name": server["name"],
            "script": server["script"],
            "tools": list(server["tools"]),
            "args": _mcp_args(server),
            "default_enabled": server["default_enabled"],
            "startup_timeout_sec": server["startup_timeout_sec"],
            "tool_timeout_sec": server["tool_timeout_sec"],
        }
        for server in profile["mcp_servers"]
    ]
    managed_paths = sorted(set(managed_hashes) | {".agents/agent-manifest.json"})
    payload = {
        "manifest_version": BUNDLE_MANIFEST_VERSION,
        "core": profile["core"],
        "adapter": profile["adapter"],
        "profile_name": profile["profile_name"],
        "profile_sha256": _profile_digest(profile),
        "canonical_adapter": f".agents/targets/{profile['adapter']['name']}",
        "projections": ["claude", "codex", "mcp"],
        "mcp_servers": mcp_signature,
        "roles": [
            {
                "name": role["name"],
                "mcp_servers": list(role["mcp_servers"]),
                "skills": list(role["skills"]),
            }
            for role in roles
        ],
        "skills": sorted(skills),
        "managed_paths": managed_paths,
        "managed_sha256": managed_hashes,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def expected_files(profile_dir: Path, output_dir: Path) -> dict[Path, str]:
    profile = load_profile(profile_dir)
    roles = load_roles(profile_dir, profile)
    skills = load_skills(profile_dir)
    core_files = load_core_files()
    files: dict[Path, str] = {
        output_dir / "AGENTS.md": render_agents_md(profile),
        output_dir / "CLAUDE.md": render_claude_md(profile),
        output_dir / ".agents/project_profile.json": json.dumps(profile, indent=2) + "\n",
        output_dir / ".agents/mcp-servers.json": render_mcp_manifest(profile),
        output_dir / ".mcp.json": render_claude_mcp(profile),
        output_dir / ".codex/config.toml": render_codex_config(profile),
    }
    for name, content in core_files.items():
        files[output_dir / "agent_core" / name] = content
    adapter_output = output_dir / ".agents/targets" / profile["adapter"]["name"]
    if not profile_dir.is_dir():
        raise BundleError(f"missing adapter directory: {profile_dir}")
    for adapter_path in sorted(profile_dir.rglob("*")):
        if adapter_path.is_symlink():
            raise BundleError(f"adapter source must not contain symlinks: {adapter_path}")
        if not adapter_path.is_file():
            continue
        if adapter_path.name == "__pycache__" or adapter_path.suffix == ".pyc":
            continue
        relative = adapter_path.relative_to(profile_dir)
        files[adapter_output / relative] = adapter_path.read_text(encoding="utf-8")
    for role in roles:
        canonical = role["source"].read_text(encoding="utf-8")
        files[output_dir / ".agents/agents" / f"{role['name']}.md"] = canonical
        files[output_dir / ".claude/agents" / f"{role['name']}.md"] = canonical
        files[output_dir / ".codex/agents" / f"{role['name']}.toml"] = render_codex_role(
            role, skills
        )
    for skill_name, content in skills.items():
        files[output_dir / ".agents/skills" / skill_name / "SKILL.md"] = content
        files[output_dir / ".claude/skills" / skill_name / "SKILL.md"] = content
    runtime_dir = profile_dir / "runtime"
    runtime_paths = sorted(runtime_dir.glob("*.py"))
    declared_runtime = {
        profile["adapter"]["runtime"]["contract_module"] + ".py",
        profile["adapter"]["runtime"]["mcp_module"] + ".py",
    }
    actual_runtime = {path.name for path in runtime_paths}
    if not declared_runtime <= actual_runtime:
        raise BundleError(
            "adapter runtime declaration does not match runtime files: "
            f"missing={sorted(declared_runtime - actual_runtime)}"
        )
    for runtime_path in runtime_paths:
        files[output_dir / "scripts" / runtime_path.name] = runtime_path.read_text(
            encoding="utf-8"
        )

    managed_hashes = {
        path.relative_to(output_dir).as_posix(): _content_sha256(content)
        for path, content in files.items()
    }
    files[output_dir / ".agents/agent-manifest.json"] = render_agent_manifest(
        profile, roles, skills, managed_hashes
    )
    return files


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _check_generated_content(files: dict[Path, str]) -> None:
    for path, content in files.items():
        if SECRET_RE.search(content):
            raise BundleError(f"credential-like text in generated file: {path}")
        for line in content.splitlines():
            if ABSOLUTE_RE.search(line) and not line.lstrip().startswith("//"):
                raise BundleError(f"absolute path in generated file: {path}")


def _load_previous_manifest(output_dir: Path) -> dict[str, Any] | None:
    manifest_path = output_dir / ".agents/agent-manifest.json"
    if manifest_path.is_symlink():
        raise BundleError("agent manifest must not be a symlink")
    if not manifest_path.exists():
        return None
    try:
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError("existing agent manifest is invalid") from exc
    if not isinstance(previous, dict):
        raise BundleError("existing agent manifest must be an object")
    return previous


def _verified_previous_manifest(
    previous: dict[str, Any] | None, output_dir: Path, profile: dict[str, Any]
) -> tuple[bool, set[str]]:
    if previous is None:
        return False, set()
    if previous.get("manifest_version") != BUNDLE_MANIFEST_VERSION:
        return False, set()
    previous_core = previous.get("core")
    previous_adapter = previous.get("adapter")
    if (
        not isinstance(previous_core, dict)
        or previous_core.get("name") != profile["core"]["name"]
        or not isinstance(previous_adapter, dict)
        or previous_adapter.get("name") != profile["adapter"]["name"]
    ):
        return False, set()
    previous_paths = previous.get("managed_paths", [])
    previous_hashes = previous.get("managed_sha256", {})
    if (
        not isinstance(previous_paths, list)
        or not all(isinstance(value, str) and _safe_relative(value) for value in previous_paths)
        or not isinstance(previous_hashes, dict)
    ):
        return False, set()
    path_set = set(previous_paths)
    hash_set = set(previous_hashes)
    if ".agents/agent-manifest.json" not in path_set:
        path_set.add(".agents/agent-manifest.json")
    if hash_set != path_set - {".agents/agent-manifest.json"}:
        return False, set()
    for relative, digest in previous_hashes.items():
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return False, set()
        path = output_dir / relative
        if path.is_symlink() or not path.is_file():
            return False, set()
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return False, set()
        if actual != digest:
            return False, set()
    return True, path_set


def _stale_managed_paths(
    previous: dict[str, Any] | None, expected: set[str]
) -> list[str]:
    if previous is None:
        return []
    previous_paths = previous.get("managed_paths", [])
    if not isinstance(previous_paths, list):
        raise BundleError("existing agent manifest has invalid managed_paths")
    stale = []
    for value in previous_paths:
        if not isinstance(value, str):
            raise BundleError("existing agent manifest has invalid managed path")
        if value in expected:
            continue
        if value.startswith(MANAGED_ROOTS):
            stale.append(value)
    return sorted(stale)


def _unregistered_managed_paths(
    output_dir: Path, expected: set[str], profile: dict[str, Any]
) -> list[str]:
    prefixes = (
        ".agents/agents",
        ".agents/skills",
        f".agents/targets/{profile['adapter']['name']}",
        ".claude/agents",
        ".claude/skills",
        ".codex/agents",
        "agent_core",
    )
    stale: list[str] = []
    for prefix in prefixes:
        base = output_dir / prefix
        if base.is_symlink():
            raise BundleError(f"managed generated directory must not be a symlink: {base}")
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_symlink():
                raise BundleError(f"managed generated path must not be a symlink: {path}")
            if not path.is_file() or path.suffix == ".pyc" or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(output_dir).as_posix()
            if relative not in expected:
                stale.append(relative)
    return sorted(set(stale))


def run(
    profile_dir: Path,
    output_dir: Path,
    write: bool,
    *,
    allow_root_overwrite: bool = False,
    allow_managed_overwrite: bool = False,
) -> int:
    files = expected_files(profile_dir, output_dir)
    _check_generated_content(files)
    expected_rel = {_relative(path, output_dir) for path in files}
    previous_value = _load_previous_manifest(output_dir)
    previous_verified, previous_managed = _verified_previous_manifest(
        previous_value, output_dir, load_profile(profile_dir)
    )
    stale = _stale_managed_paths(previous_value, expected_rel)
    stale.extend(_unregistered_managed_paths(output_dir, expected_rel, load_profile(profile_dir)))
    if stale:
        raise BundleError(
            "stale generated files detected; remove them deliberately or update "
            f"the adapter: {', '.join(sorted(set(stale)))}"
        )
    mismatches: list[Path] = []
    collisions: list[Path] = []
    for path, content in files.items():
        if path.is_symlink():
            raise BundleError(f"generated output path must not be a symlink: {path}")
        actual = path.read_text(encoding="utf-8") if path.is_file() else None
        if actual == content:
            continue
        mismatches.append(path)
        relative = _relative(path, output_dir)
        if not write or actual is None:
            continue
        if relative in ROOT_DOCS and not allow_root_overwrite:
            if not (previous_verified and relative in previous_managed):
                collisions.append(path)
        elif not allow_managed_overwrite:
            if not (previous_verified and relative in previous_managed):
                collisions.append(path)
    if collisions:
        names = ", ".join(_relative(path, output_dir) for path in collisions)
        raise BundleError(
            f"existing consumer files would be overwritten ({names}); "
            "pass --allow-root-overwrite for reviewed root docs or "
            "--allow-managed-overwrite for reviewed generated paths"
        )
    if mismatches and not write:
        for path in mismatches:
            print(f"[TARGET-AGENT] OUT-OF-DATE: {path}", file=sys.stderr)
        return 2
    if write:
        for path in mismatches:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8", newline="") as handle:
                handle.write(files[path])
        print(f"[TARGET-AGENT] wrote {len(mismatches)} generated files")
    else:
        print("[TARGET-AGENT] bundle is synchronized")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output-dir", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument(
        "--allow-root-overwrite",
        action="store_true",
        help="allow replacing an existing AGENTS.md or CLAUDE.md after review",
    )
    parser.add_argument(
        "--allow-managed-overwrite",
        action="store_true",
        help="allow replacing reviewed generated files without a verified manifest",
    )
    args = parser.parse_args()
    try:
        return run(
            args.profile_dir,
            args.output_dir,
            args.write,
            allow_root_overwrite=args.allow_root_overwrite,
            allow_managed_overwrite=args.allow_managed_overwrite,
        )
    except (OSError, KeyError, json.JSONDecodeError, BundleError) as exc:
        print(f"[TARGET-AGENT] ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
