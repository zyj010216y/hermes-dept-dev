#!/usr/bin/env python3
"""CDP probe skeleton for Electron renderer forensics.

Connects to a running Electron renderer over CDP (launched with
APP_REMOTE_DEBUG=true APP_REMOTE_DEBUG_PORT=9222, or REMOTE_DEBUGGING_PORT=9222),
then: scans the canvas for actual drawn pixels, hooks WebGL draw/texture calls
to distinguish "render loop not running" vs "drawn but invisible", and captures
a real composited screenshot.

Usage: adjust TARGET_URL_SUBSTR + ORIGIN below, then `python3 cdp-electron-probe.py`.

Key lessons baked in:
- Electron 33+ CDP WebSocket rejects cross-origin connects with HTTP 403.
  ORIGIN must match the app's remote-allow-origins value (U-NO sets it to
  http://localhost:<port>).
- preserveDrawingBuffer:false => gl.readPixels always returns transparent.
  Canvas pixel scan via readPixels is a TRAP; use Page.captureScreenshot for
  ground truth of what is actually displayed.
- Page.captureScreenshot needs NO macOS screen-recording permission.
"""
import asyncio
import base64
import json
import urllib.request

TARGET_URL_SUBSTR = 'localhost:5173/#/'  # main-window page target; exclude onboarding etc.
ORIGIN = 'http://localhost:9222'          # must match app's remote-allow-origins
DEBUG_PORT = 9222


async def main() -> None:
    pages = json.load(urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json'))
    page = next((p for p in pages if TARGET_URL_SUBSTR in p['url'] and 'onboarding' not in p['url']), None)
    if not page:
        print('page target not found:', [p['url'] for p in pages])
        return
    print('target:', page['id'], page['url'])

    import websockets
    async with websockets.connect(page['webSocketDebuggerUrl'], origin=ORIGIN, max_size=30_000_000) as ws:
        mid = 0

        async def send(method: str, params: dict | None = None) -> dict:
            nonlocal mid
            mid += 1
            await ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                msg = json.loads(raw)
                if msg.get('id') == mid:
                    return msg

        async def ev(expr: str):
            r = await send('Runtime.evaluate', {
                'expression': expr, 'returnByValue': True, 'awaitPromise': True,
            })
            res = r.get('result', {})
            if 'exceptionDetails' in res:
                return 'EX: ' + res['exceptionDetails'].get('exception', {}).get('description', '')[:400]
            return res.get('result', {}).get('value')

        # 1. canvas pixel scan — NOTE: with preserveDrawingBuffer:false this reads
        #    all-transparent even when content IS rendered. Use only as a hint.
        print('canvas pixels:', await ev(r"""(() => {
          const c = document.querySelector('canvas'); if (!c) return 'no-canvas';
          const gl = c.getContext('webgl2') || c.getContext('webgl'); if (!gl) return 'no-gl';
          const w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
          const px = new Uint8Array(w * h * 4);
          gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
          let opaque = 0; for (let i = 3; i < px.length; i += 4) if (px[i] > 128) opaque++;
          return JSON.stringify({w, h, opaquePixels: opaque});
        })()"""))

        # 2. WebGL instrumentation — install hooks, wait, read counters
        print('hook:', await ev(r"""(() => {
          const c = document.querySelector('canvas'); if (!c) return 'no-canvas';
          const gl = c.getContext('webgl2') || c.getContext('webgl'); if (!gl) return 'no-gl';
          if (window.__probeStats) return 'already-hooked';
          const s = window.__probeStats = { draws: 0, binds: 0, matrices: 0, clearCount: 0 };
          const od = gl.drawElements.bind(gl); gl.drawElements = (...a) => { s.draws++; return od(...a); };
          const ob = gl.bindTexture.bind(gl); gl.bindTexture = (...a) => { s.binds++; return ob(...a); };
          const om = gl.uniformMatrix4fv.bind(gl);
          gl.uniformMatrix4fv = (...a) => { s.matrices++; if (s.matrices <= 3) s.sample = a[2] ? Array.from(a[2].slice(0,4)) : null; return om(...a); };
          const oc = gl.clear.bind(gl); gl.clear = (...a) => { s.clearCount++; return oc(...a); };
          return 'hooked';
        })()"""))
        await asyncio.sleep(3)
        print('stats (3s):', await ev('JSON.stringify(window.__probeStats)'))
        print('gl error:', await ev(r"""(() => {
          const gl = document.querySelector('canvas').getContext('webgl2') || document.querySelector('canvas').getContext('webgl');
          return gl.getError() === gl.NO_ERROR ? 'NO_ERROR' : 'ERR_' + gl.getError();
        })()"""))

        # 3. REAL ground-truth screenshot (compositor pipeline; no screen-rec permission)
        await send('Page.enable')
        shot = await send('Page.captureScreenshot', {'format': 'png'})
        if 'data' in shot.get('result', {}):
            img = base64.b64decode(shot['result']['data'])
            path = '/tmp/uno-cdp-screenshot.png'
            open(path, 'wb').write(img)
            print(f'screenshot: {path} ({len(img)} bytes) — non-empty means content IS drawn')
        else:
            print('screenshot failed:', json.dumps(shot)[:300])


if __name__ == '__main__':
    asyncio.run(main())
