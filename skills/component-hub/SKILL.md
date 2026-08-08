---
name: frontend:component-hub
description: |
  前端·组件枢纽 — 搬模块不造轮子：shadcn/ui + kibo + creative-tim 组件库对接。触发词：组件库、shadcn、kibo、搬组件、复用组件、UI 组件、落地页区块、registry、前端模块。不用于：从零写组件（应先查本库）、视觉设计规范（design:brand）。
---

# 组件枢纽：搬模块不造轮子

> 哲学：**先查库，再写代码**。前端 UI 一律优先从组件库搬运，不手写轮子。

## 组件源（按优先级）

### 1. shadcn/ui（项目内 registry，最优先）
```bash
# 在目标项目里直接拉官方组件
npx shadcn@latest add button card dialog dropdown-menu tabs
# 自定义 registry（kibo 等第三方区块）
npx shadcn@latest add https://shadcnblocks.com/r/kibo.json  # kibo 落地页区块
```

### 2. kibo / shadcnblocks（⭐3.9k，落地页/区块模板）
- 官网：shadcnblocks.com —— 现成落地页区块（Hero/Feature/Pricing/Testimonial/FAQ）
- 用法：选区块 → 复制 registry URL → `npx shadcn add <url>` → 进项目改文案
- 适合：营销页、SaaS 落地页、作品集

### 3. creativetimofficial/ui（⭐12k，完整组件+AI agents）
- 仓库：github.com/creativetimofficial/ui
- 用法：克隆或复制对应组件到项目 components/
- 适合：需要完整主题/多组件组合时

### 4. ElevenLabs/ui（⭐2.3k，语音 AI 风组件）
- 仓库：github.com/elevenlabs/ui —— 声音相关的 UI（波形/录音/播放器）

## 搬运 SOP（标准流程）

1. **查**：先查本技能 4 个源，确认有没有现成组件/区块
2. **搬**：`npx shadcn add` 或复制源码，**不改结构只改数据**（文案/颜色/图片）
3. **适配**：只调样式变量（tailwind class / CSS var），不动组件逻辑
4. **不造**：找不到才手写，手写前先说明"为何不搬"

## 与现有技能衔接

- 视觉风格/审美 → `ui-craft`（反 AI 味规则）
- 品牌/design tokens → `design:brand`（归档恢复）
- 性能优化 → `frontend:perf-seo`（归档恢复）
- 页面实现 → `frontend:web-ui`（归档恢复）

## 组件源速查表

| 需求 | 去哪搬 |
|---|---|
| 落地页区块（Hero/定价/FAQ） | kibo/shadcnblocks |
| 基础组件（按钮/卡片/弹窗） | shadcn/ui |
| 完整 UI 主题 | creativetimedical/ui |
| 语音/音频 UI | ElevenLabs/ui |
| 图表/数据可视化 | lieflat-charts + shadcn chart |
