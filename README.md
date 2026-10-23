# Codex Windows MCP Doctor 🩺

[简体中文](README.zh-CN.md) · [Troubleshooting](docs/TROUBLESHOOTING.md) · [10-pass audit](docs/AUDIT.zh-CN.md) · [Security](SECURITY.md)

**v0.2.1** is a small, offline, **read-only static configuration diagnostic** for Codex MCP servers. It focuses on Windows users who are troubleshooting launcher, PATH, environment, URL, and tool visibility problems.

> **Scope warning**: `OK` means that none of the current *static* rules found an obvious issue in **one inspected file**. It is **not** evidence of live MCP connectivity, a working browser, or a functioning Computer Use integration. No MCP executable is launched.

## What it checks

- TOML syntax; disabled servers; missing or conflicting stdio/HTTP transports.
- Executable discovery, Windows `.cmd` fallback, `cwd`, relative executable ambiguity and server-specific PATH overrides.
- `env_vars` strings and `{name, source}` objects; local versus remote stdio execution.
- HTTP(S) endpoint format, loopback hosts, embedded credentials, and unencrypted remote connections.
- Timeout aliases, HTTP header types, missing referenced variables, overlapping enabled/disabled tool lists.
- Playwright MCP extension mode and unpinned `@latest` package usage.
- Capped input size and number of servers. Privacy-preserving output: no raw commands, args, URLs, or environment values; server names are hidden by default.

## Requirements and install

Python 3.11 or newer, no Python runtime dependencies. Codex does not need to be running, and no Codex installation is required to inspect a config file; without a config file the tool reports it as missing. **This project has not been published to PyPI.** Do not install similarly named packages from PyPI.

Extract the source ZIP or clone the repository. From the repository root, run in PowerShell:

```powershell
py -3 -m pip install .
codex-mcp-doctor
```

Without installation:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3 -m codex_mcp_doctor
```

## Usage

```powershell
codex-mcp-doctor
codex-mcp-doctor --json
codex-mcp-doctor --strict
codex-mcp-doctor --config "C:\Users\YOU\.codex\config.toml"
codex-mcp-doctor --project "D:\your-project"
codex-mcp-doctor --show-server-names
```

The default location is `CODEX_HOME/config.toml` if set, otherwise `~/.codex/config.toml`. `--project` inspects `PROJECT/.codex/config.toml` **alone**. This tool does not merge user/project/system settings, profiles, or managed policies to reconstruct Codex's effective configuration.

With default privacy settings, server IDs appear as `mcp:#1` etc. To show simple non-sensitive names, opt in using `--show-server-names`. Config paths are generalized in reports.

Exit status: `0` for no errors (including warnings by default), `1` for warnings with `--strict`, `2` for errors. JSON uses schema version 1.

## Sample output

Real output from v0.2.1 (measured on Linux; on Windows the platform field reads `windows` and hints may mention `.cmd` launchers). Server names are hidden by default and appear as `mcp:#1` etc.

A healthy config:

```toml
[mcp_servers.echo]
command = "python3"
args = ["-c", "pass"]

[mcp_servers.local]
url = "http://127.0.0.1:8931/mcp"
```

```text
$ codex-mcp-doctor --config good.toml
Codex MCP Doctor v0.2.1 | linux | OK
Config: <custom path> | entries: 2
[INFO] STATIC_CHECKS_PASSED (codex): Static checks found no obvious problems.
  Hint: This is NOT a live MCP connectivity or browser/Desktop test; check inside Codex.
Static-only, read-only. No server launch, browser test, or config-layer merge.
```

Exit status `0`.

A config with one risky server:

```toml
[mcp_servers.old]
url = "http://example.com/mcp"
```

```text
$ codex-mcp-doctor --config warn.toml
Codex MCP Doctor v0.2.1 | linux | WARNING
Config: <custom path> | entries: 1
[WARNING] INSECURE_HTTP (mcp:#1): Remote MCP endpoint uses unencrypted HTTP.
  Hint: Use HTTPS unless your deployment explicitly secures this connection.
Static-only, read-only. No server launch, browser test, or config-layer merge.
```

Exit status `0` (warnings do not fail by default; `--strict` returns `1`).

A config with three broken servers:

```toml
[mcp_servers.broken]
command = "definitely-not-a-real-binary-xyz"
args = []

[mcp_servers.confused]
command = "python3"
url = "https://example.com/mcp"

[mcp_servers.leaky]
url = "http://user:secret123@example.com:8080/mcp"
```

```text
$ codex-mcp-doctor --config bad.toml
Codex MCP Doctor v0.2.1 | linux | ERROR
Config: <custom path> | entries: 3
[ERROR] EXECUTABLE_NOT_FOUND (mcp:#1): Local MCP executable was not found.
  Hint: Check PATH, launcher extension (.cmd on Windows), cwd, and command/args separation.
[ERROR] TRANSPORT_INVALID (mcp:#2): Expected exactly one of command or url.
  Hint: Choose stdio or streamable HTTP; do not combine both.
[ERROR] URL_INVALID (mcp:#3): MCP HTTP URL has invalid scheme, host, port, or credentials.
  Hint: Use an HTTP(S) endpoint without embedded usernames, passwords, or fragments.
Static-only, read-only. No server launch, browser test, or config-layer merge.
```

Exit status `2`. Note the username and password embedded in the bad config never appear in the output.

JSON form (`--json`) of the same broken config:

```json
{
  "schema_version": 1,
  "tool_version": "0.2.1",
  "platform": "linux",
  "config": "<custom path>",
  "status": "error",
  "servers_seen": 3,
  "findings": [
    {
      "code": "EXECUTABLE_NOT_FOUND",
      "level": "error",
      "target": "mcp:#1",
      "message": "Local MCP executable was not found.",
      "action": "Check PATH, launcher extension (.cmd on Windows), cwd, and command/args separation."
    },
    {
      "code": "TRANSPORT_INVALID",
      "level": "error",
      "target": "mcp:#2",
      "message": "Expected exactly one of command or url.",
      "action": "Choose stdio or streamable HTTP; do not combine both."
    },
    {
      "code": "URL_INVALID",
      "level": "error",
      "target": "mcp:#3",
      "message": "MCP HTTP URL has invalid scheme, host, port, or credentials.",
      "action": "Use an HTTP(S) endpoint without embedded usernames, passwords, or fragments."
    }
  ]
}
```

## Important limitations

- `shutil.which()` sees **this Python process's** PATH. A Codex desktop app may see a different PATH or additional environment variables; the tool avoids treating ambiguous cases as certain failures where possible.
- A valid local path does **not** mean the executable is safe or runnable, and a well-formed HTTP URL does **not** mean the endpoint is online.
- No live `codex mcp list`, handshake, browser tab read, operating-system accessibility test, or automatic repair is performed.
- Inspect only one config layer per invocation. To compare layers, run the tool separately with `--config` or `--project`.

To continue manual diagnosis:

```powershell
codex mcp list
codex mcp get playwright
```

Use the actual MCP server name instead of `playwright`. See the [troubleshooting guide](docs/TROUBLESHOOTING.md) and the [official Codex MCP docs](https://developers.openai.com/codex/mcp).

## Tests

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python tools/security_preflight.py --source .
```

94 tests passed in the local Linux-backed development environment. A Windows/Linux Python 3.11/3.13 matrix is configured but has **not** been executed in public CI or tested on the user's Windows device yet. See the [10-pass audit](docs/AUDIT.zh-CN.md) and [pre-release security audit](docs/SECURITY_AUDIT.zh-CN.md).

## License and community

MIT, see [LICENSE](LICENSE). [Contribution guide](CONTRIBUTING.md), [security policy](SECURITY.md).

Independent community tool, not affiliated with or endorsed by OpenAI, Codex, Microsoft, or Playwright.
