---
name: byted-web-search
version: 1.3.8-hermes-dock.1
author: volcengine-search-team
description: 使用火山方舟 Agent Plan 的豆包搜索获取网页或图片搜索结果。用户明确要求豆包搜索、火山方舟搜索，或当前 profile 已配置 Agent Plan 且任务需要时效性事实、来源核验、最新信息时使用。
homepage: https://www.volcengine.com/docs/87772/2272953
---

# 豆包搜索

本 skill 是火山引擎官方 `byted-web-search` 的 Hermes Dock 内置快照。认证方式以本文件为准：只读取当前 profile 的 `ARK_AGENT_PLAN_API_KEY`，不要要求用户在对话中发送密钥，也不要从 OpenClaw、AK/SK 或其他环境变量读取凭证。

## 使用

在 skill 根目录执行：

```bash
python3 scripts/web_search.py "搜索词"
```

可选参数：

- `--type web|image`
- `--count 10`：网页最多 50 条，图片最多 5 条
- `--time-range OneDay|OneWeek|OneMonth|OneYear|YYYY-MM-DD..YYYY-MM-DD`
- `--auth-level 1`：只取权威来源
- `--query-rewrite`

涉及争议或重要事实时，用不同关键词搜索两次并交叉验证。回答应给出来源链接；结果不足时明确说明，不要编造。

缺少密钥或鉴权失败时，引导用户在 Hermes Dock 的“火山方舟 Agent Plan”供应商页填写正确密钥并“应用配置”。不要传 `--api-key`，不要建议安装 Python 依赖；Hermes 镜像已提供运行依赖。

上游关于独立搜索 Key、AK/SK、OpenClaw 和聊天框传密钥的资料已从 Hermes Dock 内置快照移除。
