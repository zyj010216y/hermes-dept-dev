---
name: electron-app-debugging
description: 调试 Electron 桌面应用（macOS）时使用：窗口枚举、DevTools、EPIPE、i18n 刷屏。
---

# Electron App Debugging (macOS)

调试 Electron 桌面应用（U-NO、OpenChatCut、Hermes 等）的高频技术与坑。配套：`references/uno-airi.md`（U-NO/AIRI 项目专属：启动命令、端口、验证命令、已修 BUG、Model Audit 弹窗解读、未决问题）。

## 1. 窗口枚举 — cua-driver 看不到的窗口

cua-driver 的 `list_windows` 会漏掉**无边框/透明/置顶(layer 1001)** 的窗口（宠物窗、overlay、浮动层）。用 Swift CGWindowList 兜底：

```swift
swift -e '
import CoreGraphics
let opts = CGWindowListOption([.optionAll])  // .optionAll 能看到隐藏窗(onscreen=?)
if let wl = CGWindowListCopyWindowInfo(opts, kCGNullWindowID) as? [[String: Any]] {
    for w in wl {
        let owner = w[kCGWindowOwnerName as String] as? String ?? "?"
        if owner.contains("Electron") {
            let num = w[kCGWindowNumber as String] ?? "?"
            let name = w[kCGWindowName as String] as? String ?? ""
            let onscreen = w[kCGWindowIsOnscreen as String] ?? "?"
            let bounds = w[kCGWindowBounds as String] as? [String: Any] ?? [:]
            print("winNum: \(num) | \(name) | onscreen: \(onscreen) | \(bounds)")
        }
    }
}'
```

拿到 winNum 后用 `computer_use capture(pid=..., window_id=...)` 精确抓该窗口。注意区分：主窗口可能是 layer 1001 浮动层，DevTools 是 layer 0——先分清再操作。AX 树能列出按钮但 AXPress/像素点击可能被透明层吞掉，此时不能断定 UI 有 BUG，需真人验证。

**⚠️ 枚举时绝不要过滤 `layer == 0`（2026-08-08 实测被咬一整轮）**：`setAlwaysOnTop(true, 'screen-saver')` 的宠物窗/主窗口在 **layer=1001**，DevTools/Settings/BeatSync 才是 layer 0。若枚举脚本写成 `if layer == 0` 会**漏掉主窗口** → 误判「主窗口不存在/没创建/离屏」，接着会错误地往 show 兜底、重启实例方向排查（全是弯路）。正确姿势：**列出所有 layer（或按 owner 分组列全）**，`on=true` 的 layer=1001 窗口就是那个「明明在屏幕上的角色窗口」。另外 layer=1001 + on=true 时 `screencapture -l <winNum>` **可正常截图**（976KB 内容丰富）——§10 记录的「onscreen=false 截图失败」是另一状态，别混为一谈。

## 2. DevTools console 读取（无 CDP 时）

DevTools 窗口本身可通过 AX 树读取：`computer_use capture(pid, window_id=devtools)` 后，Console 面板的日志以 `AXStaticText` 呈现（label 即日志文本，如 `[intlify] Not found 'X' key`、`[render-kernel] motion.started`）。点 Console 标签页（AXRadioButton 'Console'）切换面板。Console prompt 输入框是 AXTextArea，可做 JS 注入，但后台 type 不可靠——结果优先用日志文件/其他通道验证。

替代：renderer 是 Vite dev server 时可用 Hermes browser 访问 `http://localhost:5173/`，但 Electron preload API 缺失，页面是降级视图，只能看结构不能当功能验证。

## 3. EPIPE 崩溃框（main process）

**症状**：打开任意窗口弹「A JavaScript error occurred in the main process — Uncaught Exception: Error: write EPIPE」。

**根因链**：日志库（如 `@guiiai/logg`）的 `outputToConsole` 直接 `console[method]()` 无 try/catch → stdout/stderr 是管道且读端已关（launchd/supervisor/后台进程 teardown）→ 每次 console 写抛 EPIPE → 主进程**没注册 uncaughtException** → Electron 默认弹模态崩溃框。

**修复模式**（main 入口顶部，app 初始化前）：

```ts
process.on('uncaughtException', (error) => {
  const message = errorMessageFromUnknown(error)
  const isEpPipe = (error as NodeJS.ErrnoException | undefined)?.code === 'EPIPE' || message.includes('EPIPE')
  if (isEpPipe) {
    // 限流写 stderr（try/catch 包裹，stderr 也可能 EPIPE），吞掉继续跑
    return
  }
  dialog.showErrorBox('An error occurred in the main process', message) // 真实错误保留弹窗
})
process.on('unhandledRejection', /* 同款 EPIPE 吞掉，其余弹窗 */)
```

验证管道状态：`lsof -p <pid> | grep -E "1u|2u"` 显示 PIPE 即 stdout/stderr 是管道。

## 4. macOS 截图（26.x）

- `screencapture -R x,y,w,h` 需要「屏幕录制」权限，无权限报 `could not create image from rect` → 让用户在 系统设置→隐私与安全性→录屏与系统录音 授权。
- `CGWindowListCreateImage` 在 macOS 15+ **已废弃**（编译报 unavailable，需迁移 ScreenCaptureKit）。
- cua-driver 是**单窗口**捕获，无整屏/多显示器；`app='screen'` 返回空窗口。
- 视觉分析无 provider 时：截屏后用 `tools:read-image`（MiMo）看图；多图/长任务用 `terminal(background=true, notify_on_complete=true)` 跑——前台 120s 会超时。

## 5. CDP 运行时调试 renderer（拿到「实际渲染」的 ground truth）

AX 树看不到 canvas 内容、`screencapture` 又要权限时，用 CDP 直接连 renderer 执行 JS + 截图——**这是取证最快路径**。

### 5.1 启动带调试端口

- 项目原生支持（U-NO `debugger.ts`）：`APP_REMOTE_DEBUG=true APP_REMOTE_DEBUG_PORT=9222` 启动 dev。**优先用它**——它会正确设置 `remote-allow-origins`。
- electron-vite 通用：`REMOTE_DEBUGGING_PORT=9222` 环境变量（electron-vite 5 自动转成 `--remote-debugging-port`）。
- ⚠️ `ELECTRON_CLI_ARGS` 在 background shell 启动链里**经常传丢**（npx→pnpm 环境隔离），不要依赖它。
- ⚠️ **kill 清理纪律**（2026-08-07 实测反复被咬）：`process kill` 掉的是 pnpm wrapper（exit 143），**Electron 子进程会残留并继续占 9222/5173** → 下次启动报 `bind() failed: Address already in use (48)` + DevTools 403 看似 origin 问题实为旧实例占端口。换端口/重启前必须三连：`pkill -9 -f "Electron.app/Contents/MacOS/Electron"` + `pkill -9 -f electron-vite` + `lsof -iTCP:<port> -sTCP:LISTEN` 逐个确认 FREE（5173/6121/9222）再启。历史后台进程的 exit 通知里出现 `Address already in use` 大多是这种残留，先清再判。
- 端口起来了：`curl -s http://127.0.0.1:9222/json` 列 target（每个窗口一个 page target + DevTools + worker）。

### 5.2 连 WebSocket：Electron 41+ 的 403 陷阱

Electron 33+ 默认拒绝跨 origin 的 CDP WebSocket 连接（HTTP 403）。**必须带与 `remote-allow-origins` 匹配的 origin**——U-NO 的 debugger.ts 把它设成 `http://localhost:9222`：

```python
import asyncio, json, urllib.request, websockets
pages = json.load(urllib.request.urlopen('http://127.0.0.1:9222/json'))
page = next(p for p in pages if p['url'].endswith('#/'))
async with websockets.connect(page['webSocketDebuggerUrl'],
                              origin='http://localhost:9222', max_size=30_000_000) as ws:
    await ws.send(json.dumps({'id':1,'method':'Runtime.evaluate',
        'params':{'expression':'1+1','returnByValue':True}}))
    # 循环 recv 直到 id 匹配；注意页面会推异步事件（consoleAPICalled 等），要按 id 过滤
```

`devtools://devtools`、`http://localhost:5173` 等其他 origin 全 403。系统 Python 有 `websockets`（hermes venv 15.0.1）；`ws` npm 包在 monorepo 根可能不可见，需绝对路径 require 或放子包里。

### 5.3 ⚠️ 核心陷阱：preserveDrawingBuffer:false 时 readPixels 全是透明

Pixi/Live2D 应用常设 `preserveDrawingBuffer: false`（防帧残留拖影）——**绘制后 buffer 即被回收，`gl.readPixels` 永远返回全 0（透明）**。用它判断「模型没渲染」是**误判**！正确做法：

- **`Page.captureScreenshot`**（CDP，走合成管线，拿真实显示内容）：`Page.enable` → `Page.captureScreenshot {format:'png'}` → base64 存文件。不需要系统录屏权限！截出来文件非空（几十 KB）就说明画面有内容。
- readPixels 只能配合 `preserveDrawingBuffer: true` 的实例用（如独立预览实例）。

### 5.4 WebGL 插桩：区分「渲染循环没跑」vs「画了但不可见」

Hook canvas 的 WebGL 方法计数，3 秒后读统计——一锤定音：

```js
// 挂到目标页：Runtime.evaluate 执行
const gl = canvas.getContext('webgl2') || canvas.getContext('webgl')
const s = window.__stats = { draws:0, binds:0, matrices:0 }
gl.drawElements = (...a) => { s.draws++; return origDraw(...a) }  // 循环在跑？
gl.bindTexture = (...a) => { s.binds++ }                          // 纹理在绑？
gl.uniformMatrix4fv = (...a) => { s.matrices++; /* 采样 NaN/Inf */ }
```

判读：draws 每帧几十次 + bindTexture 大量 + MVP 无 NaN/Inf + `getError()==NO_ERROR` → **渲染循环正常，问题在纹理内容/模型 transform/scale**，不是「没画」。配合 `Page.captureScreenshot` 确认实际画面。

### 5.5 找模型/组件实例（Vue）

组件树遍历：`#app.__vue_app__._instance` 递归 `setupState`/`subTree`（深度 ≤16，去重 seen）；或 `window.__VUE_DEVTOOLS_GLOBAL_HOOK__.apps[0]._instance`。异步组件/keep-alive 会让名字匹配落空——用 setupState 里含 pixi 特征键（`x,y,scale,width,internalModel`）的对象做启发式，别只按组件名找。

**直接调 app 源码模块（无需找组件实例）**：Vite dev 下 CDP 里可用 `await import('/@fs/<绝对路径>.ts')` 直接 import 项目源码模块（命中 Vite 转换缓存），然后调用导出函数——实测直接调 `loadLive2DModelPreview(file)` 复现/验证预览链路，比绕组件树快得多。注意：页面顶层 `import('untitled-pixi-live2d-engine/cubism')` 这类**包名**会解析失败（包名只在 Vite 编译期映射），必须用 `/@fs/` 绝对路径；`/@fs/` import 到的模块实例可能与运行时预打包副本不同（见 §5.9 双副本陷阱），用于「调用函数看行为」没问题，用于「验证引擎内部对象被 patch」会误导。

### 5.6 引擎/运行时版本兼容性调研（渲染类 BUG 的高杠杆步骤）

「渲染循环正常但画面不对/空白」时，**先查渲染引擎与其运行时（Core/SDK）的版本兼容**，再深挖代码——往往上游 issue 已有官方结论：

1. 确认栈：引擎包 + 运行时版本（例：untitled-pixi-live2d-engine 1.3.5 内置 Cubism Framework 5-r.4，配 Cubism Core 6.0.1）
2. 查引擎 README 徽章/描述声明的支持范围（untitled 徽章明确「Cubism 2/3/4/5」→ Core 6 不在内）
3. 搜引擎 GitHub issues 中「适配 <新版本> SDK」类 issue——官方作者常给出已验证解法（issue #11：降级 Core 到 5-r.4 即正常）
4. 找运行时 Core 的真实来源（U-NO 用 `DownloadLive2DSDK` 插件从 SDK zip 提取 `Core/live2dcubismcore.min.js`，electron.vite.config.ts 的 URL 决定版本）——替换方案往往是改一行 URL + 清缓存，而非改引擎
5. 上游未发布的修复别等（v2 适配 5-r.5 遥遥无期）——优先做官方验证过的降级/替换路径
6. **先查上游再深挖**（用户偏好）：遇到「渲染/加载类疑难 + 已确认引擎兼容可疑」时，**先花 10 分钟搜引擎 GitHub issues/PR**（`gh api search/issues?q=repo:<owner>/<repo>+<关键词>`），官方作者常已给出结论或直接删除了不维护的功能（untitled #18 删除 zip loader：「本来就不能用，也不好用」）。上游明确不支持的功能别硬补丁，优先换官方支持的路径（如预览改走 legacy 后端/复用正式加载路径）。

**降级替换落地要点（已实测，U-NO Core 6.0.1→5-r.4）**：
- **改 URL 必须同步改引用**：SDK 目录名含版本号，改 `DownloadLive2DSDK({from: ...5-r.4.zip})` 后，`index.html` 里 `<script src="/assets/js/CubismSdkForWeb-5-r.X/Core/live2dcubismcore.min.js">` 也要同步改——否则 404（Vite 会 SPA-fallback 成 HTML，加载 JS 直接失败）。
- **清缓存范围**：`.cache/assets/js/CubismSdkForWeb-5-r.X`（插件的 cacheDir）+ `src/renderer/public/assets/js/...`（复制目标）+ `src/renderer/.cache/...` + `out/renderer/...` 全部删；dev 运行时从 `public/` serve（out/ 是 build 产物，dev 可不理但删了干净）。插件只会在「目录不存在」时重新下载。
- **验证残留的陷阱**：curl 已删路径返回 `200 text/html` 是 **Vite SPA fallback**（不存在 → 回退 index.html），不是文件残留！判断依据看 `Content-Type`：真 JS 是 `text/javascript` 且内容以 `var/function` 开头，HTML fallback 是 `<!doctype html>`。别被 status 200 骗到。
- 验证链：`pnpm -F <pkg> typecheck`（严格退出码：重定向到文件再 `echo $?`，别走管道）+ curl 新旧两个 URL 的 content-type 对比 + `find -path '*旧版本*'` 残留数应为 0。

### 5.7 配套脚本

`scripts/cdp-electron-probe.py`：CDP 连接 + canvas 像素扫描 + WebGL 插桩 + 截图的最小骨架，改 target URL 匹配即可复用。

### 5.8 Live2D 模型 zip 导入/预览失败：先做静态检查（不碰运行时）

「导入模型失败 / Preview unavailable / 贴图错乱」类问题，**先静态检查 zip，再上运行时**：

1. **别信系统 unzip**：含中文文件名的 zip 用 `unzip` 可能报 `Illegal byte sequence`——这是 unzip 编码问题**误报**，不代表 zip 损坏。用 JSZip + 项目自己的 decode 逻辑验证。
2. **JSZip 解析 + 关键文件定位**：用 `scripts/check-live2d-zip.mjs <zip>` 一条命令完成——列条目数、找 `*.model3.json`、打印其 `FileReferences`（Moc/Textures/Physics/Pose）、逐个验证引用路径在 zip 条目中存在、识别 VTS/大纹理等格式线索。**model3.json 引用了不存在的纹理/物理文件**是导入失败最常见根因（路径大小写、子目录层级、文件名编码）。
3. 识别模型格式线索：`*.vtube.json` = VTube Studio 格式（走 VTS 合并路径）；`*.8192/` 等子目录 = 大纹理图集（8192px 超 WebGL 默认上限风险）；`*.cdi3.json`/`*.cfg` = 第三方工具产物。
4. **怀疑「模型是用更新的 Cubism 版本导出」时**：读 moc3 文件头版本号（`scripts/check-live2d-zip.mjs` 已内置）——offset 4 的 uint32：1=3.0, 2=3.3, 3=4.0, 4=4.2, 5=5.0, 6=5.3。若 version > 6 = Cubism 6 导出，需要 Core 6.x 才支持（untitled 引擎只到 5.x）。**注意**：多数「自定义模型加载失败」其实是运行时 blob:/instanceof 问题（§5.9），moc3 版本只是排除项。
5. 预览链路失败点回顾：`loadLive2DModelPreview` = 解析 zip → setupLive2DModel 加载模型+纹理 → 离屏 canvas 渲染 → crop → dataURL，任一步抛错 catch 吞掉返回 undefined（只看 console.error）。静态检查通过后仍需运行时 CDP 抓 console 才能定位是哪一步。
6. **⚠️ 检查 model3.json 的 Motions/Expressions 引用（「AI 不能做动作」类问题首选检查）**：model3.json 的 `FileReferences.Motions` 为空 + `Expressions` 为空，但目录里 motion3.json/exp3.json 文件都在 → **模型包导出/打包时引用声明丢失**。症状链：`availableMotions` 只有 `["Idle"]`（引擎只靠文件扫描注册到默认组）→ systemPrompt 动作/表情清单空 → **AI 不知道有哪些动作可用 → 只会文字描述、不产生动作 token**。对比法一锤定音：读官方正常模型的 model3.json（hiyori 有 8 组 Motions）vs 问题模型的（0 组）。**与 Cubism 版本无关**（moc3 版本在 Core 支持范围内照样中招）——先查这个再怀疑版本。
   - **VTS 导出模型的隐藏注册表 = `*.vtube.json`（修复已实施，2026-08-07）**：VTS 皮套的 model3.json Motions/Expressions 常为空，动作/表情注册在**同目录 vtube.json**：`FileReferences.IdleAnimation`（待机）、`IdleAnimationWhenTrackingLost`（失焦待机）、`Hotkeys[]`（`Action: ToggleExpression` + `File: *.exp3.json` = 表情；**`Action: TriggerAnimation` + `File: *.motion3.json` = 动作热键**）。检查时**先看 vtube.json 的 Hotkeys Action 分布**（python `Counter` 统计），别只看 model3.json 就下结论。
   - **修复模板**（`mergeVtubeJsonIntoSettingsJson`，把 vtube 注册合并进 model3.json FileReferences）：① IdleAnimation 注入 Motions.Idle（已有 Idle 组则跳过）；② **IdleAnimationWhenTrackingLost 追加进 Motions.Idle**（此前只注入 IdleAnimation，TrackingLost 丢失）；③ Hotkeys 循环里**先处理 `Action==='TriggerAnimation' && file.endsWith('.motion3.json')` → pushMotion(组名=热键 Name)**（此前只处理 exp3 表情，动作热键全丢 → 动作清单只剩 Idle）；④ 提取 `ensureMotions()`/`pushMotion()` 通用函数按 File 去重。实测镌恒执刀 1→4 个动作（待机/打瞌睡/签名/沙漏）+ 33 表情。**测试 helper 默认值陷阱**：共享的 `createVtubeJsonText` helper 改动默认值（如 TrackingLost 默认非空）会破坏既有断言——保持默认向后兼容，新用例显式传 override。
   - **VTS 皮套的使用模式（用户洞察，解释「为什么动作这么少、表情是核心」）**：VTS 真人直播里 vtube.json 的 Hotkeys 就是**主播的快捷键面板**——`ToggleExpression` 热键（按键切表情）是直播表达的主力（镌恒执刀 33 个表情、伊拉利娅 21 个），`TriggerAnimation` 热键（按键播特殊动画，如签名/沙漏）数量很少（2-4 个），IdleAnimation/TrackingLost 是待机循环。**动作少是正常的**——VTS 皮套的设计就是「表情切换为主 + 少量招牌动画 + 面部捕捉」，不是每个动作都多。**U-NO 的 AI 驱动 = 把主播的手换成 AI**：AI 从 systemPrompt 的表情/动作清单里选（`<|ACT {...}|>` token），真人驱动 = 用户按 UI/热键触发同一批 exp3/motion3。修复目标是**让 AI 和真人都能触达同一套注册表**（vtube 合并进 settings 即此目的），不是给模型「加更多动作」。
7. **⚠️ 「模型大小上限」的真身：审计阈值（warning≠阻断）+ BASENAME COLLISION 才是 INVALID 主因**（2026-08-07 实测 391MB zip）：`live2d-validator.ts` 的阈值——**MOC >30MB = warning**（HEAVY RESOURCE，可导入，弹报告窗需确认）、**MOC >100MB = error**（CRITICAL WEIGHT → INVALID 阻断）。**但大 zip 被拒的常见真凶是 BASENAME COLLISION**：zip 内含多个子模型目录（如「镌恒执刀 繁花永恒」+「小角度」）各自有同名 exp3/texture 文件 → 每条 `BASENAME COLLISION` 都是 error → status=INVALID → 导入被拒。诊断顺序：先跑 `validateLive2DZip` 看 errors 列表（CDP `/@fs/` import + fetch zip → `new File([blob], 'x.zip')`），**区分「大小」与「冲突」**——391MB zip 里 MOC 各 31MB（<100MB 不阻断）、92 个纹理合计 390MB，被拒原因是 34 个 exp3 同名冲突。用户问「400MB 咋整」的答案：a) 子模型拆成独立 zip 分别导入（消冲突）——**已实测可行（2026-08-08）**：Python `zipfile` 把子模型目录重打包为独立 zip（`z.write(full, os.path.join('子模型名', rel))` 统一前缀，**保留 vtube.json**），391MB→195.8MB 单包后审计仅 WARNING（无 error）、导入成功、4 动作可用；b) 重命名冲突文件使 basename 唯一；c) 只留一个子模型变体。30MB 警告不是上限，可忽略或确认后继续。
8. **素材使用审计（「是否好多素材没用上」类问题，2026-08-08 实测）**：用户问某皮套素材是否用全时，别猜——**四方对比**：① OPFS 缓存里全部文件（按扩展名分组）② 合并后的 model3.json 的 `FileReferences`（Motions 组名 / Expressions 文件 / Textures）③ vtube.json 的 `Hotkeys[]`（`Action` 分布 + `File` 引用）④ 运行时 store（`useExpressionStore().$state` 的 expressions 数、`availableMotions`）。交集差集一眼看出未使用素材。**结论规律**：VTS 皮套素材「没用上」通常是——a) 冗余纹理（model3 只引 1 张但包里有 2 张 png，可能是 VTS 道具用，见 `vtube.json` 的 `ItemSettings`）；b) 多个子模型包文件混在 OPFS（不同 display-model-* 目录）；真正「未注册」的素材已被 vtube 合并修复覆盖（§5.8-6）。**OPFS 读取坑**：`FileSystemDirectoryHandle.getFileHandle('a/b/c.json')` 不支持 `/` 路径（抛 `Name is not allowed`）——先 `for await (const [name, handle] of dir.entries())` 递归 walk 收集 `{name, handle}` 列表，再 `byName()` 按文件名取文件；`handle.getFile()` 每次调用返回新 File。**「多出来的 PNG 是啥」定论**（2026-08-08 实测）：VTS 包里 model3 未引用的 PNG **多半是 vtube.json `FileReferences.Icon`（模型图标，332KB 级）——不是冗余、别删**；「扫把/魔法书道具」通常**不是独立文件**，是模型内 ArtMesh 部件，由 cdi3.json `Parameters` 暴露控制参数（`Param91 魔法书/Param101 法杖/Param41 帽子/Param95-99 书页`）——驱动见 live2d-runtime-drive「VTS 皮套的道具/贴图」。`items_pinned_to_model.json` 的 `Items: []` 空 = 无 VTS 场景道具。判断「某素材没用上」的完整顺序：先看 cdi3 参数名（道具在模型内）→ 再看 vtube Icon/ItemSettings（贴图用途）→ 最后才定冗余。

### 5.9 ⚠️ XHR 请求 blob: URL 永远挂起（Chromium 限制，渲染/加载类 BUG 高频元凶）

**现象**：引擎用 `XMLHttpRequest` 加载 `blob:` object URL 时**永不完成**——`onload`/`onerror` 均不触发、`xhr.response` 恒为 null。`fetch(blobUrl)` 则完全正常。已实测：`responseType` 为 `json`/`text`/`arraybuffer` 三种全部挂起（Promise.race 5s 超时），`fetch` 正常返回。

**为什么是 blob:**：zip/File 展开后的资源以 `URL.createObjectURL()` 生成 blob: URL 交给引擎（FileLoader.resolveURL 返回 object URL），引擎内部用 XHR 加载 → 挂起 → 外层 Promise 永不 resolve → 预览/加载函数超时 catch 返回 undefined → 症状表现为「Preview unavailable」「Network error」（实为超时）或功能静默失败。

**修复模板**（patch 全局 XHR，blob: 走 fetch 桥接，其余保持原生；幂等）：

```ts
// 在引擎加载前执行一次（幂等标志）
if (typeof XMLHttpRequest !== 'undefined' && !(XMLHttpRequest.prototype as any).__blobPatched) {
  const origOpen = XMLHttpRequest.prototype.open
  XMLHttpRequest.prototype.open = function (this: XMLHttpRequest, method: string, url: string | URL, ...rest: unknown[]) {
    const urlStr = typeof url === 'string' ? url : url.toString()
    if (method.toUpperCase() === 'GET' && urlStr.startsWith('blob:')) {
      const xhr = this
      // 关键①：必须先调 origOpen 保持状态机（OPENED），否则引擎后续 send() 抛
      // InvalidStateError: "The object's state must be OPENED"
      origOpen.apply(this, [method, url, ...rest] as never)
      xhr.send = () => { /* fetch-driven; no-op */ }  // 关键②：send 变 no-op
      let cancelled = false
      let responseType = ''
      Object.defineProperty(xhr, 'responseType', {  // 捕获引擎设的 responseType
        set(v: string) { responseType = v }, get() { return responseType }, configurable: true,
      })
      void (async () => {
        try {
          const res = await fetch(urlStr)
          if (cancelled) return
          if (!res.ok) { Object.defineProperty(xhr, 'status', { value: res.status, configurable: true, writable: true }); xhr.dispatchEvent(new ProgressEvent('error')); return }
          let data: unknown
          if (responseType === 'json') data = await res.json()
          else if (responseType === 'arraybuffer') data = await res.arrayBuffer()
          else data = await res.text()
          if (cancelled) return
          // 只读属性必须 defineProperty 赋值（TS 报 read-only，运行时允许）
          Object.defineProperty(xhr, 'response', { value: data, configurable: true, writable: true })
          Object.defineProperty(xhr, 'responseText', { value: typeof data === 'string' ? data : '', configurable: true, writable: true })
          Object.defineProperty(xhr, 'status', { value: res.status, configurable: true, writable: true })
          Object.defineProperty(xhr, 'statusText', { value: res.statusText, configurable: true, writable: true })
          Object.defineProperty(xhr, 'readyState', { value: 4, configurable: true, writable: true })
          xhr.dispatchEvent(new ProgressEvent('load'))
          xhr.dispatchEvent(new ProgressEvent('loadend'))
        } catch { if (!cancelled) xhr.dispatchEvent(new ProgressEvent('error')) }
      })()
      xhr.abort = () => { cancelled = true }
      return
    }
    return origOpen.apply(this, [method, url, ...rest] as never)
  }
  ;(XMLHttpRequest.prototype as any).__blobPatched = true
}
```

**要点**：
- 为什么 patch `XMLHttpRequest.prototype.open` 而不是引擎导出的 `XHRLoader.createXHR`：引擎在 Vite optimizeDeps 预打包后存在**双模块实例**（预打包副本 vs 源码副本），patch 引擎导出对象可能改错实例；patch 全局 XHR 原型则无论哪个实例都生效。
- **Vite 双副本 instanceof 陷阱**：`optimizeDeps.include` 里的引擎包（untitled-pixi-live2d-engine 等）被预打包；若应用代码自己解析的 settings 对象来自源码副本，引擎内部 `settings instanceof ModelSettings` 会 **false** → 引擎 fallback 到把 settings 当字符串 URL 处理（XHR 相对路径，页面上下文解析失败）。症状：`XHR GET <相对路径.model3.json>`。修复方向是让引擎走 `File[]` 路径（传 `{url, id}` 对象给 setupLive2DModel 触发 OPFS 中间件展开），而不是手动传解析好的 settings。
- vitest node 环境无 `XMLHttpRequest`——patch 前必须 `typeof XMLHttpRequest !== 'undefined'` 守卫，否则测试崩。
- eslint `style/max-statements-per-line`：`xhr.abort = () => { cancelled = true }` 单行两语句会报错，箭头函数体拆多行。

**验证链**：CDP `Runtime.evaluate` 里先 `XMLHttpRequest.prototype.open.toString()` 确认 `patched:true` → 强制 `Page.reload` 让 patch 全新执行（HMR 可能不重载模块缓存）→ 再调目标函数看错误从「Network error」→「InvalidStateError」→ 成功（错误类型变化 = 补丁在推进，逐层修）。

### 5.9.1 ⚠️ 实例级 patch（引擎类静态方法）不生效：下沉到数据层，别改引擎方法（2026-08-07 实测）

**现象**：同一个 patch 函数里，**全局 prototype patch 生效**（`XMLHttpRequest.prototype.open` 改写后 `toString()` 含 `blob:` 标记，跨所有模块实例有效），但**同函数内对引擎类静态方法的 patch 不生效**——如 `FileLoader.createSettings = async (files) => {...}` 改写后，运行时检查 `FileLoader.createSettings.toString()` 仍是引擎原版（不含 vtube/sanitize 特征串）。**手动重调 patch 函数也不生效**（CDP `/@fs/` import 的 loader 源码副本内部 `import('untitled-pixi-live2d-engine/cubism')` 解析到的实例 ≠ 应用运行时用的预打包实例；`/@fs/` 源码副本与 `.vite/deps/` 预打包副本 `sameInstance === false`）。

**判定**（别被「patch 函数执行过」误导）：XHR 全局标记（如 `__blobPatched:true`）只证明函数跑到 XHR 段；**类静态方法是否 patch 成功必须直接查**：CDP 里 `FileLoader.createSettings.toString().includes('特征串')` 对**预打包副本**（`/@fs/<app>/node_modules/.vite/deps/<pkg>_*.js`）检查——这是应用真正用的实例。`/@fs/` 源码路径的检查结果不可信（不是运行时实例）。

**修复模式：把变换下沉到数据/中间件层，不依赖引擎实例**（U-NO 实测模板，opfs-loader.ts）：
- 在 `OPFSCache.checkMiddleware` 的 **cache-miss 分支**（zip 展开成 File[] 后）：找到 `model3.json` + `*.vtube.json` → `mergeVtubeJsonIntoSettingsJson` 合并 → 用 `new File([JSON.stringify(merged)], name)` + `Object.defineProperty(file, 'webkitRelativePath', {value: path})` **替换 File[] 里的 settings 文件** → 引擎 `createSettings` 读到合并文本。
- **cache-hit 也必须合并**（否则二次加载读旧缓存）：把同样合并写进 `OPFSCache.save`（持久化前替换 model3.json 内容）。
- **改完 bump `live2DOpfsCacheVersion`**（v3→v4→v5）：旧缓存 meta.version 不匹配自动删重建。**同步更新测试里 mock 的 version 数字**（opfs-loader.test.ts 里 `version: 3` → 新版本号），否则「does not restore ignored archive metadata」类测试误报。
- **⚠️ 测试环境陷阱**：数据层文件**顶层 import 引擎相关模块**会把 pixi-live2d-display 带进 vitest Node 环境 → `window is not defined` 崩。合并函数用**函数体内动态 `await import('./live2d-zip-loader')`**，别顶层 import。
- **数据层验证链**（一锤定音）：reload 后 console 出现 `[OPFS] vtube.json merged into ...` → CDP 递归读 OPFS 缓存里 model3.json 的 `FileReferences.Expressions` 数量（21/33）→ **手动跑引擎 createSettings 验证**：`/@fs/` import 预打包副本 → 从 OPFS 递归读 File[]（补 webkitRelativePath）→ `await FileLoader.createSettings(files)` → `settings.expressions.length === 33` = 数据层全通。
- ⚠️ 数据层全通 ≠ 功能生效：若下游 store（如 expression-store）仍空，问题在**组件/控制器调用端**（initExpressionController 未触发/未注册），与数据层无关——别回头改数据层，去查调用链（Model.vue 的 `watch(modelSrcRef)` → `loadModel` finally → `initExpressionController`）。
- **⚠️ 功能开关门控控制器（2026-08-08 实测「数据层全通但 store 空」的最终根因）**：Model.vue 里 `initExpressionController` 被 `if (live2dExpressionEnabled.value)` 包着（禁用内置 Cubism expressionManager 的配套逻辑同门控），而该设置**默认 `false`**（`live2d.ts` 的 `useLocalStorageManualReset('settings/live2d/expression-enabled', false)`）→ 表达式系统默认关闭 → `registerExpressions` 从未执行 → store 空。**判定**：数据层验证全绿（引擎 createSettings 手动跑出 33 个 expressions）+ store 空 → 查 `localStorage.getItem('settings/live2d/expression-enabled')` 是否 `false`；改默认值对**已存裸值用户不生效**，用 `useVersionedLocalStorageManualReset(key, true, {defaultVersion:'2.0.0'})` 版本化迁移（旧裸值无 version 字段自动重置为新默认）。验证链：reload 后 localStorage 变为 `{"version":"2.0.0","data":true}` + store `modelId` 非空 + `groupCount` 21/33 + `toggle('expression1')` 返回 `{success:true, state:[{name:'Param71', value:1}]}`（**可用表情名是 `ParamNN` 参数 ID**，数量 = exp3 文件数；视觉确认：触发后角色惊讶瞪眼张嘴）。
- **⚠️ 表情自动复位语义（2026-08-08 用户需求「表情触发后 3S 回到正常」）**：`expression-store.ts` 的 `applyValue` 原本只有 `duration > 0` 才调度 setTimeout 复位，**调用方不传 duration = 永久保持**（AI 工具 `expression_set` 的 duration 是 optional，工具描述甚至写 "Omit for permanent change"）→ 表情一直挂着不回到默认脸。修复：`DEFAULT_AUTO_RESET_SECONDS = 3`，`duration === undefined` 时默认 3 秒复位，显式传 0/负数 = 永久保持（持续脸红等场景）。语义对齐 VTS 真人直播「热键切表情 → 回默认脸」——表情是瞬时表达，动作才是刻意行为。验证链：CDP 触发 `store.set('expression1', 1)`（不传 duration）→ t+1s `store.get()` 该参数 value=1 → t+4.5s `get()` stillActive=0（已复位）+ 视觉对比截图（t0 半闭眼倦怠 vs t4.5 睁眼自然默认脸）确认回默认。

## 5.10 Live2D 表情/动作测试驱动（CDP + 视觉确认，用户逐个验收）

用户「你来调用表情/动作，我一个一个确认」场景的完整工作流（2026-08-08 实测，U-NO + 伊拉利娅/镌恒执刀）。

**先查模型有什么可测**（避免对纯表情模型找动作）：
```js
// 当前模型 + 可用动作（localStorage 由模型加载时写入）
localStorage.getItem('settings/stage/model')
JSON.parse(localStorage.getItem('settings/live2d/available-motions'))  // [{motionName, fileName}]
// 可用表情数（可用名是 ParamNN 参数 ID，数量 = exp3 文件数）
const store = (await import('/@fs/<abs>/packages/stage-ui-live2d/src/stores/expression-store.ts')).useExpressionStore()
store.set('__probe__', 1).available  // 全部可用名数组
```
- **纯表情型皮套**（伊拉利娅：21 个 exp3 表情、仅 1 个动作 Scene1 Idle）——动作没什么可测，测表情为主；**表情+动作型**（镌恒执刀：33 表情 + 4 动作 待机/打瞌睡/签名/沙漏）两者都测。这是 VTS 皮套的正常设计（见 §5.8-6 末），不是缺陷。

**⚠️ 动作触发 API 别搞错**（实测踩坑）：
- ❌ `store.currentMotion.value = { group: '签名动画', index: 0 }` **只是写状态，不触发播放**（render-kernel 无 `motion.started` 日志）。
- ✅ 正确：`useLive2dParams().emitMotionEvent({ group: '签名动画', index: 0 })` → render-kernel 日志出现 `[info] [render-kernel] motion.started 签名动画` = 播放确认。

**表情触发 API**：`store.set(name, 1)`（组名或 ParamNN 均可）、`store.toggle(name)`、`store.resetAll()`（测下一个前清状态）。**2026-08-08 起不传 duration 默认 3 秒自动复位**（见 §5.9.1 末），测试时触发后 2s 内截图即可拍到表情生效。

**验证链（每项）**：CDP 触发 → `Page.captureScreenshot` 触发前/后各一张（触发后等 1.5-2s）→ read-image（MiMo）视觉对比（眼睛/眉毛/嘴巴/整体情绪变化）→ 把两张图 `MEDIA:` 发给用户人工确认 → 下一个。表情名称读 `store.set('__probe__', 1).available` 迭代（Param63/Param67/Param71/Param102...）。

**模型切换**（测另一模型的动作时）：`/@fs/` import `useSettingsStageModel()` → `store.stageModelSelected = '<display-model-id>'` → `await store.updateStageModel()` → 等 8-10s → 再查 available-motions/expression-store（模型加载完成后写入）。**ID 从 `useDisplayModelsStore().displayModels` 取**（`display-model-*` 前缀，勿写死）；纯本地 zip 大模型切换加载要 10s+。

**⚠️ 表情/动作参数改了但画面不变 → 先查 Pixi Ticker 是否在跑**（2026-08-08 实测，U-NO 表情测试）：store 值正确（`store.get()` 显示 ParamNN=1）、render-kernel 无 motion.started、但**用户看真实窗口说「没变化」**——先查渲染循环，别先怀疑表情链路：

```js
// CDP 检测 Pixi v8 ticker 是否在跑（false = 渲染冻结，画面是最后帧）
const pixi = await import('/@fs/<app>/node_modules/.vite/deps/@pixi_ticker.js')
const shared = pixi.Ticker.shared
shared.started   // false = 冻结
pixi.Ticker.system.started  // 双查
// 帧计数验证（3 秒）：
let frames = 0; const l = () => frames++
shared.add(l); await new Promise(r => setTimeout(r, 3000)); shared.remove(l)
frames / 3  // ≈60 = 满速，≈0 = 冻结
```

**临时恢复验证**（确认「冻结→恢复渲染」因果关系）：`shared.start(); pixi.Ticker.system?.start()` → 帧计数恢复 60 FPS → 再触发目标动作/表情看画面变化。**已实测有效**（ticker 重启后 3s 180 帧满速）。

**⚠️ 已确认的根因候选（本会话未定案，别当结论写死）**：
- `Canvas.vue` 的 `installRenderGuard`：guardedRender 里 `app.render()` 抛错 → `app.ticker.stop()`，**无自动恢复机制**（console 未捕获到 render error，但早期可能发生过一次即永久冻结）。
- `Model.vue` `watch(paused)` → `paused ? pixiApp.stop() : start()`；paused 链只该在 minimized 时暂停（`shouldPauseStageFromLifecycle` 返回 `state.minimized`），实测 lifecycle `minimized:false, visible:true` 时 ticker 仍停 → paused 不是主因，倾向 render-guard 停表。
- 排查下一步：hook `app.render`/`guardedRender` 计数 + 捕获首次抛错堆栈。
- **macOS 透明 panel 主窗口「启动后从未 show」（ready-to-show 不触发，2026-08-08 实测）**：`show:false + type:'panel' + 透明` 组合下 `ready-to-show` 可能**永不触发** → 窗口对象在 Electron 进程里存在但从未显示（CGWindowList 看不到 / on=false，`screencapture -l` 失败或纯黑）。**与「用户点关闭按钮 hide」是不同场景——这是启动即不显示**。诊断交叉验证法：AppleScript `System Events` 列 Electron 进程窗口能看到 "U-NO"（窗口对象存在）但 CGWindowList 看不见（没 show）；`document.visibilityState` 在 renderer 里可能是 `visible`（欺骗性强）。伴随日志：`GPU process exited unexpectedly: exit_code=15`（可能相关，未定案）。**候选修复（已 typecheck/eslint 通过，运行时待验证）**：`ready-to-show` 之外加兜底——`window.webContents.once('dom-ready')` / `once('did-finish-load')` 各挂延时 `window.show()`（~800ms），`await load()` 返回后再挂 1200ms 兜底（`!window.isDestroyed() && !window.isVisible()` 守卫）。⚠️ **electron-vite 对 main 进程改动不自动热重启**（HMR 只热更 renderer）——改 main 后必须手动 kill 重启，否则新代码不生效。⚠️ **复盘纠偏（本会话尾声）**：「主窗口看不到」很可能是 **§1 的 layer==0 过滤陷阱**（窗口其实在 layer=1001 on=true 正常显示），**先按 §1 列全 layer 再下「从未 show」结论**——本会话正是先误判「窗口不存在」绕了 show 兜底+重启一大圈，最后发现窗口一直在。show 兜底修复保留（无副作用），但「启动即不显示」的判定必须先排除 layer 过滤问题。
- **⚠️ `Ticker.shared` 检查可能误导（Pixi8 Application 用独立 ticker，2026-08-08 实测）**：Pixi8 `Application` 默认 `sharedTicker:false` → app 用**自己的 ticker**，`Ticker.shared.started=false` 且 `listeners=0` 可能只是 shared 空转，不代表 app 渲染循环死了；反之 `shared.start()` 后 60fps 满速（3s 180 帧）也**不能**反推 app 渲染在跑。真正确认渲染循环：找到 app 实例的 `app.ticker`（组件树深挖 setupState 的 pixiApp，可能因 Canvas 组件未暴露而找不到）；找不到时以**用户实际窗口画面是否变化**（两秒全屏截图对比静止？）为 ground truth，别只看 shared ticker 数字。

**⚠️ 教训：CDP 截图分析的帧间差异可能是自然动画，别反驳用户**（2026-08-08 实测）：表情测试时 CDP `Page.captureScreenshot` 两张图被视觉模型读出「眼睛/嘴巴差异」（眨眼/呼吸自然帧差），但**用户看真实窗口说「没变化」**——真相是渲染冻结，截图差异是冻结前不同帧的静态对比。**用户对真实窗口的判断优先**：用户说没变化时，先查 Ticker/渲染循环是否活着，别用截图分析结论去质疑用户。

## 6. 验证纪律：项目脚本 + stash 基线

- 裸跑 `vue-tsc --noEmit -p <猜测的配置>.json` 会灌入大量无关 moduleResolution 错误——**用项目自己的脚本**：`pnpm -F <pkg> typecheck`。
- 证明「零新增错误」：`git stash push <仅自己的文件>` → 跑检查 → `git stash pop` → 对比错误数。stash 时只 push 自己改的文件，别把他人未提交工作卷进去。

## 8. MaxListenersExceededWarning：事件监听器泄漏（main process）

**症状**：主进程 stderr/stdout 出现 `MaxListenersExceededWarning: Possible EventEmitter memory leak detected. 11 move listeners added to [BrowserWindow]`（数字 >10 且随操作递增）。

**根因模式**：一个「可重复触发」的 handler（如打开 onboarding 窗口、重建 tray 菜单）在**每次调用时都 `mainWindow.on('move'/'resize', listener)`**，而清理只挂在「窗口关闭」回调里（`onClosed`）。窗口开着时再次 toggle 打开 → 新监听器叠加、旧的永不移除 → 累积到 10+。**排查方法**：grep `\.on\('(move|resize)'` 找到所有挂载点，看每个挂载是否在可重复执行的函数体内、是否有成对的 removeListener。

**修复模板**（detach-before-add 模式，幂等且不破坏 onClosed 清理）：

```ts
let detachMainMoveListener: (() => void) | undefined

defineInvokeHandler(ctx, openOnboarding, async () => {
  // 每次进入先移除上一轮遗留的监听器（窗口未关闭时 onClosed 清理不会触发）
  detachMainMoveListener?.()
  detachMainMoveListener = undefined

  const moveListener = () => { /* ... */ }
  params.mainWindow.on('move', moveListener)
  params.mainWindow.on('resize', moveListener)
  detachMainMoveListener = () => {
    params.mainWindow.removeListener('move', moveListener)
    params.mainWindow.removeListener('resize', moveListener)
  }

  cleanupOnClosed = windowManager.onClosed(() => {
    detachMainMoveListener?.()          // 双保险：关闭路径也清理
    detachMainMoveListener = undefined
    // ...原有 cleanup
  })
})
```

**要点**：
- 只保存「当前轮」的 detach 函数，进 handler 先调用——比收集历史 listener 数组更简单且不会误删。
- 若函数体内还有 `setTimeout` 引用，也要存句柄并在 cleanup 里 clearTimeout（避免 timer 悬空改状态）。
- **验证**：`grep -c MaxListenersExceededWarning <log>` 基线为 0 → 触发 N 次开关循环（真实 UI 点击或 CDP 调 Vue setupState 里的打开函数）→ 再 grep 仍为 0。修复前同样循环会累积到 11+。

## 9. 触发 renderer 内部函数（Eventa/自定义 IPC 桥）

**陷阱**：自定义 IPC 桥（如 @moeru/eventa）的 invoke 通道**不是** `window.electron.ipcRenderer.invoke('eventa:invoke:...')` 直接可达——直接调报 `Error invoking remote method ... No handler`（eventa renderer adapter 实际用 `ipcRenderer.send` + 独立响应通道）。**别浪费时间逆向 eventa 的通道协议**。

**可靠做法**：直接调 Vue 组件实例 setupState 里暴露的函数。CDP `Runtime.evaluate` 深扫组件树：

```js
// 找 setupState 里的目标函数（如 openOnboarding）
const app = document.querySelector('#app').__vue_app__
const seen = new Set(); let fn = null
const walk = (inst, d) => {
  if (!inst || seen.has(inst) || fn || d > 16) return
  seen.add(inst)
  const ss = inst.setupState || {}
  if (typeof ss.openOnboarding === 'function') { fn = ss.openOnboarding; return }
  if (inst.subTree) walk(inst.subTree.component, d + 1)
}
walk(app._instance, 0)
await fn()   // 返回 promise，awaitPromise:true 可等结果
```

触发 UI 动作（开窗口、切模型、跑导入）用这个方式最稳；关闭窗口则用 `computer_use` 像素点击真实关闭按钮（AXPress 对自定义标题栏可能无效，用坐标点击兜底）。

**⚠️ 切模型/改设置：用 store 的 computed setter，别直写 localStorage**（2026-08-07 实测）：`useLocalStorageManualReset` 类 ref 有**内存态优先**——`localStorage.setItem('settings/stage/model', ...)` 后 `Page.reload`，store 初始化时会把选中值**重置回内存态/默认**（localStorage 被覆盖），表现为「设置了但 reload 后还是旧模型」。正确姿势：`/@fs/` import 对应 store → `store.stageModelSelected = '<id>'`（computed setter 同步写 localStorage + 内存态）→ `await store.updateStageModel()`（真正触发加载）→ 等 8s → 验证 `localStorage.getItem('settings/live2d/available-motions')` 是否更新（模型加载完成后写入）。store 方法清单看 `Object.keys(store).filter(k => typeof store[k] === 'function')`，但注意 pinia 的 action 可能签名无参（从内部 state 读，如 `updateStageModel()`），先读 store 源码确认参数。

## 10. 后台监听运行中 app：正式模式（无 CDP）的 BUG 监听工作流

用户「我在里面操作、你监听找 BUG」场景的**首选方案**——不需要 CDP/调试端口，**tail -f 日志文件即可同时捕获主进程 + renderer 的 console**（Electron 会把 renderer console 转发进主进程日志文件，实测日志里出现 `[CSM] Live2D Cubism Core version`、`[render-kernel] motion.started` 等 renderer 消息）。

```bash
# 监听脚本骨架（带时间戳逐行输出）
LOG=$(ls -t "$HOME/Library/Application Support/<AppName>/Logs/"*.log | head -1)
tail -f -n 0 "$LOG" | while IFS= read -r line; do
  echo "$(date '+%H:%M:%S') $line"
done
```

- 用 `terminal(background=true, watch_patterns=[...])` 挂**高价值错误模式**自动通知：`["Uncaught", "EPIPE", "Unhandled", "TypeError", "ReferenceError", "Cannot read", "is not a function", "ERROR:"]`。不要挂 `error`/`warn` 裸词（[warn] artistry-bridge 等已知噪音会刷屏触发限频自动禁用）。
- **已知噪音清单**（监听时先排除，避免误报）：`[warn] artistry-bridge`（#3 已记录，syncConfig 每次触发）、`[log] websocket connected/closed`（心跳）、vite HMR、`[info] chat-sync WS skipped: anonymous user`。
- 配合窗口枚举（§1）理解用户操作轨迹：窗口列表变化（onboarding 关了、Chat 开了）≈ 用户动作时间线，据此把日志时间点对上操作。
- 监听期间新发现的 BUG 记入 references 的「未决问题」节，附窗口/日志证据。
- 主窗口 `onscreen=false` 时 `screencapture -l <winNum>` 会失败或截出纯黑——先查 onscreen 再截图，别把离屏误判成渲染 BUG。
- ⚠️ **`onscreen=false` 可能是误报**：`setAlwaysOnTop(true,'screen-saver')` + `setVisibleOnAllWorkspaces(true)` 的窗口（U-NO 宠物窗正是如此），CGWindowList 的 `kCGWindowIsOnscreen` 可能恒 false，但窗口**实际可见**。2026-08-07 实测：onscreen=false + `screencapture -l` 失败/纯黑 + AXRaise 无效，但**全屏 `screencapture -x` + 视觉分析确认角色窗口就在屏幕上**。判据：renderer 进程活着 + DOM 有内容（CDP `document.body.children.length`）+ 全屏截图能看到 → 窗口没问题，是 CGWindowList 状态异常。也别把「点关闭按钮=hide 不退出」（`close` 事件 preventDefault + `window.hide()`，tray Show 才恢复）误判成窗口丢失。
- **离屏窗口的渲染验证用 CDP `Page.captureScreenshot`**（onscreen=false 时 `screencapture -l` 失败/纯黑）：CDP 截图走合成管线，**不依赖窗口是否在屏上**，能直接证明「角色在渲染」——2026-08-07 实测主窗口 onscreen=false 时 CDP 截出 271KB 完整角色画面（伊拉利娅）。视觉分析确认「无 loading 转圈 + 角色完整 + UI 按钮齐全」即渲染正常，别再纠结窗口为何不显示。

### ⚠️ 用户打开了「正式构建版」≠ 你调试的 dev 实例（Loading/行为差异排查）

**症状**：用户说「重新打开 U-NO 后一直在 loading / 行为和你测的不一样」，但你 dev 实例一切正常。**先分清用户打开的是哪个产物**：

1. **看主进程日志的模块路径**：`grep -a "app.asar" <log>` 或日志里 `file:///.../Contents/Resources/app.asar/out/main/index.js` 的堆栈 = **正式构建版**（`~/Applications/U-NO.app`），不是 dev 模式（dev 是 `out/main/index.js` 本地路径 + Vite `localhost:5173`）。
2. **对比构建时间 vs 修复时间**：`ls -la ~/Applications/U-NO.app/Contents/Resources/app.asar` 的 mtime。**正式版只包含构建时刻的已提交/工作区代码——之后做的任何修复（XHR blob 桥、VTS 补全等）都不在其中** → 旧构建会复现「已修复」的症状（如加载导入模型转圈 = 缺 blob 桥）。2026-08-07 实测：app.asar mtime 16:30，XHR blob 桥 22:15 才完成 → 用户打开旧正式版加载伊拉利娅时 XHR blob: 挂起转圈，而 dev 模式（CDP 确认 Core 5.1 + OPFS cache hit + WebGL 正常 + 角色渲染）一切正常。
3. **处理**：先向用户确认/说明这是旧构建，问是否用 dev 模式（推荐，含全部修复）或重新 `pnpm build`。**别在旧构建上花时间调 BUG**——它反映的是历史代码状态。build 产物与 dev 共用同一 user-data-dir（`~/Library/Application Support/U-NO`），模型/IndexedDB 数据互通，不会丢。


## 11. ⚠️ 多窗口 Electron：AI 工具/共享 store 的跨窗口隔离陷阱

**症状**：AI 助手（跑在 Chat/辅助窗口）调用「驱动主窗口状态」的工具（表情设置、动画播放、模型切换）时**永远失败**——即使主窗口模型明明加载正常。典型 AI 回复：「我好像没有模型加载呢，所以只能用文字描述」。工具条目显示绿色成功（调用没崩），但返回内容是可读错误（如 `No Live2D model is currently loaded`）。

**根因（架构级）**：Electron 每个 BrowserWindow 是**独立 renderer 进程 → 独立 pinia store**。若 `App.vue`（所有窗口共享的根组件）无条件注册了 AI 工具（如 `live2dToolsStore.refresh()`），则**每个窗口都注册了同一批工具，但工具 execute 里 `useExpressionStore()` 读的是当前窗口自己的 store**。模型状态（modelId/expressions）只在主窗口的 store 里，Chat 窗口的 store 恒为空 → 工具永远报「无模型」。**全仓 grep 无 broadcast/IPC/webContents.send 跨窗口同步 = 实锤**。

**排查路径（快）**：
1. AI 说没模型 → 看工具源码的 `ensureModelLoaded()` 检查什么（常是 `store.modelId` 空）
2. 确认 Chat/辅助窗口是独立 `new BrowserWindow`（`windows/chat/index.ts`）+ 独立路由（`/chat`）
3. **grep 跨窗口同步机制**：`broadcast|BroadcastChannel|webContents.send|sendToAll|storage`（localStorage 同源会共享，注意区分）——零结果即隔离实锤
4. 判断「不是配置问题」：AI 能回复、工具调用返回绿色成功 = 服务配置正常；失败在状态可见性，不在链路

**⚠️ 隔离有两层，都要查**（2026-08-07 实测，Chat 窗口 AI 无法驱动 Live2D）：
- **工具执行层**：工具 execute 里 `useXxxStore()` 读的是当前窗口自己的 store → 永远报「无模型」。
- **提示词组装层**：systemPrompt 若含「从模型运行时读取的动态清单」（如 ACT-strict 的动作组/表情列表，`airi-card.ts` 的 `formatMotionInjection`/`formatExpressionInjection`），Chat 窗口组装的清单**恒空** → 模型**不知道有哪些动作可用** → 只能文字描述、不产生动作 token。用户会问「是不是角色卡描述写错」——不是，是清单注入层被隔离。**修跨窗口问题必须两层一起处理**（同步状态 或 让辅助窗口复用主窗口的 orchestrator/store）。

**「AI 不能做动作」的完整诊断链**（2026-08-07 实测，含用户「是不是 Act 指令/角色卡写错」的假设排查）：
1. **先理解动作机制**：U-NO 类应用教模型输出 `<|ACT {"emotion":...,"motion":[...]}|>` 流式 token（ACT-strict 模板，i18n `base.prompt.*`），提示词里注入三个动态清单：`{emotions}`（官方九组硬编码，恒有）、`{motions}`（`useLive2dMotionSource()`：ModelProfile 优先，否则 `live2d.availableMotions`）、`{expressions}`（expression-store 的 expressionGroups）。**动作/表情清单是否为空 = 模型能否产生动作 token 的决定因素**。
2. **dump 实际 systemPrompt 验证清单**（CDP + `/@fs/` import，比猜快）：
   ```js
   const mod = await import('/@fs/<abs>/packages/stage-ui/src/stores/modules/airi-card.ts')
   const store = mod.useAiriCardStore()
   store.systemPrompt  // 看 "available motions"/"available expressions" 段有没有实际条目
   ```
   主窗口清单里**只有 DELAY、没有动作组** → 说明 `motionGroups` 空，不只是跨窗口问题。
3. **查 availableMotions 持久化**：`useLive2dParams().availableMotions` 存在 **localStorage `settings/live2d/available-motions`**（模型加载时写入）。CDP 读：
   ```js
   JSON.parse(localStorage.getItem('settings/live2d/available-motions'))
   ```
   **只有 `["Idle"]` = 模型加载时 motion 解析只识别了默认组**。**先静态检查根因再上运行时**：读该模型 model3.json 的 `FileReferences.Motions`/`Expressions`——为空但目录里文件都在 = **模型包引用声明缺失**（最常见，连主窗口清单都空，与跨窗口隔离无关，见 §5.8 第 6 点）；若引用非空但运行时仍只有 Idle = 引擎解析问题。同时看 `settings/stage/model` 确认当前是 hiyori 预设还是自定义模型。
4. 区分三层根因：① 工具执行层读空 store（跨窗口隔离，§11 主坑）；② 提示词组装层清单空（隔离或模型未解析）；③ `availableMotions` 本身只有 Idle（**先查 model3.json Motions 引用缺失（§5.8-6），排除后再疑引擎解析**）。①② 修同步/转发，③ 修模型包引用或引擎扫描补全（或换预设验证）。


**修复方向（二选一，未实施留档）**：
- **A. 跨窗口同步模型状态**：主窗口模型加载/卸载时经 IPC/broadcast 把 modelId+expressions 推到 Chat 窗口 → 工具能读到
- **B. 工具执行转发**：Chat 窗口工具经 IPC 委托主窗口执行（主窗口有真实模型 + 能直接驱动渲染）——更彻底，因为 expression_set 最终要作用在主窗口的模型上

**设计红线**：注册工具前判断窗口角色（`initialWindowRoutePath === '/chat'` 之类），或让工具只读「本窗口存在」的状态、把跨窗口操作走 IPC 转发——别让共享根组件无脑注册依赖主窗口状态的工具。

## 12. 监听模式下的新 BUG 取证闭环

用户「你监听、我操作」模式下发现新 BUG 后的标准取证链（配合 §10 监听工作流）：
1. 监听日志匹配到现象 → **窗口枚举（§1）对时间线**：窗口列表变化（onboarding 关、Chat 开）≈ 用户操作，据此定位触发操作
2. 截屏取证：`screencapture -l <winNum>`（先查 `onscreen`，离屏窗口截出纯黑/失败——见 §10 末尾）
3. 视觉分析（read-image/MiMo）念出**报错文字原文**（AI 回复、工具返回、红字）
4. 区分「链路坏了」vs「状态不可见」：工具条目绿色成功 = 调用链没坏 → 问题在**工具读的状态**（→ §11 跨窗口隔离）或**消息组装层**（→ #20 reasoning 泄漏）
5. 结论进 references 的未决问题节，附窗口/日志/截图证据；修复后回填到「已修 BUG」节

## 7. i18n provider 本地化模式（intlify 刷屏）

**症状**：`[intlify] Not found '<某字符串>' key in 'zh'/'en' locale messages` 刷屏。

**根因**：provider 的 `nameLocalize: () => '硬编码字符串'` 绕过了 i18n——字符串被当键查。正确模式（与同目录其他 provider 一致）：

```ts
nameLocalize: ({ t }) => t('settings.pages.providers.provider.<id>.title'),
descriptionLocalize: ({ t }) => t('settings.pages.providers.provider.<id>.description'),
```

且**所有** locale 文件都要有对应键，否则项目 `check:i18n` 脚本直接 FAIL（要求键全语言一致）。修复后跑 `check:i18n` + provider 目录单测 + 两个包的 typecheck 收口。
