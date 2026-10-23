"""Conservative, read-only diagnostics for Codex MCP TOML settings.

The program NEVER runs configured commands, opens URLs, or prints config values.
A passing report is not proof of a working MCP connection.
"""
from __future__ import annotations

import ipaddress
import math
import os
import re
import shutil
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

VERSION = "0.2.1"
MAX_CONFIG_BYTES = 2 * 1024 * 1024
MAX_SERVERS = 512


@dataclass(frozen=True)
class Finding:
    code: str
    level: str
    target: str
    message: str
    action: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class Report:
    config: str
    platform: str
    version: str
    servers_seen: int
    findings: tuple[Finding, ...]

    @property
    def status(self) -> str:
        levels = {f.level for f in self.findings}
        if "error" in levels:
            return "error"
        if "warning" in levels:
            return "warning"
        return "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "tool_version": self.version,
            "platform": self.platform,
            "config": self.config,
            "status": self.status,
            "servers_seen": self.servers_seen,
            "findings": [f.to_dict() for f in self.findings],
        }


def default_config_path(env: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    env = os.environ if env is None else env
    if env.get("CODEX_HOME"):
        return Path(env["CODEX_HOME"]).expanduser() / "config.toml"
    return (home if home is not None else Path.home()) / ".codex" / "config.toml"


def _public_path(path: Path, home: Path) -> str:
    """Only display paths with a known generic form, never a user's arbitrary names."""
    if path == home / ".codex" / "config.toml":
        return "~/.codex/config.toml"
    if path.name == "config.toml" and path.parent.name == ".codex":
        return "<project-or-custom>/.codex/config.toml"
    return "<custom path>"


def _safe_label(name: str, ordinal: int, show_names: bool) -> str:
    # Explicit opt-in, and still reject suspicious or control-containing names.
    if show_names and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,39}", name):
        if not re.search(r"(?i)(?:secret|token|password|key|auth|cookie|credential|sk-[a-z0-9]+|ghp_|github_pat_|xox[baprs]-|AKIA)", name) and len(name) < 32:
            return f"mcp:{name}"
    return f"mcp:#{ordinal}"


def _expand_path(text: str, env: Mapping[str, str], home: Path) -> tuple[Path, bool]:
    """Expand known variables, no shell, and flag variables absent in our environment."""
    missing = False
    pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|%([A-Za-z_][A-Za-z0-9_]*)%")

    def repl(match: re.Match[str]) -> str:
        nonlocal missing
        key = match.group(1) or match.group(2)
        if key in env:
            return env[key]
        # %VAR% is Windows expansion syntax; the Windows environment is
        # case-insensitive even if the test fixture uses mixed casing.
        if match.group(2):
            matches = [value for name, value in env.items() if name.casefold() == key.casefold()]
            if matches:
                return matches[0]
        missing = True
        return match.group(0)

    expanded = pattern.sub(repl, text)
    if expanded == "~":
        expanded = str(home)
    elif expanded.startswith("~/") or expanded.startswith("~\\"):
        expanded = str(home) + expanded[1:]
    return Path(expanded), missing


def _looks_like_path(command: str) -> bool:
    return "/" in command or "\\" in command or command.startswith(".")


def _is_local_http_host(host: str) -> bool:
    if host.lower().rstrip(".") == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def inspect_config(
    path: Path | None = None, *,
    env: Mapping[str, str] | None = None,
    platform: str | None = None,
    which: Callable[[str], str | None] | None = None,
    exists: Callable[[Path], bool] | None = None,
    is_dir: Callable[[Path], bool] | None = None,
    home: Path | None = None,
    show_names: bool = False,
) -> Report:
    """Inspect one config file. Never runs commands or joins Codex config layers.

    Dependencies are injectable to test Windows command discovery on non-Windows CI.
    A PATH observation is only evidence about THIS Python process, not Codex GUI.
    """
    env = dict(os.environ if env is None else env)
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else Path(home)
    path = default_config_path(env, home) if path is None else Path(path).expanduser()
    which = shutil.which if which is None else which
    exists = Path.exists if exists is None else exists
    is_dir = Path.is_dir if is_dir is None else is_dir
    findings: list[Finding] = []

    def env_present(key: str) -> bool:
        if env.get(key):
            return True
        return platform == "win32" and any(k.casefold() == key.casefold() and bool(v)
                                            for k, v in env.items())

    def add(code: str, level: str, target: str, message: str, action: str) -> None:
        findings.append(Finding(code, level, target, message, action))

    config_label = _public_path(path, home)

    def report(count: int = 0) -> Report:
        return Report(config_label, platform, VERSION, count, tuple(findings))

    try:
        with path.open("rb") as fh:
            raw = fh.read(MAX_CONFIG_BYTES + 1)
    except FileNotFoundError:
        add("CONFIG_MISSING", "warning", "codex", "Codex config.toml was not found.",
            "Check --config, CODEX_HOME, and project-scoped .codex/config.toml.")
        return report()
    except (OSError, ValueError) as exc:
        add("CONFIG_UNREADABLE", "error", "codex", f"Could not read config.toml ({type(exc).__name__}).",
            "Check file permissions; no file changes were made.")
        return report()
    if len(raw) > MAX_CONFIG_BYTES:
        add("CONFIG_TOO_LARGE", "error", "codex", "Config exceeds the 2 MiB safety limit.",
            "Review file size locally; this tool intentionally does not parse huge files.")
        return report()
    try:
        config = tomllib.loads(raw.decode("utf-8-sig"))
    except (tomllib.TOMLDecodeError, UnicodeError, ValueError, RecursionError):
        add("CONFIG_INVALID_TOML", "error", "codex", "Config contains invalid TOML or encoding.",
            "Back up the file and validate its TOML syntax without sharing secrets.")
        return report()
    if not isinstance(config, dict):
        add("CONFIG_INVALID", "error", "codex", "Config root is invalid.", "Validate TOML structure.")
        return report()
    servers = config.get("mcp_servers")
    if servers is None:
        add("MCP_NOT_CONFIGURED", "warning", "codex", "No [mcp_servers] section in this file.",
            "Inspect other Codex config layers; add a server with `codex mcp add` if needed.")
        return report()
    if not isinstance(servers, dict):
        add("MCP_SECTION_INVALID", "error", "codex", "mcp_servers must be a TOML table.",
            "Use [mcp_servers.NAME] tables.")
        return report()
    if len(servers) > MAX_SERVERS:
        add("MCP_TOO_MANY", "error", "codex", "MCP server entry count exceeds the 512-entry safety limit.",
            "Review this unusually large configuration before diagnosing it.")
        return report(len(servers))
    if not servers:
        add("MCP_EMPTY", "warning", "codex", "No MCP server entries found.",
            "Use `codex mcp add` or inspect other config layers.")

    for ordinal, (name, settings) in enumerate(sorted(servers.items()), start=1):
        label = _safe_label(name, ordinal, show_names)
        if not isinstance(settings, dict):
            add("SERVER_INVALID", "error", label, "Server settings must be a TOML table.",
                "Use [mcp_servers.NAME] with valid fields.")
            continue
        enabled = settings.get("enabled", True)
        if not isinstance(enabled, bool):
            add("ENABLED_INVALID", "error", label, "enabled must be a boolean.", "Set enabled = true or false.")
            continue
        if not enabled:
            add("SERVER_DISABLED", "info", label, "Server is explicitly disabled.",
                "Enable only if you intend to use it.")
            continue

        remote = settings.get("experimental_environment", "local")
        if remote not in ("local", "remote") or not isinstance(remote, str):
            add("ENVIRONMENT_INVALID", "error", label, "experimental_environment is invalid.",
                "Use local or remote, if this Codex version supports remote stdio.")
            remote = "local"
        remote_stdio = remote == "remote"

        command, url = settings.get("command"), settings.get("url")
        has_command, has_url = command is not None, url is not None
        if has_command == has_url:
            add("TRANSPORT_INVALID", "error", label, "Expected exactly one of command or url.",
                "Choose stdio or streamable HTTP; do not combine both.")
        if remote_stdio and has_url:
            add("REMOTE_HTTP_UNSUPPORTED", "error", label, "Remote placement does not support HTTP MCP.",
                "Use local HTTP or a supported remote stdio executor.")

        extra_env_preview = settings.get("env", {})
        custom_path = isinstance(extra_env_preview, dict) and any(
            isinstance(k, str) and k.lower() == "path" for k in extra_env_preview
        )

        cwd: Path | None = None
        specified_cwd = settings.get("cwd")
        if specified_cwd is not None:
            if not isinstance(specified_cwd, str) or not specified_cwd.strip():
                add("CWD_INVALID", "error", label, "cwd must be a nonempty directory path.",
                    "Use a valid working directory for the MCP process.")
            elif not remote_stdio:
                cwd_path, unknown = _expand_path(specified_cwd, env, home)
                if unknown:
                    add("CWD_ENV_UNRESOLVED", "warning", label, "cwd contains unavailable environment variables.",
                        "Ensure variables exist in the Codex process environment.")
                elif not cwd_path.is_absolute():
                    add("CWD_RELATIVE", "warning", label, "cwd uses a relative path.",
                        "Prefer an absolute working directory to avoid launch ambiguity.")
                else:
                    try:
                        directory_found = is_dir(cwd_path)
                    except (OSError, ValueError, OverflowError):
                        directory_found = None
                    if directory_found is None:
                        add("CWD_UNVERIFIED", "warning", label,
                            "Cannot safely check the MCP working directory.",
                            "Verify the directory locally; its path was not included in this report.")
                    elif not directory_found:
                        add("CWD_NOT_FOUND", "error", label,
                            "Local MCP working directory was not found.",
                            "Create the directory or update cwd.")
                    else:
                        cwd = cwd_path
            else:
                add("REMOTE_CWD_NOT_VERIFIED", "info", label, "Remote MCP cwd cannot be checked locally.",
                    "Verify the directory on the remote executor.")

        if has_command:
            if not isinstance(command, str) or not command.strip():
                add("COMMAND_INVALID", "error", label, "command must be a nonempty string.",
                    "Set one executable in command and put arguments in args.")
            elif (command != command.strip() or any(ord(c) < 32 for c in command)
                  or re.search(r"\s--?[A-Za-z][A-Za-z0-9-]*(?=\s|$)|\s/(?:c|k)(?=\s|$)", command)
                  or any(token in command for token in ("&&", "||", "|", ";"))):
                add("COMMAND_FORMAT", "error", label, "command has surrounding whitespace or controls.",
                    "Use an executable path without embedded shell syntax.")
            elif remote_stdio:
                add("REMOTE_COMMAND_NOT_VERIFIED", "info", label, "Remote executable cannot be checked locally.",
                    "Confirm it is installed in the remote executor.")
            else:
                resolved = False
                unexpanded = False
                relative_unbound = False
                path_check_failed = False
                if _looks_like_path(command):
                    cmd_path, unexpanded = _expand_path(command, env, home)
                    if not unexpanded:
                        if not cmd_path.is_absolute() and cwd is not None:
                            cmd_path = cwd / cmd_path
                        elif not cmd_path.is_absolute():
                            relative_unbound = True
                        if not relative_unbound:
                            try:
                                resolved = exists(cmd_path) and not is_dir(cmd_path)
                            except (OSError, ValueError, OverflowError):
                                path_check_failed = True
                else:
                    try:
                        resolved = bool(which(command))
                        if not resolved and platform == "win32" and not Path(command).suffix:
                            resolved = any(which(command + ext) for ext in (".cmd", ".exe", ".bat", ".com"))
                    except (OSError, ValueError, OverflowError):
                        path_check_failed = True
                if relative_unbound:
                    add("RELATIVE_COMMAND_UNVERIFIED", "warning", label,
                        "Relative executable path cannot be resolved without a known cwd.",
                        "Set an absolute command path or confirm Codex launch cwd.")
                elif unexpanded:
                    add("COMMAND_ENV_UNRESOLVED", "warning", label, "Executable path references an unset variable.",
                        "Check the environment seen by the Codex process.")
                elif path_check_failed:
                    add("EXECUTABLE_UNVERIFIED", "warning", label,
                        "Executable lookup failed; its availability is unknown.",
                        "Check permissions, PATH and file-path validity locally.")
                elif not resolved and custom_path and not _looks_like_path(command):
                    add("CUSTOM_PATH_UNVERIFIED", "warning", label,
                        "Executable is absent from this process PATH, but server overrides PATH.",
                        "Verify command discovery with the PATH inherited by the MCP process.")
                elif not resolved:
                    add("EXECUTABLE_NOT_FOUND", "error", label, "Local MCP executable was not found.",
                        "Check PATH, launcher extension (.cmd on Windows), cwd, and command/args separation.")
                if platform == "win32" and isinstance(command, str) and command.lower().endswith((".ps1", ".py")):
                    add("SCRIPT_LAUNCHER", "warning", label, "A script was used directly as the executable.",
                        "Prefer an explicit interpreter such as powershell.exe or python.exe, with script in args.")
            args = settings.get("args", [])
            if not isinstance(args, list) or any(not isinstance(a, str) for a in args):
                add("ARGS_INVALID", "error", label, "args must be an array of strings.",
                    "Use args = ['-y', 'package-name'] or similar.")
            else:
                base = command.replace("\\", "/").split("/")[-1].lower() if isinstance(command, str) else ""
                if base in ("npx", "npx.cmd", "npm", "npm.cmd") and not args:
                    add("NPX_NO_ARGS", "warning", label, "Node package launcher has no arguments.",
                        "Specify the intended package/command in args.")
                if base in ("npx", "npx.cmd") and any(a == "@playwright/mcp@latest" for a in args):
                    add("UNPINNED_PACKAGE", "warning", label, "Playwright MCP uses a floating @latest version.",
                        "For reproducible runs, pin a tested version.")
                if base in ("npx", "npx.cmd") and any("@playwright/mcp" in a for a in args):
                    if "--extension" in args:
                        add("PLAYWRIGHT_EXTENSION", "info", label, "Playwright extension mode is configured.",
                            "Verify the matching browser extension is installed and attached.")
        if has_url:
            if not isinstance(url, str) or not url or any(c.isspace() or ord(c) < 32 for c in url):
                add("URL_INVALID", "error", label, "MCP HTTP URL is invalid.",
                    "Use an absolute HTTP(S) URL without whitespace.")
            else:
                try:
                    parts = urlsplit(url)
                    host = parts.hostname
                    port = parts.port
                    valid = parts.scheme in ("http", "https") and bool(host) and (port is None or port > 0)
                    valid = valid and bool(parts.netloc) and not parts.fragment and not parts.netloc.endswith(":")
                    valid = valid and not (parts.username is not None or parts.password is not None)
                    valid = valid and not re.search(r"[^A-Za-z0-9.\-_:]", parts.netloc.replace("[", "").replace("]", ""))
                except (ValueError, TypeError):
                    valid = False
                    parts = None
                    host = None
                if not valid:
                    add("URL_INVALID", "error", label, "MCP HTTP URL has invalid scheme, host, port, or credentials.",
                        "Use an HTTP(S) endpoint without embedded usernames, passwords, or fragments.")
                elif parts is not None:
                    if parts.scheme == "http" and not _is_local_http_host(host):
                        add("INSECURE_HTTP", "warning", label, "Remote MCP endpoint uses unencrypted HTTP.",
                            "Use HTTPS unless your deployment explicitly secures this connection.")
                    if parts.query:
                        add("HTTP_URL_QUERY", "info", label, "MCP URL includes query parameters.",
                            "Avoid storing authentication tokens inside URLs.")

        for key in ("startup_timeout_sec", "tool_timeout_sec", "startup_timeout_ms"):
            v = settings.get(key)
            invalid_timeout = (isinstance(v, bool) or not isinstance(v, (float, int)))
            if isinstance(v, int) and not isinstance(v, bool):
                invalid_timeout = v <= 0 or v.bit_length() > 63
            elif isinstance(v, float):
                invalid_timeout = not math.isfinite(v) or v <= 0
            if v is not None and invalid_timeout:
                add("TIMEOUT_INVALID", "error", label, f"{key} must be a finite positive number.",
                    "Use a positive numeric timeout.")
        if "startup_timeout_sec" in settings and "startup_timeout_ms" in settings:
            add("STARTUP_TIMEOUT_DUPLICATE", "warning", label, "Both startup timeout aliases are present.",
                "Keep only one startup timeout field to avoid ambiguity.")

        extra_env = settings.get("env", {})
        env_valid = isinstance(extra_env, dict) and all(isinstance(k, str) and isinstance(v, str)
                                                        for k, v in extra_env.items())
        if not env_valid:
            add("ENV_INVALID", "error", label, "env must map names to string values.",
                "Use env = { KEY = 'value' } or [mcp_servers.NAME.env].")
            extra_env = {}
        elif extra_env and has_url and not has_command:
            add("STDIO_ENV_ON_HTTP", "warning", label, "env is a stdio setting, not HTTP authentication.",
                "For HTTP use bearer_token_env_var, OAuth, or supported HTTP headers.")

        env_vars = settings.get("env_vars", [])
        if not isinstance(env_vars, list):
            add("ENV_VARS_INVALID", "error", label, "env_vars must be an array.",
                "Use variable names or { name = 'VAR', source = 'local|remote' } objects.")
        else:
            missing_count = 0
            invalid = 0
            for item in env_vars:
                if isinstance(item, str):
                    var, source = item, "local"
                elif isinstance(item, dict) and set(item) == {"name", "source"}:
                    var, source = item["name"], item["source"]
                else:
                    invalid += 1
                    continue
                if not isinstance(var, str) or not var or "=" in var or "\x00" in var or not isinstance(source, str) or source not in ("local", "remote"):
                    invalid += 1
                    continue
                if source == "remote" and not remote_stdio:
                    add("REMOTE_VAR_NO_EXECUTOR", "error", label, "Remote env_vars entry requires remote stdio.",
                        "Use source = 'local', or configure a supported remote executor.")
                if source == "local" and not env_present(var) and var not in extra_env:
                    missing_count += 1
            if invalid:
                add("ENV_VARS_INVALID", "error", label, "env_vars contains invalid entries.",
                    "Each entry must be a name or object with name and source.")
            if missing_count:
                add("ENV_VAR_MISSING", "warning", label,
                    f"{missing_count} locally forwarded variable(s) are unset in this Python process.",
                    "They might be optional; check what environment Codex itself receives.")

        token_var = settings.get("bearer_token_env_var")
        if token_var is not None:
            if not isinstance(token_var, str) or not token_var:
                add("TOKEN_ENV_INVALID", "error", label, "bearer_token_env_var must be a variable name.",
                    "Provide the name, not the credential itself.")
            elif has_url and not env_present(token_var):
                add("TOKEN_ENV_MISSING", "warning", label, "HTTP bearer token variable is unavailable locally.",
                    "Check Codex process environment; OAuth may be an alternative.")
            if not has_url:
                add("TOKEN_ENV_ON_STDIO", "warning", label, "HTTP bearer-token setting is on a stdio server.",
                    "Use env or env_vars for stdio authentication.")

        for field in ("http_headers", "env_http_headers"):
            value = settings.get(field)
            if value is not None and (not isinstance(value, dict) or any(
                    not isinstance(k, str) or not isinstance(v, str) for k, v in value.items())):
                add("HEADERS_INVALID", "error", label, f"{field} must map header names to strings.",
                    "Use a TOML table of string values; never paste credentials into issues.")
            elif isinstance(value, dict) and field == "env_http_headers" and has_url:
                count = sum(1 for v in value.values() if not env_present(v))
                if count:
                    add("HEADER_ENV_MISSING", "warning", label,
                        f"{count} HTTP-header environment variable(s) are unset locally.",
                        "Check variables in the Codex process environment.")
        for field in ("enabled_tools", "disabled_tools"):
            value = settings.get(field)
            if value is not None and (not isinstance(value, list) or
                                      any(not isinstance(item, str) for item in value)):
                add("TOOL_LIST_INVALID", "error", label, f"{field} must be an array of strings.",
                    "Use MCP tool names as strings.")
        allow, deny = settings.get("enabled_tools"), settings.get("disabled_tools")
        if isinstance(allow, list) and isinstance(deny, list) and all(isinstance(x, str) for x in allow + deny):
            if set(allow) & set(deny):
                add("TOOLS_FILTER_CONFLICT", "warning", label, "Tool names appear in both allow and deny lists.",
                    "The deny list takes precedence; review intended availability.")

    if not findings:
        add("STATIC_CHECKS_PASSED", "info", "codex", "Static checks found no obvious problems.",
            "This is NOT a live MCP connectivity or browser/Desktop test; check inside Codex.")
    return report(len(servers))
