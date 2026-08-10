#!/usr/bin/env python3
"""Small MCP facade over the deterministic XinAnRiver DV contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from xinanriver_dv_contract import (
    load_profile,
    parity_signature,
    summarize_evidence,
    workflow_inputs,
)


try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - exercised only by a client runtime
    raise SystemExit("MCP runtime is required; install the target agent requirements") from exc


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / ".agents" / "project_profile.json"
PROFILE_DATA = load_profile(PROFILE)
mcp = FastMCP("xinanriver-dv")


@mcp.tool()
def get_profile() -> dict:
    """Return the validated, non-secret DV profile."""
    return parity_signature(PROFILE_DATA)


@mcp.tool()
def plan_target_run(project_sha: str, project_branch: str | None = None) -> dict:
    """Render the fixed ETX target workflow inputs without dispatching it."""
    return workflow_inputs(PROFILE_DATA, project_sha, project_branch=project_branch)


@mcp.tool()
def review_evidence(
    artifact_dir: str, expected_project_branch: str | None = None
) -> dict:
    """Review a retained source-free artifact directory."""
    return summarize_evidence(
        PROFILE_DATA,
        Path(artifact_dir),
        expected_project_branch=expected_project_branch,
    )


if __name__ == "__main__":
    mcp.run()
