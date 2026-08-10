#!/usr/bin/env python3
"""XinAnRiver adapter for the reusable RTL-DV agent core."""

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

from agent_core.dv_contract import (  # noqa: E402,F401
    ContractError,
    load_core_manifest,
    load_profile,
    parity_signature,
    summarize_evidence,
    validate_profile,
    workflow_inputs,
)

__all__ = [
    "ContractError",
    "load_core_manifest",
    "load_profile",
    "parity_signature",
    "summarize_evidence",
    "validate_profile",
    "workflow_inputs",
]
