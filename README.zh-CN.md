# Codex Windows MCP Doctor 🩺

[English](README.md) · [排查手册](docs/TROUBLESHOOTING.zh-CN.md) · [十轮审查报告](docs/AUDIT.zh-CN.md) · [安全说明](SECURITY.md)

一个**只读、离线、默认隐私保护**的 Codex MCP 静态诊断工具，主要服务 Windows 用户。目前版本 **0.2.1**。

> **重要边界**：本工具检查的是配置文件和当前 Python 进程看到的环境，不会启动 MCP、不连接浏览器、不测试 Computer Use，也不擅自修复你的电脑。显示 `OK` 仅代表本轮静态规则没有发现明显异常，**不等于 Codex 已能正常使用工具**。

## 能查出哪些有用的问题？

- TOML 损坏、配置文件缺失、服务器被禁用、`command` 与 `url` 冲突。
- `npx` 等启动命令是否可查找；Windows `.cmd` 启动入口；脚本直接充当可执行文件；工作目录 `cwd` 是否缺失。
- 当前终端和服务器私有 `PATH` 不一致、相对路径来源不确定时**不直接误判为确定故障**。
- `env_vars` 的字符串和 `{name, source}` 对象写法，以及远程执行器来源区别。
- 服务器环境变量、HTTP bearer token、HTTP headers、工具启用/禁用列表、超时配置。
- 非本地明文 HTTP、格式有误的地址、账号密码嵌入 URL 等问题。
- Playwright MCP 的 `--extension` 模式与 `@latest` 漂移风险（仅提示，不连接插件）。
- 文本或 JSON 报告。默认用 `mcp:#1` 这样的编号代替可能敏感的 MCP 名称，不输出原始命令、参数、URL、环境值。

## Windows 安装

需要 Python 3.11+。不需要 Codex 在运行，工具只读配置文件；没有配置文件也能跑，会报缺失。本项目**没有发布到 PyPI**，不要根据项目名在 PyPI 随便安装同名包。

下载项目 ZIP 后解压，进入项目根目录，在 PowerShell 运行：

```powershell
py -3 -m pip install .
codex-mcp-doctor
```

无须安装的临时运行方式：

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3 -m codex_mcp_doctor
```

常用选项：

```powershell
codex-mcp-doctor --json
codex-mcp-doctor --strict
codex-mcp-doctor --config "C:\Users\你的用户名\.codex\config.toml"
codex-mcp-doctor --project "D:\my-project"
codex-mcp-doctor --show-server-names
```

`--project` 只检查该项目目录下的 `.codex/config.toml`；**不会**把系统、用户、项目配置合并成 Codex 最终生效的配置。`--show-server-names` 是可选的，且仅显示部分格式简单的名称。默认隐藏更适合分享报告。

## 示例输出

以下为 v0.2.1 的真实输出（Linux 环境实测；Windows 上平台一栏显示 windows，提示中可能提到 .cmd 启动入口）。服务器名称默认隐藏，显示为 mcp:#1 等。

健康的配置：

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

退出码 `0`。

一项有风险的配置：

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

退出码 `0`（默认警告不算失败；`--strict` 返回 `1`）。

三项都有问题的配置：

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

退出码 `2`。注意：坏配置里写的账号密码没有出现在输出里。

同一份坏配置的 JSON 形式（`--json`）：

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

## 看懂结果

`OK`：静态检查没有发现明显问题。`WARNING`：可能有风险，或现有环境不足以证明问题。`ERROR`：配置格式错误或在**本次检查环境**中明确缺少必要对象。

默认仅有 `WARNING` 时退出码 `0`；加入 `--strict` 返回 `1`；存在 `ERROR` 返回 `2`。请不要把 `OK` 当成 Windows 浏览器控制的成功率指标。

Windows Codex 桌面版、PowerShell、远程执行器可以有不同的环境变量与权限。诊断器发现的 `ENV_VAR_MISSING` 只能证明**当前 Python 进程**看不到该变量，不能证明 Codex 桌面端一定看不到。

## 检查通过后依然不工作？

用官方命令确认 MCP 是否注册，再在 Codex 中实际触发工具：

```powershell
codex mcp list
codex mcp get playwright
```

把 `playwright` 替换成你的实际服务器名称。浏览器偶尔读取失败、窗口权限错误、后台点击失败、Chromium CDP 连接失败等，可能发生在 MCP 成功启动之后，**本程序当前不能定位根因**。请参见[排查手册](docs/TROUBLESHOOTING.zh-CN.md)。

## 安全原则与测试

不启动被配置的命令，不上传数据，不自动联网，不采集 Cookie，不修改 Codex 配置。源码中的默认报告仅包含诊断代码、泛化文案、计数和运行平台。共享 JSON 前仍应人工审核。

```powershell
py -3 -m pip install -e .
py -3 -m unittest discover -s tests -v
py -3 tools/security_preflight.py --source .
```

已有 94 项本地测试通过，且配置了 Windows/Linux 的 GitHub Actions 测试矩阵；**尚未在 Windows 实机验收，也尚未在公开仓库触发 GitHub CI**，两者不是一回事。十轮审查的测试范围和剩余风险见[审查报告](docs/AUDIT.zh-CN.md)，新一轮发布安全专项检查见[安全审查](docs/SECURITY_AUDIT.zh-CN.md)。

MIT License。独立社区项目，不代表 OpenAI、Microsoft 或 Playwright 的官方产品。
