---
name: slidev-presentations
description: "使用 Slidev 从零创作结构清晰、视觉完成度高的演示文稿、汇报、路演材料、技术分享或课程课件，并交付 Slidev 源文件、PDF、PNG、Web 或图片型 PPTX。适用于用户更重视演示效果和视觉还原、无需在 PowerPoint 中逐项编辑文本与图形的任务。不用于读取或修改现有 PPTX、套用原生 PowerPoint 模板，或创建必须完全可编辑的 PPTX；这些任务使用 powerpoint skill。"
---

# Slidev 幻灯片创作

把 Slidev Markdown 作为可编辑源文件，先完成叙事和视觉设计，再渲染检查。不要把提纲直接堆成标题加项目符号。

## 文件与交付边界

- 默认工作目录：`$HERMES_DOCK_PROFILE_HOME/tmp/slidev/<slug>`，不得把非 default profile 的源文件写进 `/opt/data/tmp`。
- 默认交付目录：`/opt/data/.dock/shared/<deck-name>`。
- 不覆盖已有文件或目录；目标已存在时停止并让用户指定新名称。
- 保留 `slides.md`、`style.css`、`layouts/`、`public/` 和依赖锁文件，作为真正可编辑的源文件。
- 交付源文件时不要复制 `node_modules`、预览图片或其他可重新生成的缓存和构建产物。
- 明确说明 Slidev 导出的 PPTX 每页是图片：适合放映和分享，不支持逐项编辑文字、图表或形状。
- 用户要求原生可编辑 PPTX、修改现有 PPTX 或沿用 PowerPoint 模板时，改用 `powerpoint` skill。

## 必须读取的参考

开始创作前读取 [narrative.md](references/narrative.md) 和 [visual-design.md](references/visual-design.md)。需要编写或导出 Slidev 时再读取 [slidev.md](references/slidev.md)。

## 工作流

1. **确定约束**：确认受众、演示目的、时长、语言、交付格式、品牌素材和是否要求 PowerPoint 元素可编辑。只有会显著改变结果且无法合理推断的缺失信息才询问；否则说明假设并继续。
2. **规划叙事**：先写页面计划。每页记录一句结论、支持证据、视觉形式和讲者备注；不要先写 Slidev 代码。
3. **初始化项目**：运行：

   ```bash
   node <skill-dir>/scripts/init-deck.mjs "$HERMES_DOCK_PROFILE_HOME/tmp/slidev/<slug>"
   ```

4. **替换 starter**：重写示例文案，选择与信息类型匹配的布局。将本地图片放进 `public/`，使用 `/文件名` 引用。不要保留占位文字。
5. **控制素材**：优先使用用户提供或有明确来源的素材。下载远程图片到 `public/` 后再引用，避免导出依赖临时 URL。不得伪造数据、引文或来源。
6. **预检**：运行：

   ```bash
   node <skill-dir>/scripts/preflight.mjs "$HERMES_DOCK_PROFILE_HOME/tmp/slidev/<slug>"
   ```

7. **渲染检查**：先导出 PNG，逐页检查完整尺寸图片；联系表只能辅助检查整套节奏，不能替代逐页检查。修复截断、拥挤、低对比、错误裁切、意外换行和布局重复。
8. **导出交付物**：确认 `/opt/data/.dock/shared/<deck-name>` 不存在，再使用不带 `-p` 的 `mkdir` 创建一次交付根目录。使用 `export-deck.mjs` 导出 PDF、PPTX、Web 或 PNG；脚本要求父目录存在，但拒绝覆盖具体输出。脚本固定依赖、复用 `AGENT_BROWSER_EXECUTABLE_PATH`，并显式关闭点击步骤展开。
9. **交付说明**：报告源目录和导出文件的完整路径；如果交付 PPTX，必须同时提示它是图片型 PPTX。

## 导出命令

```bash
node <skill-dir>/scripts/export-deck.mjs \
  "$HERMES_DOCK_PROFILE_HOME/tmp/slidev/<slug>" \
  png \
  /opt/data/.dock/shared/<deck-name>/preview

node <skill-dir>/scripts/export-deck.mjs \
  "$HERMES_DOCK_PROFILE_HOME/tmp/slidev/<slug>" \
  pdf \
  /opt/data/.dock/shared/<deck-name>/<deck-name>.pdf

node <skill-dir>/scripts/export-deck.mjs \
  "$HERMES_DOCK_PROFILE_HOME/tmp/slidev/<slug>" \
  pptx \
  /opt/data/.dock/shared/<deck-name>/<deck-name>.pptx

node <skill-dir>/scripts/export-deck.mjs \
  "$HERMES_DOCK_PROFILE_HOME/tmp/slidev/<slug>" \
  web \
  /opt/data/.dock/shared/<deck-name>/web
```

首次运行需要从当前 npm registry 安装锁定依赖。安装失败时返回真实错误，不改用 `latest`、不全局安装、不下载另一套 Chromium，也不静默切换生成器。

## 内容硬约束

- 一页只表达一个主要结论；页面标题优先写结论，不写空泛栏目名。
- 标题页和章节页保持低密度。内容过多时删减或拆页，不缩小到难以投影阅读。
- 默认不用满页项目符号，不把长段落原样搬进幻灯片。
- 图表先表达结论，再保留必要刻度和来源；没有数据时不要制造图表。
- 视觉元素必须服务信息。不要为了满足“每页一张图”而添加装饰图、随机图标或无意义渐变。
- 面向观众写页面文案。规划说明、设计理由和制作提示只能放在工作记录中，不得出现在页面上。

## 视觉验收

逐页确认：

- 标题没有意外换成两行，正文没有裁切或溢出。
- 页面边缘留白一致，相邻元素没有贴边、重叠或失衡。
- 正文、来源和图表标签在投影尺寸下仍可读。
- 图片没有拉伸，主体没有被错误裁切。
- 页面之间既保持同一视觉系统，也没有连续重复同一构图。
- 事实、数据、图片和引文能够追溯来源。
- PPTX/PDF 中没有缺失字体、未完成动画或未渲染组件。

导出失败或视觉检查未通过时不要交付半成品。
