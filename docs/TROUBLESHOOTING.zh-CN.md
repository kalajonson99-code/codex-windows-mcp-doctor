# Codex Windows MCP 故障排查手册

诊断器只检查配置，不代表 MCP 连接成功。显示 `OK` 后，浏览器还是可能读不到网页，Computer Use 还是可能打不开。

## Codex 看不到 MCP

运行 `codex mcp list`，与静态报告核对。Codex 可能有用户级、项目级、系统管理配置；项目级配置的生效还与项目信任状态等有关。可用 `codex-mcp-doctor --project D:\项目目录` 单独检查项目配置，但两份报告不会自动合并。

## `npx` / `npm` / `node` 找不到

PowerShell 检查：

```powershell
Get-Command npx
Get-Command node
node --version
```

PowerShell 能找到不代表启动已久的 Codex 桌面版也能找到。若服务器独立设置了 `env.PATH`，当前终端找不到同样不等于服务器一定找不到。不要直接删除或覆盖 PATH，修改后按需重新启动软件再测试。

## MCP 启动正常，浏览器读取偶尔失败

可能是扩展连接、CDP、浏览器会话、弹窗、网站权限、MCP 协议握手或 Codex 路由问题。请在无敏感信息的测试网页复现，结合 MCP 自身日志定位。静态诊断器不会连接网页，不能提供具体根因或成功率。切勿公开 Cookie、Token、带认证参数的完整 URL。

## Computer Use 不能用

操作系统无障碍权限、窗口前后台切换、GUI 驱动服务、Codex 权限检查等都可能影响桌面控制。本项目目前**不修复也不绕过**这些问题。建议用 Windows 记事本做独立验收，再考虑接入业务软件。

## `WARNING` 该不该信

`ENV_VAR_MISSING` 表示运行本诊断器的 Python 进程看不到变量，不代表所有 Codex 客户端都看不到。`*_UNVERIFIED` 表示无法确定，而不是断言某个文件不存在。把诊断工具当成排除静态问题的筛子，而不是替代运行测试的裁判。

## 官方参考

- [Codex MCP 文档](https://developers.openai.com/codex/mcp)
- [Codex 配置说明](https://developers.openai.com/codex/config-reference)
- [Playwright MCP](https://github.com/microsoft/playwright-mcp)
