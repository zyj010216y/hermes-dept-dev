# U-NO CDP 远程调试实战（2026-08-07）

## 启动与连接
```bash
# 项目原生调试开关（自动配 remote-allow-origins，比 REMOTE_DEBUGGING_PORT 正统）
export APP_REMOTE_DEBUG=true APP_REMOTE_DEBUG_PORT=9222
npx -y pnpm@10.33.0 -F @uno/stage-tamagotchi dev
```
- 页面列表：`curl http://127.0.0.1:9222/json` → 找 `url` 以 `#/` 结尾且非 beat-sync 的 target
- **必须带 origin**（Electron 41 白名单）：`websockets.connect(wsUrl, origin='http://localhost:9222')`，否则 403

## 探针脚本骨架（Python websockets）
```python
async def ev(expr, timeout=120):
    # Runtime.evaluate 带 awaitPromise + returnByValue
    await ws.send(json.dumps({'id': mid, 'method': 'Runtime.evaluate',
        'params': {'expression': expr, 'returnByValue': True, 'awaitPromise': True}}))
    # 循环 recv：id 匹配返回；consoleAPICalled/exceptionThrown 收集日志
```

## 关键技巧
1. **动态 import 项目模块**：`await import('/@fs/<绝对路径>')` 页面顶层可加载项目源码直接调用（如 `loadLive2DModelPreview`、`mergeVtubeJsonIntoSettingsJson`）。包名 import（`'untitled-pixi-live2d-engine/cubism'`）页面顶层失败——Vite 编译期才解析。HMR 后旧模块缓存残留，先 `Page.reload`。
2. **找 pinia store**：devtools hook `window.__VUE_DEVTOOLS_GLOBAL_HOOK__.apps[0]._instance` 递归扫 `setupState` 中 `$id` 匹配的对象；懒加载 store 主窗口可能没挂（如 display-models），需动态 import store 模块调用。
3. **WebGL 插桩**（判断渲染循环是否真在画）：
   ```js
   const gl = canvas.getContext('webgl2');
   const orig = gl.drawElements; let count = 0;
   gl.drawElements = function(...a) { count++; return orig.apply(this, a); };
   // 3 秒后 count 大量（~70/帧）→ 渲染循环正常
   ```
   同理可 hook bindTexture / uniformMatrix4fv / getError。
4. **blob XHR 挂起验证**：`new XMLHttpRequest(); xhr.open('GET', blobUrl); xhr.responseType='json'; xhr.onload=...` 永不触发 onload/onerror（超时）→ 确认 Chromium blob: + XHR 挂起；`fetch(blobUrl)` 正常。
5. **readPixels 误判**：`preserveDrawingBuffer:false` 时绘制后 buffer 被回收，readPixels 恒 0 → 用 `Page.captureScreenshot`。
6. **URL 日志**：hook `XMLHttpRequest.prototype.open` 和 `window.fetch` 记录 URL，看引擎实际请求 blob: 还是相对路径。

## 本次修复的探针用途
- 预览失败复现：直接调 `loadLive2DModelPreview(file)` 拿返回长度（0=失败，20万+=成功）
- 动作验证：读 localStorage `settings/live2d/available-motions`（模型加载后写入，JSON 数组含 motionName/fileName）
- 模型切换：store `stageModelSelected` setter + `updateStageModel()`（直接写 localStorage + reload 会被 store 初始化覆盖）
- 动作播放验证：`[render-kernel] motion.started <组名>` 出现在 console（Runtime.enable 后监听）
