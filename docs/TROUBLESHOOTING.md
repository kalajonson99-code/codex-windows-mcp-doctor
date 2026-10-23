# Troubleshooting

This static checker **does not test MCP runtimes**. `OK` means only that the inspected file passed static rules. Codex can merge additional config layers, and managed settings may override them.

### MCP missing from Codex

Run `codex mcp list`, then compare against your inspected file. A config in `PROJECT/.codex/config.toml` may be applied differently depending on project trust and client context. To inspect a project config directly, use `codex-mcp-doctor --project PROJECT`.

### `npx`, `node`, or `python` missing

Check in PowerShell:

```powershell
Get-Command npx
Get-Command node
node --version
```

The PATH seen by an already-running Codex GUI may differ from PowerShell. Restart the relevant app after intentionally changing PATH. Avoid running unverified installation/fix scripts. If the server overrides `env.PATH`, the doctor explicitly says the launcher is not verifiable with the current process PATH.

### Browser tool loaded but page reads fail intermittently

A valid TOML file cannot diagnose browser permission prompts, CDP connectivity, extension handoff, browser version, page site policies, server launch timeout, or tool routing. Test a harmless public page with a new browser session; compare the MCP's logs and actual tool errors. Never publish session cookies or screenshots containing account data.

### Built-in Computer Use fails

Desktop window automation problems are separate from MCP configuration issues. This checker does not inspect or bypass operating system accessibility controls, Codex policy, or the built-in Computer Use implementation. Reproduce on a harmless app such as Notepad before diagnosing sensitive applications.

### Unsure whether a warning is real

Distinguish `*_MISSING` from `*_UNVERIFIED`, and remember that `ENV_VAR_MISSING` refers to this Python process rather than every Codex client. Read the audit's remaining limitations and run separate checks in relevant client environments.

Official resources: [Codex MCP documentation](https://developers.openai.com/codex/mcp), [configuration reference](https://developers.openai.com/codex/config-reference), [Playwright MCP](https://github.com/microsoft/playwright-mcp).
