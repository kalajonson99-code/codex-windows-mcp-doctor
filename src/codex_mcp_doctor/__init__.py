"""Codex Windows MCP Doctor: offline, read-only diagnostics."""
from .doctor import VERSION, Finding, Report, default_config_path, inspect_config

__version__ = VERSION
__all__ = ["VERSION", "Finding", "Report", "default_config_path", "inspect_config"]
