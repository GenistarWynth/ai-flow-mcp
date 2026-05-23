from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Patchbay MCP server.")
    parser.add_argument("--root", default="", help="Repository root to operate on.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.root:
        os.environ["PATCHBAY_ROOT"] = str(Path(args.root).resolve())
    SCRIPT_DIR = Path(__file__).resolve().parent
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    from ai_flow.mcp_server import main

    raise SystemExit(main())
