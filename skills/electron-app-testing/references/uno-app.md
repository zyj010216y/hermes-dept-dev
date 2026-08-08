# U-NO（moeru-ai/airi fork）实测档案

> 实测日期：2026-08-07。工作区有 130 个未提交文件（+4146/-1028 行），跑 app 前先 `git status` 了解改动面。

## 项目形态
- 仓库：`~/Desktop/U-NO`，基于 moeru-ai/airi 0.11.3 的剪枝增强分支
- 定位：单机优先的虚拟角色 AI Agent（Live2D 皮套 + 本地 LLM/TTS + 角色卡驱动行为）
- 技术栈：Electron 41 + Vue3/Vite + TypeScript + Pinia + UnoCSS；pnpm 10.33.0（packageManager 固定）
- 目录：`apps/stage-tamagotchi`（唯一 app），`packages/stage-ui` / `stage-ui-three` / `server-sdk` 等

## 启动
```bash
npx -y pnpm@10.33.0 -F @uno/stage-tamagotchi dev   # 或双击 启动U-NO.command
```
- 需 Node >= 22；node_modules 已装好
- 启动后：主窗口 292×358 宠物窗 @ 屏幕右上（layer 1001 置顶浮动）+ detached DevTools（800×600 @ 左上）

## 端口面（2026-08-07 实测）
| 端口 | 服务 | 备注 |
|---|---|---|
| 6121 | `@uno/server-runtime` WebSocket（channel-server） | authToken 在 `~/Library/Application Support/U-NO/server-channel-config.json`；WS 握手 101 正常 |
| 5173 | Vite dev server（renderer） | |
| 53089 | channel-server 的 h3 HTTP 面 | 所有 GET 路由 404 是正常行为（非 HTTP API） |
| MCP /mcp | U-NO MCP server（StreamableHTTP） | **未启动**：`vaultService.getRegisteredPath()` 为空直接拒绝——需先在设置里选 Obsidian 仓库（`mcp-server/server.ts:447`） |

## 数据目录 `~/Library/Application Support/U-NO/`
- `app-config.json`：窗口位置（x/y/width/height/tag）
- `app-options.json`：language（zh-Hans）
- `server-channel-config.json`：authToken/hostname
- `artistry-options.json`：artistryProvider（none）、comfyui/replicate/nanobanana 配置
- `mcp.json`：外部 MCP 服务器注册（当前空）
- `Logs/airi-tamagotchi-<ts>.log`：FileLogger 主进程日志（injeca DI 全链路可见）

## 主窗口控件（controls-island，`src/renderer/components/stage-islands/controls-island/index.vue`）
- 左上 48×48 圆形按钮：「已连接. 打开连接设置」
- 右侧竖排 40×40 ×6：设置(`/settings`) / toggle / 聊天 / 刷新窗口 / 重置位置 / 深色模式
- 事件链：`@click → useElectronEventaInvoke(electronOpenSettings) → 主进程 settingsWindow.openWindow()`

## 2026-08-07 已知 BUG/问题清单
1. **auto-updater 双故障**：GitHub releases API 404 + fetch ETIMEDOUT（fork 无 release，每次启动外联）→ 应禁用或本地化
2. **`[intlify] Not found 'Atlas Cloud' key` 刷屏数十条**：`providers.ts:2942-2968` 新增 provider 缺 zh/en 翻译键 → 加 i18n 键
3. **artistry-bridge 重复告警**：renderer 每次 syncConfig 尝试写主进程专属密钥（replicateApiKey/nanobananaApiKey）被拒 → 同步协议应剥离 secret 字段
4. **CSP 缺失**：Electron Security Warning（dev 常见，打包后不显示但问题仍在）
5. **MCP server 未启动**：需先选 Obsidian 仓库（待配置，非代码 BUG）
6. `[chat-sync] WS skipped: anonymous user`：未登录设计行为，非 BUG
7. `[render-kernel] motion.started Flick/Tap/FlickDown/FlickUp 0`：待机动作正常
8. **主窗口按钮点击**：AXPress/pixel 被吞（layer 1001 透明置顶窗），但**用户手测"大部分正常"** → 确认是自动化点击失效，非 UI BUG（真人手点可用）
9. **🔴 EPIPE 主进程崩溃框**：打开 Settings/Chat/Notice 窗口必弹「Uncaught Exception: Error: write EPIPE」（5 张截图实证）。根因：`@guiiai/logg@1.2.11` 的 `outputToConsole` 直接 `console[method]()` 无 try/catch + 主进程无 uncaughtException 兜底；agent 后台启动管道断开放大。修复：主进程注册 uncaughtException handler + logger 容错
10. **🔴 Live2D 主体不渲染只剩蝴蝶结 —— ✅ 已修复（Core 降级 5-r.4，方案 A）**：moc3/motion 加载成功（Core 6.0.1 OK、motion.started 在播），但角色脸/身体完全缺失，仅蓝色蝴蝶结部件在动（主窗口截图实证）。**根因（CDP + WebGL 插桩 + GitHub 调研）**：untitled-pixi-live2d-engine（README 声明仅支持 Cubism 2/3/4/5）内置 Framework 5-r.4 **不兼容 Cubism Core 6.0.1**（上游 issue #11 官方验证：换 Core 5.x 即正常）。U-NO 的 Core 来自 `electron.vite.config.ts:314` 的 `DownloadLive2DSDK`（SDK 5-r.5 zip 自带 Core 6.0.1）。渲染循环本身正常（drawElements/bindTexture/uniformMatrix4fv 大量调用、MVP 无 NaN、GL 无错误），**readPixels 全透明是 preserveDrawingBuffer:false 的误判**（用 CDP Page.captureScreenshot 看真实画面）。**修复**：`electron.vite.config.ts:314` URL 改 `CubismSdkForWeb-5-r.4.zip` + `index.html:12` script src 同步改 + 清 `.cache`/`public`/`out` 下全部 5-r.5 目录，重启后插件自动下载 5-r.4 Core。**已确认成功（21:48 截图 + 视觉分析）**：完整 hiyori 角色（脸/双马尾/红发饰/米色开衫/水手领/领结）占画面 80%+。验证链：typecheck exit 0 + 5-r.4 URL 200 text/javascript + 5-r.5 URL 200 text/html（Vite SPA fallback，非残留）+ find 残留 0。
11. **Model Audit Report 弹窗（导入自定义模型时）**：同名 basename 纹理冲突（BASENAME COLLISION，如多个子模型目录各有 `texture_41.png` → AIRT loader 按文件名索引互相覆盖贴图错乱）+ MOC 过大警告（HEAVY RESOURCE，~31MB）。不影响默认 hiyori 模型；用户可重命名冲突纹理或 Cancel 关闭。详见 electron-app-debugging 技能 references/uno-airi.md。
12. **🔴 自定义模型预览 "Preview unavailable"（导入任意 zip 均失败）—— ✅ 已修复**：untitled 引擎 XHRLoader 用 XMLHttpRequest 加载 blob: URL **永久挂起**（Chromium 限制，onload/onerror 不触发）→ urlToJSON middleware 卡死 → 预览超时返回 undefined；另有跨模块副本 `instanceof ModelSettings` 失败。修复：`live2d-zip-loader.ts` 全局 XHR blob: → fetch 桥接补丁 + `live2d-preview.ts` untitled 预览复用 `{url,id}` OPFS 路径。验证：CDP 实测 hiyori 238KB / 伊拉利娅 900KB 预览生成成功。
13. **🔴 AI 说"没有模型加载"、无法做动作 —— ✅ 已修复（VTS vtube 桥增强）**：根因两层——① Chat 窗口是独立 BrowserWindow，pinia store 与主窗口隔离，AI 工具读不到模型状态（跨窗口架构缺陷，见 SKILL §10）；② 更底层：自定义 VTS 模型（镌恒执刀/伊拉利娅）model3.json 的 Motions/Expressions 为空，注册表在 vtube.json——原 `mergeVtubeJsonIntoSettingsJson` 只处理 IdleAnimation + exp3 热键，**漏了 `IdleAnimationWhenTrackingLost` 和 `TriggerAnimation` 动作热键** → availableMotions 只剩 1 个 Idle → systemPrompt 动作清单空 → AI 不知道可用动作。修复：`live2d-zip-loader.ts` merge 增强（ensureMotions/pushMotion + TrackingLost + TriggerAnimation）。验证：镌恒执刀 1→4 个动作（待机/打瞌睡/签名/沙漏），render-kernel `motion.started 签名动画` 实测播放。
14. **MaxListenersExceededWarning（11 move/resize listeners）—— ✅ 已修复**：`onboarding/index.ts` 的 `electronOpenOnboarding` handler 每次打开 onboarding 窗口都 addEventListener（move/resize），cleanup 只在窗口关闭时执行；窗口开着时再次 toggle → 累积。修复：进入 handler 前先 `detachMainMoveListener?.()` 移除上一轮监听器。验证：6 次开/关循环日志 0 警告。
15. **AI 回复泄露内部推理文字（thinking/reasoning 显示在气泡）**：Chat 消息直接显示了模型思考过程（"The user is just saying 嗯..."）。未修复，待查消息组装层是否应过滤 reasoning 内容。

## 测试注意
- 日志：读最新 `Logs/airi-tamagotchi-*.log`（FileLogger + injeca 依赖树，可看窗口/服务初始化时序）
- Electron 进程树：`node_modules/.pnpm/electron@41.2.1/.../Electron.app/Contents/MacOS/Electron .`（user-data-dir 指向 U-NO）
- 权限弹窗（录屏/麦克风）出现时交给用户处理，勿自动点击
