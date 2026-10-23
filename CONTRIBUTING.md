# Contributing

Contributions, issue reports, reproducible test cases, and documentation translations are welcome.

- Open an issue describing expected behavior, observed behavior and platform/versions. Sanitize any output before posting.
- For code changes, add or update `unittest` cases, then run `python -m unittest discover -s tests -v`.
- Changes that execute configured MCP processes, rewrite Codex configuration, collect browser data, or send telemetry require a separate documented security design and explicit opt-in; do not introduce these under a read-only command.
- Keep runtime dependencies minimal and compatible with Python 3.11+.

## Reporting issues safely

Share only a **manually reviewed redacted** report. Config files often contain private URL query strings, API keys, and local directory structures. Never post a raw config or logs without reviewing them.
