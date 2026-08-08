# U-NO / AIRI 项目调试速查（2026-08-07 实测）

## 项目身份

- 位置：`~/Desktop/U-NO`，monorepo root 包名 `@uno/root` v0.11.3
- 本质：moeru-ai/airi 0.11.3 的剪枝增强分支（README 自述「基于 moeru-ai/airi 0.11.3 + 4 个本地提交」），单机优先虚拟角色 AI Agent：Live2D 皮套 + 本地 LLM/TTS + 角色卡驱动行为
- 栈：Electron 41.2.1 + Vue 3 + Vite + TypeScript + Pinia + Eventa (IPC/RPC) + UnoCSS；Live2D Cubism Core 6.0.1 + untitled-pixi-live2d-engine 1.3.5；渲染双后端 `untitled-backend.ts` / `legacy-backend.ts`
- pnpm 10.33.0（README 要求 `npx -y pnpm@10.33.0` 前缀，或 mise/corepack）
- 工作区常有大量未提交改动（130 文件/4000+ 行级别）——验证改动时用 stash 只压自己的文件

## 启动

- `npx -y pnpm@10.33.0 -F @uno/stage-tamagotchi dev`（或双击仓库根 `启动U-NO.command`）
- **CDP 调试启动**：`APP_REMOTE_DEBUG=true APP_REMOTE_DEBUG_PORT=9222 npx -y pnpm@10.33.0 -F @uno/stage-tamagotchi dev`（项目原生支持，`debugger.ts` 会同时设 remote-debugging-port + remote-allow-origins=http://localhost:9222）。连 WS 时 origin 必须带 `http://localhost:9222`，否则 403。详见 SKILL.md §5。
- 端口：
  - channel-server：`ws://127.0.0.1:6121`（h3 HTTP 也在同一 server，GET 404 是正常的）
  - Vite dev renderer：`http://localhost:5173`
  - U-NO 自带 MCP server：需先在设置里选 Obsidian 仓库（vault 未注册时 `start()` 直接拒绝：'尚未选择 Obsidian 仓库'）
- 窗口（macOS）：
  - 主宠物窗 292×358 @ layer 1001（cua-driver list_windows 看不到，用 CGWindowList 枚举）
  - DevTools 800×600 @ layer 0
  - BeatSync 窗口默认隐藏（onscreen 未知）

## 验证命令（真实可跑）

- i18n 一致性：`npx -y pnpm@10.33.0 check:i18n`（9 locales vs en，1764 键）
- typecheck：`npx -y pnpm@10.33.0 -F @uno/stage-tamagotchi typecheck`（= vue-tsc --noEmit）、`-F @uno/stage-ui typecheck`
- 单测：`npx -y pnpm@10.33.0 -F @uno/stage-ui exec vitest run src/libs/providers`（55 passed）
- ⚠️ 裸跑 `vue-tsc --noEmit -p tsconfig.node.json` 是错路（moduleResolution 错误海啸），必须用 package 脚本

## 已修 BUG（2026-08-07）

1. **EPIPE 崩溃框**：`apps/stage-tamagotchi/src/main/index.ts` 顶部加 `uncaughtException`/`unhandledRejection` 兜底（EPIPE 吞掉、真实错误保留 `dialog.showErrorBox`）。触发条件：stdout 管道读端关闭（后台/supervisor 启动 dev）。`errorMessageFromUnknown` 来自 `@uno/stage-shared`（不是 `errorMessageFromValue`）。
2. **Atlas Cloud i18n 刷屏**：`packages/stage-ui/src/libs/providers/providers/atlascloud/index.ts` 的 `nameLocalize`/`descriptionLocalize` 从硬编码字符串改为 `t('settings.pages.providers.provider.atlascloud.title/description')`，并在 9 个 `packages/i18n/src/locales/*/settings.yaml` 的 deepseek 块前补 `atlascloud:` 键。check:i18n 全绿。
3. **Live2D 主体不渲染（只剩蝴蝶结）——已修复，方案 A（Core 降级 5-r.4）成功**（2026-08-07 21:44 改码 → 21:48 截图确认）：
   - 改动：`electron.vite.config.ts:314` SDK URL `CubismSdkForWeb-5-r.5.zip`→`5-r.4.zip` + `index.html:12` script src 同步改 + 清 4 处 `CubismSdkForWeb-5-r.5` 目录（`.cache`、`src/renderer/.cache`、`src/renderer/public`、`out/renderer`）。
   - **修复后画面（read-image 视觉分析确认）**：完整 hiyori 角色——面部/双马尾长发/红色发饰/米色开衫/深蓝水手领/领结全部可见，占画面 80%+，背景图书馆场景正常，右侧 5 按钮 + 底部 V 按钮完整。修复前只有底部一个蓝色领结。
   - 根因链条完整记录：untitled 引擎内置 Framework 5-r.4 只支持 Core 5.x；5-r.5 SDK zip 自带 Core=6.0.1 → 官方不支持组合 → 主体 drawable 不渲染。详见下方「未决问题→已解决」节的完整取证。
   - 遗留观察：若未来 untitled 引擎发布 v2（适配 csm 5.5/Core 6）可切回 5-r.5；`untitled-backend.ts` 的 drawOrders 补丁在 Core 5.x 下可保留（向下兼容），暂不简化。
4. **自定义模型预览失败（Preview unavailable）——已修复**（详见「未决问题」节完整取证与 2 文件改动）。
5. **MaxListenersExceededWarning（11 move/resize listeners）——已修复**（2026-08-07 22:30）：
   - 根因：`apps/stage-tamagotchi/src/main/services/airi/onboarding/index.ts` 的 `electronOpenOnboarding` handler **每次打开 onboarding 窗口都 addEventListener**（mainWindow move/resize 各 1），cleanup 只挂 `onClosed`；窗口开着时再次 toggle 打开 → 监听器累积（实测 11 个）。
   - 修复（1 文件 +19/-1）：`detachMainMoveListener` 变量保存当前轮移除函数，**进入 handler 先 `detachMainMoveListener?.()`** 再重新挂；`onClosed` cleanup 里同步 detach（双保险）。同时把 `setTimeout` 句柄存入 `ignoreNextMovesTimer` 以便 clearTimeout。
   - 验证：typecheck exit 0 + eslint exit 0 + CDP 调 Vue setupState 的 `openOnboarding` 循环 6 次 → 日志 `grep -c MaxListenersExceededWarning` 恒为 0（修复前同循环累积到 11+）。

## 未决问题（2026-08-07 晚 CDP 运行时取证后更新）

- **#21 模型无法做动作：AI 工具跨窗口 store 隔离（架构 BUG）——2026-08-07 23:0x 监听模式确认，未修**：
  - 现象：用户要求「做动作/展示表情」，AI 回复「我好像没有模型加载呢，所以只能用文字描述啦」。Chat 窗口工具条目（`expression_get`/`spine_list_animations`/`spine_list_skins`）均绿色成功但 AI 收到 `No Live2D model is currently loaded`。
  - 根因（全链路实锤）：Chat 是独立 BrowserWindow（`apps/stage-tamagotchi/src/main/windows/chat/index.ts:22` `new BrowserWindow` + `/chat` 路由）→ 独立 renderer → 独立 pinia store。`App.vue`（所有窗口共享根组件）无条件 `live2dToolsStore.refresh()`（165 行，注释明说「无模型加载时工具执行返回可读错误给 LLM」——设计上就允许 Chat 窗口报此错）→ 每个窗口都注册了 expression 工具，但 execute 里 `useExpressionStore()` 读**当前窗口自己的 store**。模型状态（modelId/expressions）只在主窗口 store，Chat 窗口恒空 → 工具永远报无模型。全仓 grep `broadcast|BroadcastChannel|webContents.send|sendToAll` **零结果** = 无跨窗口同步实锤。
  - 判断「不是用户配置问题」：AI 能回复、工具调用绿色成功 = 服务/模型/工具链都正常；失败在状态可见性（Chat 窗口看不到主窗口的 store）。
  - 修复方向（未实施，见 SKILL.md §11）：A. 跨窗口同步 modelId+expressions（IPC/broadcast 推送）；B. 工具经 IPC 转发主窗口执行（更彻底，expression_set 最终要驱动主窗口渲染）。
  - 证据链记录：expression-tools.ts `ensureModelLoaded()`（`!store.modelId || store.expressions.size===0`）→ expression-store.ts `modelId` 由 `registerExpressions` 设置（模型解析时）→ 主窗口才解析模型 → Chat 窗口永无。App.vue:90/165（注册）+ windows/chat/index.ts（独立窗口）。
  - **ACT token 机制与「提示词层」同样被窗口隔离（2026-08-07 23:2x 用户「查看角色卡里的 Act」追问后取证）**——#21 有两层，工具层 + 提示词层：
    - **ACT 机制**：架构让模型在回复文本中嵌入 `<|ACT {"emotion":"surprised","motion":["shrug","Nod"],"priority":"explicit"}|>` token 驱动角色动作/表情（ACT-strict v1.6 模板，i18n `base.prompt.*`，`packages/i18n/src/locales/*/base.yaml`：prefix/suffix/emotions/motions 四块；配套 `<|DELAY n|>`、`<|CALL [...]|>`）。解析链：`act-extraction.ts` → `normalizeActPayload`（`packages/pipelines-audio/src/llm-streaming-control/payloads.ts`，NormalizedActPayload={emotion,motion,gaze,priority}）→ `act-executor.ts`（createActExecutor 应用 emotion/motion/gaze）。
    - **systemPrompt 组装**（`packages/stage-ui/src/stores/modules/airi-card.ts:434-448`）：`basePrompt + 情绪清单(formatEmotionList) + 动作清单(formatMotionInjection(motionGroups)) + 表情清单(formatExpressionInjection(expressionNames))`。**motionGroups 来自 `useLive2dMotionSource()`（从已加载模型读）、expressionNames 来自 `useExpressionStore().expressionGroups`（注释明说模型未加载时为空）**。
    - **窗口隔离第二层**：Chat 窗口的 `InteractiveArea.vue:38` 也 `useAiriCardStore()` → Chat 窗口自己的 systemPrompt computed 里 motionGroups/expressionNames **恒空** → 发给模型的 system prompt 没有动作/表情清单 → **模型根本不知道有哪些动作可用** → 只能「文字描述表情」。用户问「是不是角色卡描述的 Act 问题」→ 不是角色卡文本写错，是清单注入层被窗口隔离（与工具层同根因）。
    - 结论：修 #21 只同步工具状态还不够——**systemPrompt 的清单注入也要跨窗口同步**（或让 Chat 会话复用主窗口的 orchestrator/airi-card store）。判断「非配置问题」的旁证：AI 能回复、工具绿色成功、但不知道可用动作名。\n\n- **#21 第三层：主窗口的 availableMotions 也可能只有 [\"Idle\"]（模型加载时 motion 解析不全）——2026-08-07 23:3x CDP 取证，未修**：\n  - 背景：验证「主窗口对话是否正常」时，CDP dump 主窗口 `airi-card.systemPrompt`（`/@fs/` import `useAiriCardStore()`）发现**主窗口的动作清单也只有 DELAY、没有模型动作组**，表情清单段缺失（promptLen 2254，cardName=ReLU）。\n  - 关键 localStorage 证据：`settings/live2d/available-motions` = `[\"Idle\"]`（只有 1 个默认组）；`settings/stage/model` = `display-model-HmQIgJ9Cv85Nqp6fwMMMl`（**自定义导入模型**，不是 hiyori 预设）。\n  - 机制：`useLive2dParams().availableMotions` 持久化在 localStorage（`model-parameters.ts:112`），模型加载时写入；`useLive2dMotionSource()` 的 `motionGroups` 优先 ModelProfile（W4 profile 未配置时）回退 `live2d.availableMotions` → 只有 Idle → systemPrompt 动作清单空。\n  - 含义：**「AI 不能做动作」可能是模型加载/解析层问题（自定义模型 motion 组未注册），与跨窗口隔离（#21 前两层）无关**——主窗口自己也中招。需区分：hiyori 预设下 `availableMotions` 是否 >1（若 hiyori 正常 → 自定义模型 motion 解析 BUG；若 hiyori 也只剩 Idle → 通用解析问题）。\n  - 排查顺序沉淀（三层）：① 工具层 store 隔离（Chat 窗口）→ ② 提示词清单注入隔离（Chat 窗口）→ ③ **availableMotions 本身只有 Idle（主窗口也空，模型加载解析层）**。
  - ✅ **③ 最终根因确认（2026-08-07 23:4x，静态检查闭环）：模型包 model3.json 缺少 Motions/Expressions 引用——不是 U-NO 引擎解析 BUG，是模型包本身配置问题**：
    - 对比表（读各 model3.json 的 `FileReferences.Motions`/`Expressions` + 目录实际文件数）：
      - hiyori（官方，正常）：**Motions 8 组 / 10 个**（Idle×3/Flick/Tap×2/...）、Expressions 0（hiyori 用情绪参数非 exp3）
      - 伊拉利娅：**Motions 0 组**、Expressions 0 个（zip 里实际有 1 个 motion3.json + 21 个 exp3.json 但**全未被引用**）→ 引擎只靠文件扫描注册到 1 个 Idle（`Scene1.motion3.json`）
      - 镌恒执刀 繁花永恒：**Motions 0 组**（目录实际 4 个 motion3.json + 34 个 exp3.json 全丢引用）
      - 镌恒执刀 小角度：**Motions 0 组**（同样 4+34 全丢）
    - 机制：引擎忠实读取 model3.json → Motions 空 → `availableMotions=["Idle"]` → systemPrompt 动作/表情清单空 → **AI 不知道有哪些动作可用** → 只能文字描述。文件都在包里，是导出/整理时 model3.json 的引用声明丢失（VTS 导出或人工打包时）。
    - 修复方向（未实施）：① 模型侧——给 model3.json 补 `FileReferences.Motions`/`Expressions` 引用（JSON 手动编辑，文件就在目录里）；② U-NO 侧治本——加载时 model3.json Motions 为空则**自动扫描目录全量补全**（现有逻辑只补了扫描到的 1 个 Idle，修成补全部，任何缺引用的模型包导入都受益）。
    - ✅ **U-NO 侧修复已实施（2026-08-07 23:2x，走 vtube.json 桥而非目录扫描）**：`packages/stage-ui-live2d/src/utils/live2d-zip-loader.ts` 的 `mergeVtubeJsonIntoSettingsJson` 增强——① 补 `IdleAnimationWhenTrackingLost` → 追加进 Motions.Idle；② Hotkeys 循环新增 `Action==='TriggerAnimation' && *.motion3.json` → pushMotion（此前只处理 exp3 表情，动作热键全丢）。提取 `ensureMotions()`/`pushMotion()` 按 File 去重。验证：typecheck exit 0 + eslint exit 0 + **vitest 246 passed**（新增 TriggerAnimation+TrackingLost 用例）；CDP `/@fs/` import 真实镌恒执刀 vtube.json 实测 **动作 1→4**（待机/打瞌睡/签名/沙漏）+ 33 表情注入。测试 helper 默认值注意向后兼容（共享 `createVtubeJsonText` 改默认值会破坏既有断言，新用例显式传 override）。
    - ✅ **数据层修复第二轮（2026-08-08 01:4x，opfs-loader.ts）：vtube 合并下沉到 OPFS 中间件**——实例级 patch 不生效（见 SKILL.md §5.9.1），改为：`OPFSCache.checkMiddleware` cache-miss 分支 + `OPFSCache.save` 都做 vtube 合并（替换 File[] 里 model3.json 为合并文本），`live2DOpfsCacheVersion` 3→5（同步改 opfs-loader.test.ts 的 mock version），`mergeVtubeJsonIntoSettingsJson` 用函数内动态 import（顶层 import 会把 pixi-live2d-display 带进 vitest Node 崩 `window is not defined`）。验证：typecheck/eslint exit 0 + vitest 246 passed + 运行时 console `[OPFS] vtube.json merged into 伊拉利娅完整版/伊拉利娅/白猫大魔女.model3.json` + **OPFS 缓存递归读确认 Expressions 21（伊拉利娅）/33（镌恒执刀）** + CDP 手动 `FileLoader.createSettings(OPFS File[])` → `settings.expressions.length === 33`（数据层全通）。
    - 🟡 **未决（2026-08-08 01:5x）**：数据层全通后 **expression-store 仍空（modelId="", groupCount=0）**——即使切换镌恒执刀（availableMotions=4 生效）+ reload + 清 OPFS 缓存重build。`Model.vue:537/848` 的 `initExpressionController` 应在 loadModel finally 注册，但运行时未生效。**数据层 ≠ 注册层**：settings.expressions 有 33 条（引擎 createSettings 手动验证），但 store 没注册——问题在组件/控制器调用端（initExpressionController 未触发/读的 internalModel 不对/exp3 fetch 失败被 catch 吞），别回数据层找，去查 Model.vue 调用链。
    - 遗留（模型侧未动）：伊拉利娅 zip 内 21 个 exp3 未被 model3.json 引用（其 vtube.json 的 Hotkeys 是否覆盖待查——伊拉利娅可用动作可能仍少）。
    - 与用户「Cubism 版本不一致」「角色卡 Act 写错」假设的判定：moc3 版本（伊拉利娅 4.0/镌恒 5.0）都在 Core 5.1.0 支持范围 → 版本假设排除；角色卡文本正常 → Act 假设排除；**根因唯一指向 model3.json 缺 Motions 引用**。

- **#20 Chat 窗口暴露 AI 内部推理文字（reasoning 泄漏）——2026-08-07 22:5x 监听模式新发现，未修**：
  - 现象（Chat 窗口截图 + read-image 视觉确认）：AI 回复气泡里直接渲染了模型思考过程——英文 `The user is just saying "嗯" (which means "yeah" or "mm-hmm" in Chinese)...`、中文 `用户要求我展示所有现有的表情和动作。首先，我需要使用可用的工具来检...`。
  - 性质：这些是 LLM 的 reasoning/thinking 内容，本应被过滤/折叠（UI 未做 thinking 分离，或服务层把 reasoning 拼进了 content）。涉及隐私暴露 + 可能违反 API 约定（带 reasoning 的模型如 deepseek-reasoner）。
  - 排查方向（未实施）：① Chat 消息渲染组件是否把 `reasoning_content`/`thinking` 字段渲染成消息；② AI 服务层（provider 封装）是否把 reasoning 拼接进 content 返回。
  - 相关工具调用正常：`expression_get`、`spine_list_animations` 等工具条目可见——说明工具调用链路没坏，问题限定在消息文本组装/渲染层。

- ~~**自定义模型预览失败（Preview unavailable）——定位中（伊拉利娅完整版.zip 案例）**~~ → **已解决（2026-08-07 22:15 修复并验证）**：
  - **根因（CDP 运行时取证 + GitHub 调研闭环）**：
    1. untitled 引擎 XHRLoader 用 `XMLHttpRequest` 加载 `blob:` URL **永远挂起**（Chromium 限制，onload/onerror 均不触发）——zip 展开后资源全是 blob: URL，引擎 `urlToJSON` middleware 卡死 → 预览超时 → catch 返回 undefined。
    2. 预览路径（live2d-preview.ts）手动传解析好的 ModelSettings 给 `setupLive2DModel`，但 Vite optimizeDeps 预打包造成**双模块副本**，`settings instanceof ModelSettings` 为 false → 引擎 fallback 成字符串 URL 路径 → XHR 相对路径 `伊拉利娅完整版/伊拉利娅/白猫大魔女.model3.json`（页面上下文不可解析）。
    3. GitHub 调研：untitled 引擎官方 **#18 PR 已删除 zip loader**（作者原话「本来就不能用，也不好用，故删去」）——引擎官方不支持 zip 加载，U-NO 的 zip 支持全靠自造补丁。
  - **修复（2 文件，+76/-5）**：
    - `packages/stage-ui-live2d/src/utils/live2d-zip-loader.ts`：`patchUntitledFileLoaderSanitization` 内新增全局 XHR blob: fetch 桥接补丁（patch `XMLHttpRequest.prototype.open`，`typeof XMLHttpRequest !== 'undefined'` 守卫；关键：先 `origOpen.apply` 保持状态机否则 `send()` 抛 InvalidStateError，`send` 变 no-op，只读属性用 defineProperty 赋值）。
    - `packages/stage-ui-live2d/src/utils/live2d-preview.ts`：untitled 预览分支从「手动 `loadUntitledLive2DZipSettings` 传 settings」改为「传 `{url: objUrl, id: previewId}` 给 `setupLive2DModel`」——复用 OPFS checkMiddleware 正式加载路径，与 Model.vue 一致，绕过双副本 instanceof 陷阱。
  - **验证**：CDP 实测 `loadLive2DModelPreview` → hiyori 238KB / 伊拉利娅 900KB 预览 dataURL 生成成功（修复前为 0）；eslint/typecheck exit 0；vitest 245 passed。
  - 通用模板见 SKILL.md §5.9（XHR blob: URL 挂起 + Vite 双副本 instanceof 陷阱）。
- ~~**Live2D 主体不渲染，只剩蝴蝶结**~~ → **已解决，见已修 BUG #3**。以下取证过程与结论保留作为同类问题的排查模板：
  - **运行时取证结论（CDP + WebGL 插桩，推翻早期假设）**：
    - ❌ 早期假设「texture_00 加载失败只画蝴蝶结」**不成立**——`bindTexture` 12282 次/3s 大量绑定、`texImage2D` 纹理上传发生过（启动期，hook 晚装所以计 0）、GL `getError()==NO_ERROR`。
    - ❌ 「渲染循环没跑」**不成立**——`drawElements` 12104 次/3s（每帧 ~68 次）、`uniformMatrix4fv` 11968 次、MVP 矩阵采样无 NaN/Inf/全零。
    - ⚠️ **readPixels 全透明是误判**：Pixi8 `preserveDrawingBuffer:false`（Canvas.vue:76，防拖影）→ buffer 绘制后回收，readPixels 恒 0。真实画面用 CDP `Page.captureScreenshot`（90KB 非空，说明画面有内容，视觉分析确认只剩蓝色蝴蝶结装饰）。
    - 🎯 **GitHub 调研结论（untitled-pixi-live2d-engine issue #11「适配 Cubism 6 SDK」）**：引擎 README 徽章只支持 Cubism 2/3/4/5；内置 Framework 5-r.4 官方实测不兼容 Core 6.0.1；官方解法=降级 Core 到 5.x（`CubismSdkForWeb-5-r.4.zip` 的 `Core/live2dcubismcore.min.js`）；Framework 5-r.5 仍是 beta 别等上游。
- 次选嫌疑（未触发，留档）：`Model.vue:328-329` modelLoaded 时 `initialModelWidth.value = model.value.width` 若读到 0/异常 → scale 爆炸出画布；3D 场景（stage-ui-three）与 Live2D 合成层级问题。
- 注意模型 store 状态 `scenePhase:"pending"`、`lastCommittedModelSrc:""`（3D 场景侧未提交，与 Live2D 无关，别被带偏）。
- 相关代码位：Canvas.vue（Pixi8 init，preserveDrawingBuffer:false）、Model.vue（modelLoaded→initialModelWidth→setScaleAndPosition）、fit-model.ts（normalize 计算）、untitled-backend.ts:110-124 / legacy-backend.ts:5-25（R5 drawOrders 补丁，OpenCode 确认补丁本身正确）。

## 模型特性表（2026-08-08 实测，测表情/动作前先看这个）

| 模型 | display-model id | 表情（exp3） | 动作（motion3） | 类型 |
|---|---|---|---|---|
| 伊拉利娅 完整版 | `display-model-HmQIgJ9Cv85Nqp6fwMMMl` | 21（Param63/67/71/102...，vtube Hotkeys ToggleExpression） | 1（Scene1.motion3.json → Idle） | 纯表情型 |
| 镌恒执刀 繁花永恒 | `display-model-OrdEnXee8djo1p_MyDQOE` | 33 | 4（待机/打瞌睡/签名动画/沙漏动画） | 表情+动作型 |
| 菜咪-灵蝶之狐 | `display-model-KXVFeqDEdqdlfJ2AFy_pB` | 未测 | 未测 | — |

- 表情可用名是 **ParamNN 参数 ID**（`store.set('__probe__',1).available` 枚举），数量 = exp3 文件数。
- 动作触发走 `useLive2dParams().emitMotionEvent({group, index})`；`currentMotion.value=` 只写状态不播放（详见 SKILL.md §5.10）。
- 伊拉利娅重复导入过两次（HmQIgJ9Cv85Nqp6fwMMMl 与 e8wCMuMPRhu9ThXwtbH1R），切换时用 display-models store 的 id，勿写死。

## 表情注册阻塞已解除（2026-08-08 复查确认）

上次未决「expression-store 空（modelId='', groupCount=0）」已消失：运行时 `expressionsSize=21`、`modelId='model-url:伊拉利娅完整版/伊拉利娅/白猫大魔女.model3.json'`、`expressionGroups` Map size=21（expression1-21）、`expression-enabled` 版本化迁移生效（`{"version":"2.0.0","data":true}`）。`store.set('expression1',1)` 返回 `{success:true, state:[{name:'Param71', value:1, autoResetAt:...}]}`。**验证链**：CDP `/@fs/` import expression-store → `$state` dump + `set('__probe__',1).available` 枚举 + 触发后 `Page.captureScreenshot` 对比。

## 伊拉利娅 21 表情映射（cdi3 参数名，2026-08-08 实测；「表情」很多是素材开关）

每个 exp3 都是**单参数终值**（`expressionN.exp3.json` = `[{Id:"ParamNN", Value:1, Blend:"Add"}]`，无关键帧）——VTS 皮套的 exp3 本来就是「参数置位」，动画感要靠驱动层渐变（见下）。cdi3.json `Parameters[].Name` 是「这个 Param 是表情还是道具」的 ground truth：

| expression | Param | cdi3 名 | | expression | Param | cdi3 名 |
|---|---|---|---|---|---|---|
| expression1 | Param71 | 惊讶 | | expression12 | Param41 | 帽子（素材）|
| expression2 | Param67 | 生气 | | expression13 | Param44 | 虎牙 |
| expression3 | Param68 | 无语 | | expression14 | Param89 | 笔芯 |
| expression4 | Param72 | 爱心 | | expression15 | Param91 | 魔法书（素材）|
| expression5 | Param69 | 星星 | | expression16 | Param101 | 法杖（素材）|
| expression6 | Param78 | 哭哭 | | expression17 | Param90 | 麦克 |
| expression7 | Param73 | 阿尼亚 | | expression18 | Param88 | q版 |
| expression8 | Param70 | 疑问 | | expression19 | Param62 | 罗马卷 |
| expression9 | Param66 | 汗 | | expression20 | Param82 | 坐姿 |
| expression10 | Param63 | 呆毛龙卷风 | | expression21 | Param87 | 咪咪 |
| expression11 | Param102 | 光环 | | | | |

- 查法：CDP 读 OPFS 缓存 `display-model-HmQIgJ9Cv85Nqp6fwMMMl` 目录的 `*.cdi3.json` + 21 个 exp3，映射表由 `cdi3.Parameters[].Id→Name` + `exp3.Parameters[].Id` 交叉得出。
- **用户验收发现（2026-08-08）：「表情触发成功但只是素材/部件硬切、没动画感」**——触发表情后画面确实变（ParamNN=1 生效），但 0→1 **一帧跳变**（VTS 里表情热键有 fadeIn/fadeOut 渐变）。根因：U-NO 用自研 expression-controller 替代引擎 expressionManager（Model.vue:551 `motionManager.expressionManager = null`，因引擎 manager 在 motionManager.update 后跑会覆盖 final-plugin 值），但自研 controller 每帧 `setParameterValueById` 直写终值、**无时间插值**。
  - ✅ **已实施并验证（2026-08-08 下午）**：`expression-controller.ts` 的 `applyExpressions` 加 VTS 式 fade 渐变（easeOutCubic，默认 500ms，exp3 FadeInTime/FadeOutTime 优先，`fadeStates` 渲染层插值，store currentValue 仍是语义目标）；`motion-manager.ts` 调用处 `ctx.now * 1000`（**引擎 now 是秒，单位陷阱**——否则渐变停滞成每帧 +0.0001）。验证：typecheck/eslint 0 + vitest 248 passed（+2 fade 用例）+ CDP 参数轨迹（0→1 约 500ms）+ 连拍截图视觉确认生气表情分阶段成型。完整模板见 live2d-runtime-drive「VTS 式表情渐变（fade）」节。
- **✅ 「表情/道具卡住不复位」已修复（2026-08-08 下午）**：症状=触发后 3s 自动复位不生效、道具（Param91 魔法书/101 法杖/41 帽子）永远显示。根因=**双写入源**：`Model.vue` loadModel 的「道具参数驱动」段（遍历 `modelParameters` 额外 Param* 键 value>0 写 coreModel）与 expression-controller 写同一批参数；而 `modelParameters` 是 `useLocalStorageManualReset('settings/live2d/parameters')` 持久化，残留值（Param91=1）不会被 expression-store 复位清理 → coreModel 被残留卡住。修复=道具驱动段跳过 expression-store 已注册的 parameterId + CDP 清 localStorage 残留。验证链：清残留→reload→coreModel 归零→触发→渐入/渐出完整周期。完整模板见 live2d-runtime-drive「双写入源 + localStorage 残留」节。

## 其他已知点

- **正式构建版 vs dev 模式**：`~/Applications/U-NO.app` 是 build 产物（app.asar 里 `out/main/index.js`），**只含构建时刻的代码**——构建后做的修复（XHR blob 桥 22:15、VTS 补全 23:26 等）不在其中。2026-08-07 实测：用户重开 16:30 构建的 U-NO.app 后「主界面/角色窗口一直 loading」= 旧版缺 blob 桥 → 加载导入模型（blob URL）时 XHR 挂起；dev 模式（CDP 确认 Core 5.1 + OPFS cache hit + WebGL 正常 + Page.captureScreenshot 271KB 角色完整渲染）一切正常。**排查「用户说 loading/行为不对」先查日志里是否 `app.asar` 路径 + `ls -la` 构建时间**，别在旧构建上调 BUG。两者共用 user-data-dir（模型/IndexedDB 互通）。
- 主窗口右侧 6 按钮（controls-island）：设置/toggle/聊天/刷新/重置位置/深色模式，走 Eventa IPC（`electronOpenSettings` 等）
- **Eventa IPC 通道**：invoke 通道（`eventa:invoke:electron:windows:onboarding:open` 等）**不能**用 `window.electron.ipcRenderer.invoke()` 直接调（报 No handler——eventa renderer adapter 实际用 `ipcRenderer.send` + 独立响应通道）。触发 UI 用 CDP 深扫 Vue setupState 找函数直接调（如 `openOnboarding`，见 SKILL.md §9）。
- 角色卡/模型数据在 IndexedDB + OPFS（`~/Library/Application Support/U-NO/`）；模型预设 `preset-live2d-1` = `hiyori_pro_zh.zip`（文件完整 23 项）
- 3D 场景背景（图书馆等）来自 stage-ui-three，localStorage 键 `settings/stage-ui-three/*`——不是 Live2D 一部分
- logg 库版本 @guiiai/logg 1.2.11 的 `outputToConsole` 无 try/catch（EPIPE 根因）

## Model Audit Report（模型审计弹窗，导入自定义模型时弹出）

导入 Live2D 模型后 U-NO 会弹「Model Audit Report」审计面板（Close/Cancel 按钮），两类警告：

1. **BASENAME COLLISION（同名纹理冲突，红色条目）**：zip 内**多个子模型目录**（如「镌恒执刀 繁花永恒」和「镌恒执刀 繁花永恒 小角度」）各自含同名 `texture_4X.png`。AIRT 加载器按**文件名（basename）**建索引 → 同名不同内容会互相覆盖、数据丢失，模型贴图错乱。
   - 用户侧修复：重命名冲突文件使 basename 唯一（如 `texture_41.png`→`texture_41_big.png`/`texture_41_small.png`），或删掉不用的子模型变体。
2. **HEAVY RESOURCE（MOC 过大，黄色条目）**：moc3 文件 >~30MB，web/Electron 渲染性能风险。本地跑通常可忽略，主要影响网页端加载速度。

对默认 hiyori 模型无此弹窗——只在导入自定义模型时出现；不影响其他功能，可 Cancel 关闭。

## 模型导入大小限制实测（2026-08-07，391MB「雕刻师 - qq1126045441.zip」）

- **审计阈值（`packages/stage-ui-live2d/src/utils/live2d-validator.ts`）**：MOC `>30MB` → warning「HEAVY RESOURCE」（可导入，弹报告窗需确认）；`>100MB` → error「CRITICAL WEIGHT」→ **INVALID 阻断**。用户问「30 多 MB 上限」= 30MB warning 阈值，不是硬限制。
- **391MB zip 实测（`validateLive2DZip` CDP 跑）**：status=**INVALID**，但被拒原因是 **BASENAME COLLISION**（两个子模型目录「镌恒执刀 繁花永恒」+「小角度」的 34 个 exp3 同名冲突，每条都是 error），**不是大小**——MOC 各 31.0MB（<100MB 不触发 size error），92 个纹理合计 390.8MB（4096 分辨率）。
- **给用户的「400MB 咋整」答案**：a) 子模型拆成独立 zip 分别导入（消冲突）；b) 重命名冲突文件使 basename 唯一；c) 只留一个子模型变体。30MB warning 忽略即可。
- **诊断手法**：CDP `/@fs/` import `live2d-validator.ts` → fetch zip → `new File([blob], 'x.zip')` → `validateLive2DZip(file)` 直接看 `errors[]` 列表，区分「大小」与「冲突」两类 error。
