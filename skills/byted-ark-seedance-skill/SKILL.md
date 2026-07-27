---
name: byted-ark-seedance-skill
license: MIT
description: 使用火山方舟 Agent Plan 的豆包 Seedance 生成视频，支持文生视频、图生视频、首尾帧、多媒体参考和任务查询。用户明确要求使用 Seedance、豆包或火山方舟生成视频时使用；不要用于图片生成。
compatibility: Requires Node.js 18+, network access, and ARK_AGENT_PLAN_API_KEY configured by Hermes Dock.
metadata:
  author: volcengine/agentplan
  version: "4.0.0-hermes-dock.1"
  category: ai/video-generation
---

# Ark Agent Plan Seedance

本 skill 是火山引擎官方 `byted-ark-seedance-skill` 的 Hermes Dock 内置快照。只使用当前 profile 的 `ARK_AGENT_PLAN_API_KEY`；不要要求用户在对话中发送密钥，也不要传入或保存其他方舟密钥。

## 创建视频

在 skill 根目录执行：

```bash
node scripts/seedance-wrapper.js create \
  --prompt "小猫在草地上奔跑，阳光明媚" \
  --duration 5 \
  --ratio 16:9
```

常用参数：

- `--duration 4..15`
- `--ratio 16:9|9:16|1:1|4:3|3:4|21:9|adaptive`
- `--resolution 480p|720p|1080p|4k`
- `--generate-audio false`
- `--image-file /opt/data/path/to/image.png`，可重复传入
- `--video-file`、`--audio-file`
- `--wait true`：用户明确在线等待时使用
- `--camera-fixed true`
- `--service-tier flex`
- `--draft true`
- `--enable-web-search true`

不要传 `--api-key` 或 `--save-api-key`。缺少密钥时，引导用户在 Hermes Dock 的“火山方舟 Agent Plan”供应商页填写并“应用配置”。

## 任务管理

```bash
node scripts/seedance-wrapper.js get --task-id cgt-xxx
node scripts/seedance-wrapper.js list --filter-status running
node scripts/seedance-wrapper.js delete --task-id cgt-xxx
node scripts/seedance-wrapper.js check-pending
```

产物默认保存到：

```text
$HERMES_DOCK_PROFILE_HOME/outputs/seedance/<task-id>/
```

`references/seedance-model-matrix.json` 保留上游模型能力矩阵；认证和平台配置说明已从内置快照移除。
