# v0.2.1 发布前专项安全审查（2026-10-21）

审查范围：CLI 源码、MCP 配置解析、异常输出、环境变量与路径检查、发布压缩包、wheel、sdist、依赖声明、GitHub Actions。**当前执行环境为 Linux，不能替代真实 Windows / Codex 桌面实测。** 本记录只陈述已实际执行的验证和未验证项。

## 发现并修复的发布阻断问题

- 深度嵌套 TOML（不到 2 MiB）可能触发 `RecursionError`，产生未捕获回溯。已改为受控错误报告。
- 数量极大的 TOML 整数 timeout 可能在 `math.isfinite` 转换中触发 `OverflowError`。现用整数安全范围检查。
- 超长可执行路径、无法访问的工作目录、PATH 查找权限异常等，会抛出包含原始用户路径的系统异常，若复制 CLI 输出到公开 issue，可能形成隐私泄漏。现将文件系统检查失败按“无法核实”处理，**不输出异常内容或敏感路径**。
- 发行流程以前没有独立检查“意外打包进来的隐私文件”。现新增 `tools/security_preflight.py`，逐文件检查源码、wheel、ZIP 和 sdist；预防常见 token、私钥块、 `.env`、私有 `config.toml`、二进制文件、zip 路径穿越和 tar 符号链接被意外发布。GitHub CI 增加源码预检。GitHub Actions 的 checkout/setup-python 由移动标签改为官方仓库核对过的完整 commit SHA，降低构建工作流供应链漂移风险。

## 安全边界

诊断时不开启 MCP，不执行 TOML 中命令，不访问配置里的 URL，不发送 telemetry，不抓浏览器数据，不改原始配置。默认隐藏 MCP 名称、配置路径和配置数值；`--show-server-names` 为显式选择，会曝光部分符合格式要求的自定义名称，因此分享报告应避免使用此选项。

## 不能伪称已验证

- 静态、启发式凭据扫描**不是**“证明不存在任何密钥”，无法识别所有自定义 token/编码形式或自然语言中的隐私。必须继续人工审阅发布内容。
- `OK` 不能证明 MCP 可启动、可调用、可信或网络可达；本项目不是杀毒软件。
- 不读取真实用户私有配置/账户，不自动扫描整个 Windows 磁盘。
- 尚无真实 Windows 安装验收，GitHub Actions 在正式仓库创建前也尚未执行；需公开后查看 CI 才能宣称 CI 通过。

## 本次复核脚本

```bash
python -m unittest discover -s tests -v
python -m compileall -q src tests tools
python tools/security_preflight.py --source . --artifact dist/<wheel> --artifact dist/<sdist> --artifact <source-zip>
```

校验工具只打印问题类型和数量，不显示凭据内容。源码压缩包要以明确的发布文件清单构建，而不是直接压缩整个工作目录。
