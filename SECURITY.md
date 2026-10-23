# Security Policy

This project is intentionally **read-only and offline**. It never starts configured MCP commands, executes shells, queries configured URLs, edits configuration files, captures browser content, or collects telemetry. It is NOT a malware detector.

A Codex config may contain real secrets. This tool never prints raw config values, commands, URL strings, argument arrays, or environment-variable values. By default it also replaces server names with numbered labels such as `mcp:#1`. `--show-server-names` explicitly opts in to simple names, and still masks suspicious patterns. Paths in reports are generic.

**Always manually review JSON reports before sharing**. Even generic metadata (error types, platform, server count and opt-in names) can be sensitive in some settings. Do not post raw `config.toml` files, environment dumps, log files, cookies or bearer tokens in public issues.

Safety bounds: 2 MiB max config read and 512 maximum MCP server entries per file. The software requires no runtime dependencies beyond Python 3.11+.

Release maintainers must run `python tools/security_preflight.py --source .` and scan each built wheel, source distribution and ZIP using repeated `--artifact` flags. This heuristic scanner rejects known token shapes, private key markers, sensitive filenames, archive traversal, symlinks, binary content, and unusually large entries. It does **not** prove that all possible secrets or sensitive text have been found: manually review all files before release, including docs and test fixtures. Never publish a report or config captured from a real user.

Filesystem errors while inspecting user-controlled executable paths are deliberately reported without raw path or exception text; their result is *unverified*, not *safe*. Very deeply nested TOML is rejected without an uncaught traceback.

## Unverified boundaries

A detected executable can still be unsafe or unusable. A valid HTTP URL can still be unreachable, misconfigured or malicious. The tool cannot know the GUI's exact PATH, merged Codex configuration, trust scope, credential validity, or accessibility permissions. A passing report does not certify runtime safety or functionality.

## Reporting vulnerabilities

Use repository security advisories/private vulnerability reporting if enabled, or a private maintainer channel. Do not create public issues containing secret material or exploit payloads if private reporting is not available.
