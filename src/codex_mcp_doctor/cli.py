"""Command-line interface. Outputs never include raw config values."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .doctor import VERSION, inspect_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="codex-mcp-doctor",
        description="Read-only static MCP diagnostics: never launches servers or edits configuration.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--config", type=Path, help="Path to one Codex config.toml (default: global config)")
    source.add_argument("--project", type=Path, help="Inspect only PROJECT/.codex/config.toml (not merged layers)")
    parser.add_argument("--json", action="store_true", help="Emit privacy-preserving JSON")
    parser.add_argument("--strict", action="store_true", help="Return code 1 for warnings; errors always return 2")
    parser.add_argument("--show-server-names", action="store_true", help="Opt in to simple, safe server names in output")
    args = parser.parse_args(argv)
    path = args.project / ".codex" / "config.toml" if args.project is not None else args.config
    report = inspect_config(path, show_names=args.show_server_names)
    try:
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(f"Codex MCP Doctor v{report.version} | {report.platform} | {report.status.upper()}")
            print(f"Config: {report.config} | entries: {report.servers_seen}")
            for f in report.findings:
                print(f"[{f.level.upper()}] {f.code} ({f.target}): {f.message}")
                print(f"  Hint: {f.action}")
            print("Static-only, read-only. No server launch, browser test, or config-layer merge.")
    except BrokenPipeError:
        return 0
    if report.status == "error":
        return 2
    if report.status == "warning" and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
