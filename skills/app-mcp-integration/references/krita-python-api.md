# Krita 5.3.3 API 面与插件内嵌服务器架构

## Krita 外部控制现状
- **无 DBus**（macOS 编译未带，Linux 版才有 org.krita 总线）
- **无 WebSocket/远程服务器**（strings 二进制无 QWebSocketServer）
- **无原生 MCP** → 外部控制必须走 pykrita 插件内嵌服务器

## Python API 面（官方文档 + 权威类型桩）
- 类型桩: /Applications/krita.app/Contents/Frameworks/krita-python-libs/PyKrita/krita.pyi
  （SIP 6.10 生成，1088 行，46 类 / 786 方法+信号）
- 真实包: /Applications/krita.app/Contents/Frameworks/PyKrita.framework/Versions/<ver>/lib/krita/
- 核心类：Krita(37) Document(108) Node(65) View(50) Window(14) Selection(32)
  Filter(9) InfoObject(7) Notifier(12 信号) + 12 个图层子类 + Shape/Resource/Palette/ManagedColor
- 插件全局：Scripter/Application/Krita 三个都指向 Krita.instance()
- 装饰器：@init/@unload/@pykritaEventHandler（生命周期钩子）
- **隐藏巨大面**：插件可 import 完整 PyQt5（QtCore/QtGui/QtWidgets/QtXml）
- 万能口：Node.paintLine/Rectangle/Ellipse/Polygon/Path 程序化绘制；
  Krita.action(name) 触发任意内置 UI 动作

## 插件内嵌服务器架构（kritamcp_full，端口 9877）
```
Codex ─stdio─> MCP server (FastMCP) ─HTTP JSON-RPC─> kritamcp_full 插件(Krita 内)
```
- 线程模型（关键）：HTTPServer 跑 Python daemon 线程；
  命令入 queue.Queue；QTimer(25ms) 在 Krita 主线程 poll 执行（Krita API 只能主线程调）；
  结果 threading.Event 通知 HTTP 线程返回
- 动作注册表：registry.py 汇总 actions/ 各功能模块的 ACTIONS dict
- 测试开关：环境变量 KRITAMCP_NO_AUTOSTART=1 禁用插件自启（供外部测试 import）

## 插件安装
- 拷贝到 ~/Library/Application Support/krita/pykrita/（插件目录 + .desktop 文件）
- Krita: 设置→配置 Krita→Python 插件管理器→启用→**必须重启 Krita**
- GUI 坑：配置对话框 AX 树文本读不到（Qt 自绘），System Events 拿列表为空，
  computer_use 也 0 元素——别硬刚，让用户手动启用，curl http://127.0.0.1:9877/ping 验证

## 第三方 Krita MCP 对比
| 项目 | 架构 | 工具数 | 定位 |
|---|---|---|---|
| nanayax3/krita-mcp (25★活跃) | 插件 HTTP :5678 + FastMCP | 15 | 绘画（stroke/fill/shape） |
| halby24/KritaMCP (归档) | 插件 + mcp_server | 6 | 文档/图层 + execute_python 万能口 |
| lorisliaoloris/krita-mcp | hermes_bridge HTTP :9876 | 3 端点 | 极简桥 |

## 用户工作流（Live2D 皮套）
- krita_live2d_prep 插件（用户自研，~/Library/Application Support/krita/pykrita/）：
  cleaning.py（alpha 阈值清洗+盒式模糊）、export_psd.py（分层/单文件 PSD）、
  naming.py（去重命名）、preprocess.py（组扁平化/遮罩烘焙）
- 本项目: ~/Desktop/codex项目列表/krita-mcp-full
  = krita-core（58 工具，13 功能模块）+ krita-live2d（6 工具），已注册 codex

## token 参考
- krita-core 58 工具 ≈ 32KB ≈ 8.2K tokens；krita-live2d 6 工具 ≈ 0.8K tokens
- 对比 cubism-mcp-full 55 工具 ≈ 11.5K tokens
