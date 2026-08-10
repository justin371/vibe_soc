#!/usr/bin/env python3
"""Generate a portable Claude Code/Codex XinAnRiver agent bundle.

The target profile is canonical. Claude and Codex files are projections of the
same role, skill, MCP, and evidence contract; generated files are never used as
inputs to the generator.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / ".agents/targets/xinanriver"


class BundleError(ValueError):
    pass


def parse_contract(path: Path) -> tuple[str, str, list[str], str]:
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
    mcp_servers: list[str] = []
    in_mcp = False
    for raw_line in frontmatter.splitlines():
        line = raw_line.strip()
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
            in_mcp = False
        elif line.startswith("description:"):
            description = line.split(":", 1)[1].strip()
            in_mcp = False
        elif line == "mcp_servers:":
            in_mcp = True
        elif in_mcp and line.startswith("-"):
            mcp_servers.append(line[1:].strip())
        elif line and not line.startswith("-"):
            in_mcp = False
    if not name or not description or path.stem != name:
        raise BundleError(f"{path}: invalid role metadata")
    return name, description, mcp_servers, body


def load_profile(profile_dir: Path) -> dict[str, Any]:
    profile = json.loads((profile_dir / "profile.json").read_text(encoding="utf-8"))
    runtime_dir = str((profile_dir / "runtime").resolve())
    if runtime_dir not in sys.path:
        sys.path.insert(0, runtime_dir)
    from xinanriver_dv_contract import validate_profile

    validate_profile(profile)
    return profile


def load_roles(profile_dir: Path, profile: dict[str, Any]) -> list[dict[str, Any]]:
    roles = []
    expected_names = profile["roles"]
    for name in expected_names:
        path = profile_dir / "agents" / f"{name}.md"
        if not path.is_file():
            raise BundleError(f"missing canonical role: {path}")
        role_name, description, mcp_servers, body = parse_contract(path)
        unknown = sorted(set(mcp_servers) - {item["name"] for item in profile["mcp_servers"]})
        if unknown:
            raise BundleError(f"{path}: unknown MCP servers: {unknown}")
        roles.append(
            {
                "name": role_name,
                "description": description,
                "mcp_servers": tuple(mcp_servers),
                "body": body,
                "source": path,
            }
        )
    if [role["name"] for role in roles] != expected_names:
        raise BundleError("profile role order does not match canonical role files")
    return roles


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_codex_role(role: dict[str, Any]) -> str:
    body = role["body"]
    if "'''" in body:
        raise BundleError(f"role body contains unsupported TOML delimiter: {role['name']}")
    return (
        f"name = {toml_string(role['name'])}\n"
        f"description = {toml_string(role['description'])}\n"
        "developer_instructions = '''\n"
        f"{body.rstrip()}\n"
        "'''\n"
        f"# MCP servers: {', '.join(role['mcp_servers'])}\n"
    )


def render_agents_md(profile: dict[str, Any]) -> str:
    project = profile["project"]
    execution = profile["execution"]
    return f"""# XinAnRiver DV agent contract

This file is generated from `.agents/project_profile.json` and the canonical
role/skill contracts. Use Bazel labels and the legacy WORKSPACE as the build
authority.

- Entry target: `{project['entry_target']}`
- Test selector: `{project['test_selector']}`
- Simulator: `{project['simulator']}`
- Execution: `{execution['automation_repository']} / {execution['workflow']}`
- Runner policy: isolated exact commit, then SHICloud `bsub`

Use the source-free map first. Keep Bazel analysis, VCS compile, simulation,
regression, and coverage as separate evidence stages. Generated Claude Code
and Codex adapters must remain projections of `.agents/`.
"""


def render_claude_md(profile: dict[str, Any]) -> str:
    return """# XinAnRiver DV agent entrypoint

Read `AGENTS.md` and `.agents/project_profile.json` before DV work. Load the
smallest matching role and skill. Use the fixed ETX workflow and preserve the
evidence state distinctions defined by the profile.

The `.claude/` files are generated projections. Edit canonical `.agents/`
contracts and regenerate them.
"""


def render_mcp_manifest(profile: dict[str, Any]) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "launcher": "python3",
            "client_prefix": "",
            "servers": profile["mcp_servers"],
        },
        indent=2,
        ensure_ascii=False,
    ) + "\n"


def render_claude_mcp(profile: dict[str, Any]) -> str:
    servers = {}
    for server in profile["mcp_servers"]:
        servers[server["name"]] = {
            "type": "stdio",
            "command": "python3",
            "args": [server["script"]],
        }
    return json.dumps({"mcpServers": servers}, indent=2, ensure_ascii=False) + "\n"


def render_codex_config(profile: dict[str, Any]) -> str:
    lines = [
        "# Generated from .agents/project_profile.json; edit the canonical profile.",
        "",
    ]
    for server in profile["mcp_servers"]:
        lines.extend(
            [
                f"[mcp_servers.{server['name']}]",
                "enabled = true",
                'command = "python3"',
                f"args = {json.dumps([server['script']], ensure_ascii=False)}",
                f"startup_timeout_sec = {server['startup_timeout_sec']}",
                f"tool_timeout_sec = {server['tool_timeout_sec']}",
                "",
            ]
        )
    return "\n".join(lines)


def expected_files(profile_dir: Path, output_dir: Path) -> dict[Path, str | None]:
    profile = load_profile(profile_dir)
    roles = load_roles(profile_dir, profile)
    files: dict[Path, str | None] = {
        output_dir / "AGENTS.md": render_agents_md(profile),
        output_dir / "CLAUDE.md": render_claude_md(profile),
        output_dir / ".agents/project_profile.json": json.dumps(profile, indent=2) + "\n",
        output_dir / ".agents/mcp-servers.json": render_mcp_manifest(profile),
        output_dir / ".mcp.json": render_claude_mcp(profile),
        output_dir / ".codex/config.toml": render_codex_config(profile),
    }
    for role in roles:
        canonical = role["source"].read_text(encoding="utf-8")
        files[output_dir / ".agents/agents" / f"{role['name']}.md"] = canonical
        files[output_dir / ".claude/agents" / f"{role['name']}.md"] = canonical
        files[output_dir / ".codex/agents" / f"{role['name']}.toml"] = render_codex_role(role)
    for skill_dir in sorted((profile_dir / "skills").iterdir()):
        if not skill_dir.is_dir():
            continue
        source = skill_dir / "SKILL.md"
        if not source.is_file():
            raise BundleError(f"skill directory lacks SKILL.md: {skill_dir}")
        content = source.read_text(encoding="utf-8")
        files[output_dir / ".agents/skills" / skill_dir.name / "SKILL.md"] = content
        files[output_dir / ".claude/skills" / skill_dir.name / "SKILL.md"] = content
    for runtime_name in ("xinanriver_dv_contract.py", "xinanriver_dv_mcp.py"):
        files[output_dir / "scripts" / runtime_name] = (
            profile_dir / "runtime" / runtime_name
        ).read_text(encoding="utf-8")
    return files


def run(profile_dir: Path, output_dir: Path, write: bool) -> int:
    files = expected_files(profile_dir, output_dir)
    mismatches: list[Path] = []
    for path, content in files.items():
        actual = path.read_text(encoding="utf-8") if path.is_file() else None
        if actual == content:
            continue
        mismatches.append(path)
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            assert content is not None
            path.write_text(content, encoding="utf-8")
    if mismatches and not write:
        for path in mismatches:
            print(f"[TARGET-AGENT] OUT-OF-DATE: {path}", file=sys.stderr)
        return 2
    if write:
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
    args = parser.parse_args()
    try:
        return run(args.profile_dir, args.output_dir, args.write)
    except (OSError, KeyError, json.JSONDecodeError, BundleError) as exc:
        print(f"[TARGET-AGENT] ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
