# Changelog

## 0.2.1 (2026-10-21)

- Handle pathological nested TOML safely without printing tracebacks.
- Treat invalid/unauthorized executable and working-directory checks as unverified instead of crashing or leaking path text.
- Validate unreasonably large numeric timeouts without float-conversion overflow.
- Add offline release preflight against accidentally bundled credentials, private files, binary payloads and archive traversal/symlinks.
- Gate future CI runs with the preflight; pin the GitHub checkout/setup-python actions to verified commit SHAs; add targeted adversarial tests.
- Continue to avoid launching MCP processes, reading browser data, sending telemetry or modifying user configuration.


## 0.2.0 (2026-10-21)

- Deep review of ten realistic failure classes, with documented outcomes and remaining limits.
- Project-scoped config inspection as an explicit single-file option; honest warning about config layering.
- Support mixed `env_vars` entries, remote executor declarations, `cwd`, timeout aliases, header environment variables, and overlapping MCP tool filters.
- Safer treatment of Windows environment-variable casing, launcher PATH overrides, and unresolved relative paths.
- Harden HTTP URL checking for loopback IPv4/IPv6, invalid ports, embedded user credentials and URI fragments.
- Default redaction of all server names, with a deliberately limited opt-in display mode.
- Guard against oversized files and pathological server counts; preserve no-execution/no-network behavior.
- Expand tests from 35 to 81, including malicious-content and composite-config cases.
- Update bilingual docs, security statement, build instructions, and CI test matrix.

**Outstanding:** No Windows-native execution yet; no Codex runtime handshake, browser automation check, or Computer Use integration. Config layers are inspected separately rather than merged.

## 0.1.0 (2026-10-21)

- First static, read-only Codex MCP TOML diagnostics.
- Initial 35 Python unit tests and cross-platform CI definition.
