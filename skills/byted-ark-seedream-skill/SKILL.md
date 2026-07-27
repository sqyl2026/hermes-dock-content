---
name: byted-ark-seedream-skill
license: MIT
description: 使用火山方舟 Agent Plan 的豆包 Seedream 生成或编辑图片。用户明确要求使用 Seedream、豆包或火山方舟生成图片时使用；未指定服务时可在已配置 ARK_AGENT_PLAN_API_KEY 的情况下使用。不要用于视频生成。
compatibility: Requires Node.js 18+, network access, and ARK_AGENT_PLAN_API_KEY configured by Hermes Dock.
metadata:
  author: volcengine/agentplan
  version: "3.0.0-hermes-dock.1"
  category: ai/image-generation
---

# Ark Agent Plan Seedream

本 skill 是火山引擎官方 `byted-ark-seedream-skill` 的 Hermes Dock 内置快照。认证方式以本文件为准：只使用当前 profile 的 `ARK_AGENT_PLAN_API_KEY`，不要要求用户在对话中发送密钥，也不要通过命令行参数保存或修改密钥。

## 使用

在 skill 根目录执行：

```bash
node scripts/generate.js \
  --prompt "一只英短蓝猫趴在洒满阳光的木质窗台上"
```

常用参数：

- `--size 2K|3K`
- `--sequential true --count 4`：生成连贯组图；prompt 必须明确每张图内容和风格一致性
- `--mode image-to-image --reference_images /opt/data/path/to/image.png`
- `--watermark false`
- `--optimize false`
- `--enable_web_search true`
- `--response_format png|jpeg`

不要传 `--api-key`、`--save-api-key` 或其他密钥参数。缺少密钥时，引导用户在 Hermes Dock 的“火山方舟 Agent Plan”供应商页填写并“应用配置”。

生成文件默认保存到当前 profile 的：

```text
$HERMES_DOCK_PROFILE_HOME/outputs/seedream/YYYY-MM-DD/
```

脚本输出 JSON。向用户展示本地文件路径、模型、耗时和失败项；不要输出或复述密钥。

`references/EXAMPLES.md` 保留上游图片生成示例；认证、安装和平台配置说明已从内置快照移除。
