---
name: coding-agent-cli-orchestration
description: "Wiring/debugging external coding CLIs (opencode/codex)."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Coding-Agent, Orchestration, OpenCode, Codex, Claude-Code, Troubleshooting]
    related_skills: [opencode, codex, claude-code, hermes-agent]
---

# Coding Agent CLI Orchestration

把 Hermes 与外置编码 CLI(OpenCode / Codex / Claude Code)「串联」:安装检查 → 认证检查 → 冒烟测试 → 故障修复 → 委派。当用户问「如何让你与 X 建立串联」、委派 CLI 冒烟失败、或默认模型/provider 行为异常时使用。

具体 CLI 的完整用法(flag、TUI 键位、PR review、并行 worktree)见各自的 bundled 技能 `opencode` / `codex` / `claude-code`。本技能负责「能不能跑起来、跑起来用哪个模型、坏了怎么修」这一层。

## 串联就绪检查(按序执行,每步独立)

```bash
# 1. 二进制定位 — 可能有多个;npm 全局与 ~/.opencode/bin 可能并存
which -a opencode          # 或 codex / claude
ls ~/.opencode/bin/opencode 2>/dev/null; ls /opt/homebrew/bin/opencode 2>/dev/null
npm ls -g | grep -i opencode

# 2. 版本
opencode --version

# 3. 认证/provider
opencode auth list         # 显示已配置的 credentials(可能多个 provider)

# 4. 可用模型(确认 provider 名下有哪些模型可指定)
opencode models
```

## 冒烟测试(必须先建 git repo —— 所有编码 CLI 都拒绝在非 git 目录运行)

```bash
cd $(mktemp -d) && git init -q . && opencode run 'Respond with exactly: OPENCODE_SMOKE_OK'
```

成功判据:输出包含 `OPENCODE_SMOKE_OK` 且 exit 0。`opencode run` 不需要 pty;交互 TUI 才需要 `pty=true`。

## 故障排查

### 读取实际生效模型
运行输出首行形如 `> build · <model>` —— **这是实际使用的模型,不是你以为配置的那个**。先读它再判断。

### `Insufficient account balance` / 401 / auth 错误
= provider 凭证有效但余额不足(或 key 失效)。这不是 CLI 坏了:
1. `opencode models` 看该 provider 名下模型;
2. 临时指定可用 provider: `opencode run '...' --model deepseek/deepseek-chat`;
3. 长期修复:显式配置默认模型(见下)。

### 默认模型选错(OpenCode 特有坑)
**`opencode.jsonc` 未声明 `"model"` 字段时,OpenCode 自动选第一个 provider 的模型**,而不是"最好的"或"最近用的"。本机实测:配置里只有 autodl provider 时,默认跑 autodl/claude-fable-5,直接撞余额不足。
修复(最小外科手术):在 `~/.config/opencode/opencode.jsonc` 顶部加一行:
```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "model": "deepseek/deepseek-chat",
  ...
}
```

### 配置路径速查
| CLI | 全局配置 | 默认模型字段 |
|-----|---------|-------------|
| OpenCode | `~/.config/opencode/opencode.jsonc` | `"model": "provider/model"` |
| Codex | `~/.codex/config.toml` | `model = "..."` / `model_providers` |
| Claude Code | `~/.claude/settings.json` | `"model"` |

### PATH 双二进制陷阱
Shell 环境可能解析到不同二进制(`which -a` 列出全部)。行为不一致时显式 pin:`$HOME/.opencode/bin/opencode`。

## 验证修复(关键)

改完配置后,**必须不带覆盖参数重跑冒烟测试**,确认默认真正生效:
```bash
cd $(mktemp -d) && git init -q . && opencode run 'Respond with exactly: OPENCODE_SMOKE_OK' 2>&1 | grep -E 'build|SMOKE'
```
输出 `> build · deepseek-chat` + `OPENCODE_SMOKE_OK` = 修复生效。仅用 `--model` 参数验证不算验证默认值。

## 委派模式速记

- **one-shot**:`opencode run '任务'`(无需 pty,git repo 内)
- **后台迭代**:`terminal(background=true, pty=true)` 起 TUI,`process(action=submit/poll/log)` 交互
- **并行**:独立 workdir / `git worktree`,各自跑一个 CLI 进程
- 具体 flag 与 PR review 流程 → 加载 `opencode` / `codex` / `claude-code` 技能

## 用户环境现状

本机(2026-08)的 CLI 安装、provider、可用模型清单、codex 桌面应用布局见 `references/user-env.md` —— 环境会变,用时先快速复核。

## Pitfalls

- 冒烟测试报错先看 `> build · <model>` 行,不要盲目重试同一命令。
- 默认模型修复后不重跑冒烟验证 = 没验证(带 `--model` 跑通不算数)。
- 编码 CLI 都要求 git repo;`mktemp -d && git init -q .` 是通用脚手架。
- 用户偏好最小修改:只加 `"model"` 一行,不动 provider/plugin/MCP 等其他配置。
