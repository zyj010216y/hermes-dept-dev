---
name: app-mcp-integration
description: 为桌面应用构建 MCP 集成：枚举 API、设计工具、注册 codex。
---

# 桌面应用 MCP 集成

把桌面应用（图形编辑器、建模工具等）接入 AI Agent（codex 等 MCP 客户端）的完整方法论。
本技能源自 Cubism Editor 5.4 alpha（原生 WS API）与 Krita 5.3.3（无远程接口，插件内嵌服务器）两条实战线。

## 触发条件
- 用户要求"做一个 MCP / 让 agent 能用 XX 软件所有功能"
- 需要枚举某应用的已知/未知 API 接口
- 需要评估/比较现有第三方 MCP 项目

## 第一步：枚举 API 面（先列清单给用户研究——用户明确偏好）

目标应用分两类，决定架构：

### A. 有原生远程接口（如 Cubism 外部应用集成，WS :22033）
- 官方文档优先：查官方手册/开发者文档（Cubism 手册在 cubism.live2d.com/editor-alpha/doc/，官方样例在 Live2D-Garage/CubismExternalAppPluginSamples）
- 类型桩/源码：.pyi 文件、官方客户端（ceplugin.py）比文档更全
- 反编译（jar/二进制）：混淆的常量池可能加密（Zelix 风格，标准工具读不出）——别陷进去，以官方文档+实测为准
- **实测验证为准**：文档写了的接口服务器不一定有（Cubism 5.4 的 SetParameterValue 单数 → MethodNotFound）；文档没写的可能真实存在（GetAPIVersion/SetPhysicsInfo）
- 产出：接口清单表（方法/请求字段/响应/实测状态/现有 MCP 覆盖缺口）

### B. 无原生远程接口（如 Krita）
- Krita 无 DBus(macOS)、无 WebSocket——外部控制必须走 pykrita 插件内嵌服务器
- API 面来源：应用自带 Python 的类型桩（Krita 的 krita.pyi 在 app bundle 里，46 类 786 方法）
- 现有第三方 MCP 项目先调研（GitHub 搜 "<app> mcp"），对比覆盖面和架构再决定 fork/重写

## 第二步：设计工具（按功能模块组装——用户明确偏好）

用户偏好：**按软件使用功能分模块组装工具**（如 Krita 的文件/图层/绘画/选择/滤镜…13 模块），
不要走"精简工具+execute_python 万能口"路线（虽然这路线 token 更省，用户明确选了前者）。

- 工具命名带模块前缀：cubism_xxx_* / krita_<模块>_* / live2d_*
- 每个工具手写类型签名（FastMCP 从签名生成 schema），参数用可选 + None 判定是否入请求体
- 枚举值用 Literal 约束（但少用——大枚举是 schema 膨胀源）
- 统一错误格式：{"ok": false, "error": "..."}，应用未运行/未连接时给友好提示（含排查步骤）

## 第三步：实现

- **mcp 依赖锁 <2.0**：`mcp>=1.0.0,<2.0`——mcp 2.x 移除了 mcp.server.fastmcp 导入路径，FastMCP 装不上
- 客户端层：sendAndWait 模式（RequestId 匹配响应）、默认超时（挂起接口如 Cubism GetCurrentDocumentUID 无文档时 8s 超时）、token 复用持久化
- 编辑类操作：事务包裹（EditBegin→Action→EditEnd，失败 Cancel 回滚）
- 无原生接口的应用：插件内嵌 HTTP 服务器，**线程模型关键**——HTTP 跑 daemon 线程，命令入队，QTimer 在主线程轮询执行（应用 API 只能在主线程调）；测试环境用环境变量禁用自启（如 KRITAMCP_NO_AUTOSTART）
- 项目结构：pyproject.toml（hatchling，[project.scripts] 入口）、src 包、README

## 第四步：验证（三步走）

1. **MCP stdio 握手测试**：临时脚本起子进程，JSON-RPC initialize → tools/list → tools/call，验证工具数和关键工具
2. **行为级测试**：monkeypatch 客户端层（ensure_ready/send_and_wait/edit_begin/edit_end），捕获实际请求体，断言字段正确进入（可选参数不传时不出现在请求）
3. **插件端测试**：stub 外部依赖（sys.modules 注入 MagicMock 模块），测注册表完整性 + HTTP 队列链路（手动调 poll 代替 QTimer）
- **token 开销测量**：tools/list 输出字节数 ÷4 ≈ tokens，55 工具 ≈ 11K tokens；报给用户做决策
- 每轮代码修改后重跑验证，临时脚本用 hermes-verify- 前缀放系统临时目录、跑完即删

## 第五步：注册 codex

~/.codex/config.toml：
```toml
[mcp_servers.<name>]
command = "<项目>/.venv/bin/python"
args = ["-m", "<pkg>.server"]
```
- codex 启动时拉起所有 enabled 的 MCP；不常用模组可加 enabled = false 按需启用
- 修改 config.toml 需重启 ChatGPT 应用才生效；pykrita 类插件需重启宿主应用
- 改动 config 前先 read_file 全量读（codex 会外部写入，注意警告）

## 注册 Hermes（hermes mcp add，2026-08 实战）

Hermes 侧注册与 codex 不同——**不要手改 ~/.hermes/config.yaml**（规范：用 `hermes config set` / `hermes mcp` 命令）：

```bash
hermes mcp add <name> --command /path/to/venv/bin/python --args /path/to/server.py
echo "y" | hermes mcp add <name> --command ... --args ...   # 交互确认工具启用
hermes mcp test <name>        # 验证连接 + 工具发现
hermes mcp list               # 查看 enabled 状态
```

- **`--args` 必须是最后一个选项**——放在它后面的选项（如 `--connect-timeout 30`）会被吞进 args 数组，成为传给 server 的参数
- add 会现场连接测试；成功后会交互问 "Enable all 3 tools?"——管道 `echo y |` 确认
- 工具名 = `mcp_<server>_<tool>`（横线/点转下划线）
- 测试失败仍可 `echo y` 保存为 disabled，再用 `hermes mcp test` 单独诊断

## stdio 部署三大坑（Connection closed 排查，2026-08 osint-collector 实战）

1. **fastmcp banner 污染 stdout**：fastmcp 默认启动打印 ASCII logo 到 stdout，而 stdio 协议要求 stdout **只有 JSON-RPC**——banner 会破坏握手（手动 printf 测试能通、客户端连接必失败）。修复：`mcp.run(show_banner=False)`
2. **Hermes spawn 继承 PYTHONPATH 遮蔽 venv 依赖**：Hermes 客户端进程的 PYTHONPATH 指向 hermes-agent 的 site-packages（含 mcp/pydantic 等），spawn MCP 子进程时被继承，导致服务器自身 venv 的包被遮蔽（如 curl_cffi 找不到）。修复：server.py 启动时把自身 site-packages **先 remove 再 insert 到 sys.path[0]**
3. **venv 依赖不完整**：curl_cffi 需要 cffi+certifi；fastmcp 需装 `fastmcp[all]`（pydantic 等）。坑：在污染 PYTHONPATH 下 `pip show` 会误报"已装"（实际是别的 venv 的）——用 `env -u PYTHONPATH <venv-python> -c "import ..."` 验证真实状态
4. **排查法**：客户端连不上时，用 mcp SDK 的 `stdio_client` 起子进程并把 `stderr=sys.stderr` 透传——服务端真实异常（ImportError 等）会暴露；裸 `printf JSON | python server.py` 测 stdout 纯净度，两者结合定位是 stdout 污染还是依赖缺失

## 常见坑
- 插件 GUI 启用：Krita 配置对话框的 AX 树文本读不到（Qt 自绘）——System Events 拿列表文本为空，computer_use 也可能 0 元素；别硬刚 GUI，让用户手动启用/重启，用 curl ping 验证
- printf '' > 建空文件会误清掉已写内容——建目录用 mkdir，别用重定向覆盖已有文件
- 验证脚本断言别太严格：FastMCP 对 Optional 类型生成联合 schema；被 mock 的方法不会记录进 send_and_wait 调用列表

## 参考文件
- references/cubism-external-api.md — Cubism 5.4 alpha 外部 API 完整知识（协议/方法清单/实测行为/手册 URL）
- references/krita-python-api.md — Krita 5.3.3 Python API 面 + 插件内嵌服务器架构 + 第三方 MCP 对比
