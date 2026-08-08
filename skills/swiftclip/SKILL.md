---
name: aigc:swiftclip
description: |
  影视·SwiftClip — 34 个 Remotion 视频模板库（搬模板不造轮子）。触发词：视频模板、SwiftClip、Remotion 模板、产品发布视频、社媒视频、片尾、开场、数据可视化视频、Lower Third、竖屏视频。不用于：精剪工程（openchatcut）、AI 出图（aigc:image-gen）。
---

# SwiftClip：Remotion 视频模板库

> 模板库位置：`~/Desktop/codex项目列表/资源库/SwiftClip/`（34 个生产级模板，MIT）
> 哲学：**改参数不拖关键帧**——写 React 组件而非 AE 关键帧。

## 何时用

用户要"做视频"且适合**程序化模板**时（产品发布/社媒卡片/数据可视化/开场片尾/竖屏故事），先查本模板库，命中直接改参数；不适合的（真人精剪/长片）走 openchatcut。

## 模板清单（remotion/ 目录）

| 模板 | 用途 | 适用场景 |
|---|---|---|
| ProductLaunch.tsx | 产品发布 | 新品官宣、SaaS 上线 |
| SocialStory.tsx | 社媒竖屏故事 | 小红书/抖音/IG Story |
| DataViz.tsx / BarChart.tsx / MetricDashboard.tsx | 数据可视化 | 报告、复盘、增长数据 |
| LowerThird.tsx | 字幕条 | 采访、口播、直播包装 |
| EndScreen.tsx | 片尾 | 频道收尾、CTA |
| CountdownTimer.tsx | 倒计时 | 活动预告、直播预热 |
| BrandReveal.tsx / GradientReveal.tsx | 品牌揭示 | 品牌片头 |
| CodeReveal.tsx | 代码展示 | 编程教学、技术分享 |
| NewsBreaking.tsx / EventPromo.tsx / PricingCard.tsx | 新闻/活动/定价 | 通知、活动、方案页 |
| MinimalTitle.tsx / AppleMovie.tsx / Macintosh.tsx | 极简标题/苹果风 | 高级感开场 |
| CelebrationBurst.tsx / DynamicIsland.tsx | 庆祝/灵动岛 | 节日、成就、系统风 |

## 使用步骤

1. 定位模板：按上表找最接近的 `remotion/<Name>.tsx`
2. 改参数：编辑模板的 props（文案、时长、颜色、分辨率），**不写新组件**（除非参数无法表达）
3. 渲染：`cd ~/Desktop/codex项目列表/资源库/SwiftClip && npx remotion render <CompName> out.mp4 --scale=2`
4. 竖屏：`--codec=h264` + 在 Composition 里设 1080×1920

## 关键路径

- 模板：`~/Desktop/codex项目列表/资源库/SwiftClip/remotion/`
- 入口/注册：`~/Desktop/codex项目列表/资源库/SwiftClip/remotion/index.ts`
- 依赖：Remotion 4.x + React 19 + lucide-react（`npm install` 后可用）

## 互补链

- 需要 AI 脚本/分镜 → 先走 `aigc:film`（归档恢复）
- 需要批量产片 → 模板参数化 + cron 批量渲染
- 需要精剪/口播清理 → `openchatcut-plugin-basics`
- 需要纯代码渲染动画（Manim）→ `aigc:video`（归档恢复）
