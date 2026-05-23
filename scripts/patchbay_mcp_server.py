from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Patchbay MCP server.")
    parser.add_argument("--root", default="", help="Repository root to operate on.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.root:
        os.environ["PATCHBAY_ROOT"] = str(Path(args.root).resolve())
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    from ai_flow.mcp_server import main as server_main

    return server_main()


if __name__ == "__main__":
    raise SystemExit(main())
