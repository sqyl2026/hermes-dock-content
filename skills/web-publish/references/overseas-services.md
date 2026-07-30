# 海外与无账号临时方案

这些方案适合海外访问者、快速预览，或大陆方案暂时不可用时的备用链接。依次尝试可用方案，不必为每次切换都停下来确认。

## 目录

- Pinggy
- Cloudflare Quick Tunnel
- localhost.run
- 静态托管

## Pinggy

容器已有 SSH 时，先选择一个空闲的本地调试端口，默认尝试 `4300`；再用 `mktemp "${HERMES_DOCK_PROFILE_HOME}/tmp/web-publish-pinggy-XXXXXX"` 创建本次专用日志。使用 `process` 启动唯一的 SSH 进程：

```bash
set -o pipefail
ssh \
  -tt \
  -p 443 \
  -o StrictHostKeyChecking=accept-new \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -R 0:127.0.0.1:4173 \
  -L <debugger-port>:localhost:4300 \
  free.pinggy.io \
  2>&1 | tee -a <pinggy-log>
```

`-tt` 强制 SSH 在后台进程环境中分配 PTY，`tee` 保留控制台输出；本地转发提供 Pinggy 官方 URL API。保持该进程运行并获取 URL：

```bash
/opt/hermes/.venv/bin/python \
  "${HERMES_DOCK_PROFILE_HOME}/skills/web-publish/scripts/wait_for_public_url.py" \
  pinggy \
  --api-url http://127.0.0.1:<debugger-port>/urls \
  --log <pinggy-log> \
  --timeout 30
```

用返回的 HTTPS URL 立即验证。不要先启动一次取得 URL，再停止并后台重连；免费隧道每次连接的随机 URL 可能不同。进程退出或重连后，旧 URL 立即作废，重新从当前连接获取并验证。

官方文档：

- `https://pinggy.io/docs/usages/`
- `https://pinggy.io/docs/api/web_debugger_api/`

## Cloudflare Quick Tunnel

已有 `cloudflared` 时，使用 `process` 启动并把输出写入本次专用日志：

```bash
set -o pipefail
cloudflared tunnel --url http://127.0.0.1:4173 \
  2>&1 | tee -a <cloudflared-log>
```

没有客户端时，可把明确版本安装到 `/opt/data/.dock/web-publish-runtime/cloudflared/<version>/` 后继续。使用下面的命令提取 `trycloudflare.com` 地址并验证，保留产生该 URL 的进程：

```bash
/opt/hermes/.venv/bin/python \
  "${HERMES_DOCK_PROFILE_HOME}/skills/web-publish/scripts/wait_for_public_url.py" \
  cloudflare \
  --log <cloudflared-log> \
  --timeout 30
```

官方文档：`https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/`

## localhost.run

前两个方案不可用时，创建本次专用日志并使用 `process` 启动：

```bash
set -o pipefail
ssh \
  -tt \
  -o StrictHostKeyChecking=accept-new \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -R 80:127.0.0.1:4173 \
  nokey@localhost.run \
  2>&1 | tee -a <localhost-run-log>
```

使用下面的命令提取 HTTPS URL 并验证。与 Pinggy 相同，不要取得 URL 后重启 SSH 进程：

```bash
/opt/hermes/.venv/bin/python \
  "${HERMES_DOCK_PROFILE_HOME}/skills/web-publish/scripts/wait_for_public_url.py" \
  localhost-run \
  --log <localhost-run-log> \
  --timeout 30
```

官方文档：`https://localhost.run/docs/`

## 静态托管

用户已有 Cloudflare 或 GitHub 工作流时，可以直接使用对应静态托管。

Cloudflare Pages Direct Upload：

```bash
wrangler pages deploy /opt/data/path/to/dist \
  --project-name <project-name>
```

GitHub Pages 适合已经在 GitHub 管理的公开静态项目。部署完成后请求生产 URL 验证。

这些海外方案在中国大陆的速度和可达性可能波动。先交付已经验证的链接，并请目标访问者实际打开；如果效果不好，再切回大陆方案。

官方文档：

- `https://developers.cloudflare.com/pages/get-started/direct-upload/`
- `https://docs.github.com/pages/getting-started-with-github-pages/what-is-github-pages`
