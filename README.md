# Hermes Dock Content

Hermes Dock 的官方内置人格与技能内容仓库。

`main` 分支是生产发布渠道。Hermes Dock 使用最新 commit SHA 识别版本，并按该 SHA 下载完整仓库快照。

仓库只维护以下内容：

```text
SOUL.md
skills/
```

提交到 `main` 前，应确认内容可以直接同步给 Hermes Dock 用户。

技能目录保持可频繁同步的轻量内容，不提交 `node_modules`、虚拟环境或可按需安装的大模型和运行依赖。此类依赖由技能包装脚本在首次使用时安装到 Hermes Dock 的 `data/.dock/` 派生运行时目录，并通过版本与 lockfile 固定。

## 同步到 Hermes Dock

每次 commit 推送到 `main` 时，`.github/workflows/sync-hermes-dock.yml` 会：

1. 检出触发 workflow 的内容 commit。
2. 运行内容工具测试，并拒绝 OCR 模型、`node_modules` 或压缩后超过 10 MiB 的内置内容。
3. 更新 `sqyl2026/hermes-dock` 的 `templates/seed-data/SOUL.md` 和 `templates/seed-data/skills/`。
4. 将来源 SHA 写入 `templates/seed-data/.content-commit`。
5. 使用 `chore(content): sync bundled content to <sha>` 直接提交并推送到 Hermes Dock `main`。

内容仓库需要配置 Actions Secret：

```text
HERMES_DOCK_SYNC_TOKEN
```

建议使用 fine-grained personal access token，只授权 `sqyl2026/hermes-dock`，并只开放 `Contents: Read and write`。如果 Hermes Dock 的 `main` 有分支保护，还需要允许该 Token 所属账号直接推送。
