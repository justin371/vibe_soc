#!/usr/bin/env python3
"""XinAnRiver adapter entrypoint for the reusable RTL-DV MCP server."""

from __future__ import annotations

import sys
from pathlib import Path


REPOSITORY_ROOT = next(
    (
        candidate
        for candidate in Path(__file__).resolve().parents
        if (candidate / "agent_core" / "manifest.json").is_file()
    ),
    Path(__file__).resolve().parents[-1],
)
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from agent_core.dv_mcp import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
