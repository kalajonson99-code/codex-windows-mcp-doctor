# v0.2.0 十轮深度审查记录

审查时间：2026-10-21。起点：v0.1.0，35 项本地单元测试；最终 v0.2.0 共有 81 项测试通过。另外做了 400 组随机类型/数值组合的非破坏性健壮性试探，未遇到未处理异常。目标：避免 Windows/Codex MCP 静态诊断**误报、漏报、误导和隐私泄漏**，不凑与用户无关的功能。

下列是**十个不同风险维度的审查**，不是将一套测试重复执行十次。每轮均在当前代码上以独立用例或构建核对，未发现问题的地方直接记录为保持原设计。

| 轮次 | 实际场景 / 核对方法 | 结果 / 处理 |
|---|---|---|
| 1 | 基线回归：从 v0.1.0 的 35 项测试开始 | 保留原测试并修正仅有的兼容性问题；未把原逻辑无故全部推翻 |
| 2 | 对照 Codex 官方 MCP 文档逐字段核验 | 补齐 `env_vars` 混合对象/remote source、`cwd`、HTTP headers、timeout alias，避免合法配置被误报 |
| 3 | 工作目录与 Windows 启动器 | 识别文件夹不能当可执行文件；相对命令找不到 cwd 不再断言失败，`.cmd` 回退仍可验证 |
| 4 | 环境变量在 PowerShell 与 GUI 中不一致 | 区分当前 Python 环境与 Codex 进程；支持 Windows 环境变量名大小写不敏感；有自定义 PATH 时降低确定性 |
| 5 | HTTP 地址真实性与安全 | 检查端口、URL 账户密码、fragment、空白、IPv6 loopback、127/8 回环及明文远程 HTTP |
| 6 | 不完整/冲突设置 | 检查 command/url 冲突、禁用项、超时数值、HTTP headers、工具允许/拒绝列表冲突 |
| 7 | 防止执行不可信配置内容 | 用恶意 Python 命令和文本测试，保证诊断不会运行 shell/MCP、改写文件或跟随参数执行 |
| 8 | 报告隐私保护 | 用伪密钥、私有服务器名称、URL query、环境变量名、私人目录测试文本与 JSON 输出均不泄露原始配置 |
| 9 | 异常输入与资源上限 | 文件不存在、无法读取、重复 TOML 键、控制字符、超过 2 MiB 文件、超过 512 项服务器均给出有界的结果 |
| 10 | CLI 与发布包回归 | `--json`、`--strict`、`--project` 退出码，文档与源码版本一致性；单元测试+构建包+隔离安装验证；补齐 sdist 缺失中文文档的实际问题 |

## 不编造的限制

- **不是 Windows 实机测试：** Windows 的启动器探测由模拟测试覆盖，但尚未在真实 Codex Windows 桌面环境完成验证。
- **不是断线排查神器：** 不能检查 MCP JSON-RPC 初始化、Playwright/CDP、扩展授权、窗口句柄或 Computer Use 内部工具是否可见。
- **不恢复“最终有效配置”：** 只检查指定的一个 TOML 文件；不会合并其他 Codex 管理配置、项目级配置、Profile 或信任规则。
- **不保证无误报/漏报：** 仍依赖所运行进程的 PATH、环境变量与静态规则；报告只支持排查，不替代最终运行验收。
- **不上传或发布：** 仓库公开发布、GitHub CI 和 Windows 实机测试均属于下一阶段，绝不能冒充已完成。

## 如何复核

在项目根目录运行：

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m build --wheel --sdist
```

`python -m build` 需额外安装构建工具；如果没有这个包，也可以执行 `python -m pip wheel --no-deps --no-build-isolation .`。测试均使用模拟配置，不读取用户隐私。

官方依据：[Codex MCP](https://developers.openai.com/codex/mcp)；[配置参考](https://developers.openai.com/codex/config-reference)。
