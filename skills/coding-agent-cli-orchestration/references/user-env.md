# 用户机器编码 CLI 环境(快照 2026-08-07,用时先复核)

## OpenCode — 已装、可用、默认模型已修

- 版本:1.18.13,npm 全局安装 → `~/.local/bin/opencode`(PATH 内)
- 认证:`opencode auth list` → 2 个 credentials:**DeepSeek api** + **autodl api**
- 可用模型(`opencode models`,2026-08):
  - `deepseek/deepseek-chat` ← 默认(已配置)
  - `deepseek/deepseek-reasoner`
  - `deepseek/deepseek-v4-flash` / `deepseek/deepseek-v4-pro`
  - `opencode/deepseek-v4-flash-free`
  - `autodl/claude-fable-5`(autodl 账号余额不足,报 `Insufficient account balance`)
- 全局配置:`~/.config/opencode/opencode.jsonc`
  - 2026-08-07 已加 `"model": "deepseek/deepseek-chat"`(此前无 model 字段 → 默认选中第一个 provider = autodl,冒烟失败)
  - 另有:superpowers 插件(git+superpowers)、MCP: context7(remote)、playwright(local)、sequential-thinking(local)
- 冒烟测试 `OPENCODE_SMOKE_OK` 已验证通过(不带 --model,默认 deepseek-chat)

## Codex — 桌面应用在用,CLI 未装到 PATH

- `which codex` / npm 全局 → 无。**CLI 藏在 ChatGPT.app 资源内**:`CODEX_CLI_PATH = /Applications/ChatGPT.app/Contents/Resources/codex`
- 桌面应用数据目录 `~/.codex/`:
  - `auth.json`(存在,Codex OAuth)
  - `config.toml`:`[mcp_servers.node_repl]`(cua_node 路径)、`computer-use`(SkyComputerUseClient,enabled=false)、`openchatcut`(http://localhost:5199/api/external-mcp/mcp)、`[model_providers.deepseek]`(base_url https://api.deepseek.com/, wire_api=responses)
  - `AGENTS.md`:用户给 Codex 的规则(浏览器偏好 in-app browser、ComfyUI 出图护栏、Live2D 皮套 SOP 强制流程)
- Hermes 侧:`~/.hermes/config.yaml` 有 `codex_gpt55_autoraise: true`、`codex_app_server_auto: native`;`~/.hermes/auth.json` 注释提及 `openai-codex (OAuth — hermes auth)` provider
- 若用户要 Hermes↔Codex 串联:选项 A) 装 CLI `npm i -g @openai/codex` 走委派;选项 B) `hermes auth add openai-codex` + `model.provider: openai-codex` 让 Hermes 直接跑 Codex 模型;选项 C) 复用 ChatGPT.app 内 CLI 二进制(pin 绝对路径)

## 通用提示

- 用户机器所有编码 CLI 都要求 git repo;冒烟脚手架 `mktemp -d && git init -q .`
- 用户偏好最小修改:修默认模型只加一行,不动其他配置
- Shadowrocket 代理常开(fake-IP 198.18.0.x)—— CLI 联网调模型一般无碍,但测速/公网 ping 会被干扰
