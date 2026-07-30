# 海外与无账号临时方案

这些方案适合海外访问者、快速预览，或大陆方案暂时不可用时的备用链接。依次尝试可用方案，不必为每次切换都停下来确认。

## Pinggy

容器已有 SSH 时直接启动：

```bash
ssh \
  -p 443 \
  -o StrictHostKeyChecking=accept-new \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -R 0:127.0.0.1:4173 \
  free.pinggy.io
```

从输出提取 HTTPS URL 并请求验证。免费隧道通常约 60 分钟，重连后 URL 可能变化。

官方文档：`https://pinggy.io/docs/http_tunnels/`

## Cloudflare Quick Tunnel

已有 `cloudflared` 时：

```bash
cloudflared tunnel --url http://127.0.0.1:4173
```

没有客户端时，可把明确版本安装到 `/opt/data/.dock/web-publish-runtime/cloudflared/<version>/` 后继续。提取 `trycloudflare.com` 地址并验证。

官方文档：`https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/`

## localhost.run

前两个方案不可用时：

```bash
ssh \
  -o StrictHostKeyChecking=accept-new \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -R 80:127.0.0.1:4173 \
  nokey@localhost.run
```

提取 HTTPS URL 并验证。

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
