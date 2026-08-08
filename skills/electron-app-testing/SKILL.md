---
name: electron-app-testing
description: 实测/跑一遍 Electron 桌面应用时使用：启动 dev、找隐藏窗口、读 console、取证。
---

# Electron App Testing & Debugging (macOS)

## Purpose / 何时用
- 实测/跑一遍 Electron 桌面应用（U-NO/AIRI、OpenChatCut 等），边跑边记录问题与 BUG
- 排查：启动失败、主窗口不显示、renderer 报错、按钮点击无效、本地端口服务未就绪

## 1. 启动 dev 模式
- 后台启动：`terminal(background=true, watch_patterns=["Local:", "error", "EADDRINUSE"])`，`workdir=仓库根`
- 首次启动会跑 vite optimizeDeps：`new dependencies optimized → reloading` 是正常现象（页面热重载一次），不是 BUG
- 启动后先 `lsof -iTCP -sTCP:LISTEN -P` 摸端口面；Electron 主进程的 WS/HTTP 服务是 app 的 channel/MCP 面
- 注意：`screencapture -R` 需要屏幕录制权限；vision provider 未配置时，视觉证据改走 AX 树 + 日志 + 端口探测

## 2. 窗口发现（关键技巧）
- **cua-driver 的 list_windows 会漏窗口**：layer 1001 浮动/置顶窗、隐藏窗、off-screen 窗经常不出现（如 Electron 宠物主窗）
- 用 Swift `CGWindowListCopyWindowInfo` 枚举**所有**窗口（含隐藏），拿 winNum/layer/onscreen/alpha/bounds/name：
  ```bash
  swift -e 'import CoreGraphics
  let wl = CGWindowListCopyWindowInfo([.optionAll], kCGNullWindowID) as? [[String: Any]] ?? []
  for w in wl { let o = w[kCGWindowOwnerName as String] as? String ?? "?"
    if o.contains("Electron") { print(w[kCGWindowNumber as String] ?? "?", w[kCGWindowLayer as String] ?? "?", w[kCGWindowName as String] ?? "", w[kCGWindowBounds as String] ?? [:]) } }'
  ```
  或直接跑本技能脚本：`swift ~/.hermes/skills/software-development/electron-app-testing/scripts/cgwindows.swift [ownerSubstring]`
- 找到目标窗口后，用 `computer_use(capture, pid=..., window_id=...)` 精确定位，别依赖 frontmost
- `CGWindowListCreateImage` 在 macOS 26 已废弃（改用 ScreenCaptureKit）——不要走这条截图路

## 3. 读 renderer console（无 CDP 时）
- Electron dev 模式常开 detached DevTools 窗口；AX 树里点 Console 标签后，console 行以 `AXStaticText` 呈现（label 即文本）
- 输出大时结果自动存文件 → `grep -oE '"label": "[^"]{10,200}"'` 提取，过滤 CSS 变量噪音
- 常见信号解读：
  - `[intlify] Not found 'X' key in 'zh'/'en'` + fallback 刷屏 = **i18n 缺翻译键**（真 BUG 信号，说明新增 provider/文案未加翻译）
  - `Electron Security Warning (Insecure Content-Security-Policy)` = dev 模式常见（打包后不显示，但 CSP 缺失问题仍在，记入隐患）
  - `[render-kernel] motion.started` / Live2D Cubism Core init OK = 渲染正常
  - `WS skipped: anonymous user` 等 = 未登录的设计行为，别当 BUG

## 4. 日志与配置取证
- 日志：`~/Library/Application Support/<AppName>/Logs/*.log`（FileLogger 时间戳命名，读最新的）
- 配置：同目录 `app-config.json`（窗口位置）/ `app-options.json`（语言）/ `server-channel-config.json`（authToken）/ `mcp.json`
- WS 服务验证：python socket 发 `GET / HTTP/1.1 ... Sec-WebSocket-Key` 握手，收到 `101 Switching Protocols` 即通
- MCP server 常有前置 guard：如「需先选 Obsidian 仓库」（`vaultService.getRegisteredPath()` 为空直接拒绝启动）——先读源码 `start()` 的 guard 再判断是 BUG 还是待配置

## 5. 交互测试陷阱
- **AXPress / pixel 点击对透明浮动窗（layer 1001）内按钮可能被吞**：AX 树能看到按钮、点击返回 ok，但窗口不出现
- ⚠️ **窗口 ID（winNum）在关闭/重开后会变**：CGWindowList 枚举拿到的 winNum 只在当次枚举内有效；窗口重建后 ID 变化（实测 onboarding 关/开后 1041→1119→1085 变过多次）。**循环自动化必须每轮重新枚举拿新 ID**，用旧 ID/旧坐标点击会落空——用户中途喊「暂停」打断循环的那次就是旧坐标连点不生效。
- 区分「自动化失效」vs「真 BUG」：① 让真人手点确认；② 从源码确认事件链（`@click → Eventa IPC → 主进程 openWindow`），若链路正常而窗口未建，多半是点击没传进 WebView
- 权限弹窗（录屏/麦克风/系统设置）**不自动点**，交给用户处理
- 主窗口按钮无 label 时，从源码定位控件（如 `controls-island/index.vue`）确认按钮功能映射

## 6. 主进程崩溃弹窗（EPIPE）根因模式
- 现象：打开任意窗口/触发日志时弹「A JavaScript error occurred in the main process — Uncaught Exception: Error: write EPIPE」，堆栈指向 logger（如 `@guiiai/logg` 的 `outputToConsole`）+ node stream
- 根因链：logger 直接 `console[method]()` 无 try/catch → stdout 是 PIPE（agent 后台启动/会话中断后读端关闭）→ 写 console 触发 EPIPE → **主进程无 `process.on('uncaughtException')` 兜底** → Electron 默认崩溃框
- 排查三步：① `grep -rn "uncaughtException" src/main/`（空 = 无兜底，是真缺陷）；② `lsof -p <pid> | grep -E "1u|2u"` 看 stdout 是否 PIPE；③ 读 logger 源码看 write 是否包 try/catch
- 判定：agent 后台启动会放大此问题，但「无 uncaughtException 兜底 + logger 无容错」本身是发布版也会踩的健壮性缺陷（launchd/管道/重定向启动同样触发）
- 修复方向：主进程注册 uncaughtException handler（记录并忽略 EPIPE 类）；logger 写 console 包 try/catch

## 7. Live2D 渲染层故障排查（只显示局部/部件缺失）
- 现象：Cubism Core 初始化 OK、`motion.started` 在播（模型加载成功），但角色主体不渲染，只剩某个部件（如蝴蝶结）在动
- **✅ 已验根因（2026-08-07 U-NO 实测）**：渲染循环正常（WebGL 插桩：drawElements/bindTexture 大量、MVP 无 NaN、GL 无错误）时，**首要嫌疑是渲染引擎与 Core 运行时版本不兼容**——untitled-pixi-live2d-engine 内置 Framework 5-r.4 只支持 Cubism Core 5.x，配 Core 6.0.1 主体不渲染。解法：把 Core 降级到引擎支持的版本（改 SDK URL + 同步改 index.html 引用 + 清缓存），上游 issue 常有官方验证结论
- 分层定位：模型 zip 完整性（`unzip -l`）→ model3.json 路径 → drawable 渲染顺序（Core R5 把 `renderOrders` 改名 `drawOrders`，旧 Framework 补丁常漏路径）→ 纹理绑定
- ⚠️ **readPixels 全透明≠没渲染**：Pixi `preserveDrawingBuffer:false` 时 buffer 绘制后被回收，readPixels 恒 0——必须用 CDP `Page.captureScreenshot`（合成管线）看真实画面
- 取证：DevTools console 的 `[CSM][I]` / `[render-kernel]` 日志 + 用户截图（`tools:read-image` 描述画面），两者结合判断加载 vs 绘制故障
- 注意：多图视觉分析（4-5 张）单次 `read_image.py` 超 120s → 用 `terminal(background=true, notify_on_complete=true)` 跑，别前台阻塞

## 8. CDP 远程调试（拿 renderer 运行时真相，首选）
- **启动带调试端口**：`APP_REMOTE_DEBUG=true APP_REMOTE_DEBUG_PORT=9222`（项目原生开关，见 `src/main/app/debugger.ts`，自动配 `remote-allow-origins`）；`REMOTE_DEBUGGING_PORT` 环境变量也行但 origin 白名单要另配。正式模式无 9222。
- **⚠️ Electron 41 CDP origin 白名单**：WebSocket 连接必须带 `origin='http://localhost:9222'`，否则 403 `Rejected an incoming WebSocket connection`。Python websockets：`websockets.connect(url, origin='http://localhost:9222')`。
- 页面列表：`GET http://127.0.0.1:9222/json` → 找 `url.endswith('#/')` 且非 beat-sync 的 target。
- **Runtime.evaluate 探针**：`{'expression': expr, 'returnByValue': true, 'awaitPromise': true}`；异常在 `result.exceptionDetails`。
- **动态 import 项目模块**：页面顶层 import 包名常失败（Vite 只在编译期解析），用 `await import('/@fs/<绝对路径>')` 直接加载项目源码做运行时验证（如直接调 `loadLive2DModelPreview`、`mergeVtubeJsonIntoSettingsJson`）。HMR 后旧模块缓存残留 → 先 `Page.reload` 再测。
- **找 pinia store**：`window.__VUE_DEVTOOLS_GLOBAL_HOOK__.apps[0]._instance` 递归走 `subTree.component` 扫 `setupState` 里 `$id === '<store-name>'` 的对象；主窗口 store 列表可从 devtools hook 一次性枚举（`modelStore`/`chat-session` 等）。
- **拿真实画面**：`Page.captureScreenshot`（合成管线）；**readPixels 在 `preserveDrawingBuffer:false` 时恒 0 = 误判**（详见 §7）。
- **hook console**：`Runtime.enable` 后收 `Runtime.consoleAPICalled` / `Runtime.exceptionThrown`；Vite HMR 刷屏（`hot updated`）要过滤。

## 9. ⚠️ XHR 加载 blob: URL 在 Chromium 永久挂起（复用修复）
- **现象**：任何用 `XMLHttpRequest` 加载 `blob:` object URL 的代码（如 untitled-pixi-live2d-engine 的 XHRLoader 加载 zip 解压后的 model3.json/moc3/纹理）会**永远挂起**——onload/onerror 均不触发，`xhr.response` 恒 null → 外层表现为 "Network error" / 超时。
- **实测**：XHR + blob: 在 responseType=json/text/arraybuffer 下全部超时；`fetch(blobUrl)` 正常。
- **修复模式**（全局桥接，幂等）：patch `XMLHttpRequest.prototype.open`，当 GET + blob: URL 时改用 `fetch` 拉取，`origOpen` 保持状态机（否则 `send()` 报 InvalidStateError），`send` 置 no-op，成功后 `defineProperty` 写 status/response/readyState 并 dispatch load 事件。示例见 U-NO `live2d-zip-loader.ts` 的 `patchUntitledFileLoaderSanitization`。
- **定位技巧**：hook `XMLHttpRequest.prototype.open` + `window.fetch` 记 URL 日志，看引擎到底请求什么（blob: 还是相对路径）——区分「blob 挂起」vs「相对路径不可解析」。

## 10. 多窗口 Electron 应用：跨窗口 pinia store 隔离陷阱
- U-NO 每个 BrowserWindow（主窗口/Chat/Settings）是**独立 renderer + 独立 pinia store**，模型/表情状态只在加载模型的那个窗口有数据。
- **AI 工具运行在 Chat 窗口但模型在主窗口** → 工具读到的 expression store 是空的 → 报 "No Live2D model is currently loaded"、AI 说"没有模型加载"——**不是配置问题，是跨窗口状态没同步**（无 broadcast/IPC 同步机制，全仓 grep 可确认）。
- 排查顺序：① 确认 Chat 是独立 BrowserWindow（`new BrowserWindow` + 独立路由）；② grep 有无 `BroadcastChannel`/`webContents.send` 跨窗口同步；③ CDP 分别查两个窗口的 store 状态对比。
- 若 systemPrompt 动态注入动作/表情清单（从模型运行时读取），Chat 窗口构建的 prompt 会缺清单 → 模型不知道可用动作 → 只文字描述。修复方向：跨窗口同步模型状态，或工具执行转发到模型所在窗口。

## 11. VTS 导出模型的注册表在 vtube.json（model3.json 常空）
- VTS 导出皮套：model3.json 的 `FileReferences.Motions/Expressions` **经常为空**，动作/表情注册在 `*.vtube.json`：
  - `FileReferences.IdleAnimation` → 注入 `Motions.Idle`；**`IdleAnimationWhenTrackingLost` 也属 Idle 语义**（失焦待机），容易漏
  - `Hotkeys[]`：`Action: "ToggleExpression"` + `File: *.exp3.json` → `Expressions`；**`Action: "TriggerAnimation"` + `File: *.motion3.json` → Motions 组**（组名=热键 Name）——很多 loader 只处理 exp3 漏掉 TriggerAnimation，导致动作清单只剩 Idle
  - `RemoveAllExpressions` 复位热键 Name/File 均空，要过滤
- 排查：读 model3.json 的 Motions 数 vs 目录实际 motion3.json 数；缺引用时检查 vtube.json。修复模式见 U-NO `mergeVtubeJsonIntoSettingsJson`（ensureMotions/pushMotion 辅助 + 按 File 去重）。
- **模型大小限制真相**：审计器 `>30MB` 是 WARNING（HEAVY RESOURCE，可导入）、`>100MB` 是 ERROR（阻止）；zip 大小 ≠ MOC 大小（纹理占大头）。真正阻止导入的常是 **BASENAME COLLISION**（多子模型同名纹理/exp3 → INVALID）——拆成单模型包即可。

## References / Scripts
- `references/uno-app.md` — U-NO（moeru-ai/airi fork）实测档案：启动命令、端口面、数据目录、主窗口按钮表、2026-08-07 已知 BUG 清单
- `scripts/cgwindows.swift` — 枚举 macOS 全部窗口（含隐藏/置顶/离屏），可按 owner 过滤
- `references/uno-cdp-debugging.md` — CDP 远程调试 U-NO 实战：探针脚本模式、WebGL 插桩、Vue store 遍历、blob XHR 桥接修复细节
