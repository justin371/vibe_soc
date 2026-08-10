#!/usr/bin/env python3
"""MCP facade for the reusable RTL-DV contract.

The same adapter entrypoint is used by every client, but each configured MCP
server exposes only the tools assigned to that server. This keeps role-level
MCP declarations meaningful instead of relying on comments in generated files.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .dv_contract import (
    load_profile,
    parity_signature,
    summarize_evidence,
    workflow_inputs,
)


def _server_names(profile: dict[str, Any]) -> set[str]:
    return {server["name"] for server in profile["mcp_servers"]}


def build_server(profile: dict[str, Any], server_name: str):
    """Build one restricted MCP server for the selected profile server."""

    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - client runtime only
        raise SystemExit("MCP runtime is required; install the target agent requirements") from exc

    names = _server_names(profile)
    if server_name != "all" and server_name not in names:
        raise ValueError(f"unknown MCP server: {server_name}")
    configured = {
        server["name"]: set(server["tools"])
        for server in profile["mcp_servers"]
    }
    tools = (
        {"get_profile", "plan_target_run", "review_evidence"}
        if server_name == "all"
        else configured[server_name]
    )
    display_name = profile["adapter"]["display_name"]
    mcp = FastMCP(f"{display_name}-{server_name}")

    if "get_profile" in tools:

        @mcp.tool()
        def get_profile() -> dict:
            """Return the validated, non-secret DV profile signature."""

            return parity_signature(profile)

    if "plan_target_run" in tools:

        @mcp.tool()
        def plan_target_run(
            project_sha: str, project_branch: str | None = None
        ) -> dict:
            """Render fixed workflow inputs without dispatching a run."""

            return workflow_inputs(
                profile,
                project_sha,
                project_branch=project_branch,
            )

    if "review_evidence" in tools:

        @mcp.tool()
        def review_evidence(
            artifact_dir: str,
            expected_project_branch: str,
            expected_project_sha: str,
        ) -> dict:
            """Review a retained source-free artifact directory."""

            return summarize_evidence(
                profile,
                Path(artifact_dir),
                expected_project_branch=expected_project_branch,
                expected_project_sha=expected_project_sha,
            )

    return mcp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--server",
        default="all",
        help="profile MCP server name; use all only for local diagnostics",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path(".agents/project_profile.json"),
    )
    args = parser.parse_args(argv)
    profile_path = args.profile
    if not profile_path.is_absolute() and not profile_path.is_file():
        profile_path = Path(__file__).resolve().parents[1] / profile_path
    profile = load_profile(profile_path)
    build_server(profile, args.server).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
