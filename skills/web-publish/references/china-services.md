# 中国大陆发布方案

根据内容类型直接选择方案，并持续推进到拿到可验证的 URL。

## 目录

- cpolar：临时网页和动态服务
- NATAPP：已有免费隧道时使用
- EdgeOne Makers：中国大陆静态网站
- 失败时继续

## cpolar：临时网页和动态服务

1. 确认服务已在 `127.0.0.1:<port>` 可访问。
2. 复用已有 `cpolar`；没有时，从 `https://www.cpolar.com/download` 下载匹配容器架构的明确版本，放到 `/opt/data/.dock/web-publish-runtime/cpolar/<version>/`。
3. 如果缺少认证，直接把下面这段申请说明发到当前聊天，并把链接做成可点击链接：

   > 请用手机打开 cpolar 免费注册页面：`https://dashboard.cpolar.com/signup`。注册并登录后，进入后台左侧的“验证”，点击复制 Authtoken，然后把复制到的整段 Token 直接发给我。后面的安装、配置和发布都由我完成，不需要操作电脑或命令行。

4. 收到 Token 后不要重复展示。使用 `process` 启动脚本并通过标准输入发送 Token，生成临时配置。默认使用本地 API 端口 `4040`；端口已占用时选择其他空闲端口并增加 `--web-port <port>`：

   ```bash
   /opt/hermes/.venv/bin/python \
     "${HERMES_DOCK_PROFILE_HOME}/skills/web-publish/scripts/write_tunnel_config.py" \
     cpolar \
     --token-stdin
   ```

   将用户发来的 Token 写入该进程的标准输入并发送换行。脚本只输出临时配置路径。

5. 记录脚本输出的 `<config-path>`。配置已启用 cpolar 控制台 UI、本地 API 和独立客户端日志。使用 `process` 启动唯一的隧道进程，并把控制台输出同时写入日志：

   ```bash
   set -o pipefail
   env -u CPOLAR_AUTHTOKEN \
     /opt/data/.dock/web-publish-runtime/cpolar/<version>/cpolar \
     http \
     -config=<config-path> \
     4173 \
     2>&1 | tee -a <config-path>.console.log
   ```

6. 在隧道进程保持运行时等待 URL。`<web-port>` 必须与生成配置时一致：

   ```bash
   /opt/hermes/.venv/bin/python \
     "${HERMES_DOCK_PROFILE_HOME}/skills/web-publish/scripts/wait_for_public_url.py" \
     cpolar \
     --api-url http://127.0.0.1:<web-port>/api/tunnels \
     --log <config-path>.console.log \
     --log <config-path>.client.log \
     --timeout 30
   ```

   脚本优先读取本地 API，API 不可用时从两份日志提取 HTTPS 地址。取得 URL 后直接请求验证，不要停止并重启 cpolar。超时则检查该进程是否仍存活及两份日志；确认没有进展后终止它并切换方案。上线后可删除临时配置，保留日志、本地服务和隧道进程。

免费随机地址会变化，适合预览、联调、Webhook 和短期分享。需要固定域名时再讨论套餐或正式部署。

官方资料：`https://www.cpolar.com/docs`

## NATAPP：已有免费隧道时使用

用户已经有 NATAPP 免费 Web 隧道时，这通常是最快的备用方案。

1. 在 NATAPP 控制台把目标设置为当前容器的 `127.0.0.1:<port>`。
2. 复用已有客户端；没有时从 `https://natapp.cn/download` 下载明确版本到 `/opt/data/.dock/web-publish-runtime/natapp/<version>/`。
3. 缺少 Token 时，把下面的说明发到当前聊天，其中 `<port>` 换成当前服务的真实端口：

   > 请用手机打开 NATAPP 注册页面：`https://natapp.cn/register`。注册并登录后，点击“购买隧道”，选择“免费隧道”和“Web”协议，本地地址填写 `127.0.0.1`，本地端口填写 `<port>`。创建完成后进入“我的隧道”，复制 Authtoken，直接发给我。后面的配置和发布都由我完成。

4. 收到 Token 后，通过标准输入生成配置：

   ```bash
   /opt/hermes/.venv/bin/python \
     "${HERMES_DOCK_PROFILE_HOME}/skills/web-publish/scripts/write_tunnel_config.py" \
     natapp \
     --token-stdin
   ```

   将 Token 写入该进程的标准输入并发送换行，然后使用输出的配置路径启动：

   ```bash
   env -u NATAPP_AUTHTOKEN \
     /opt/data/.dock/web-publish-runtime/natapp/<version>/natapp \
     -config=/opt/data/path/to/generated-natapp.ini
   ```

5. 提取公网地址并验证。如果当前免费隧道只有 HTTP，如实告诉用户即可。

官方资料：`https://natapp.cn/article/natapp_newbie`

## EdgeOne Makers：中国大陆静态网站

适合静态网站、SPA 和前端构建产物。

1. 使用明确版本安装 CLI：

   ```bash
   pnpm add \
     --dir /opt/data/.dock/web-publish-runtime/edgeone/<version> \
     edgeone@<version>
   ```

2. 优先使用中国站浏览器登录：

   ```bash
   PAGES_SOURCE=skills \
     /opt/data/.dock/web-publish-runtime/edgeone/<version>/node_modules/.bin/edgeone \
     login \
     --site china
   ```

   CLI 给出登录地址后，直接把可点击链接发到当前聊天。用户可以用手机浏览器完成登录授权，不要求他在宿主机旁。

   如果浏览器登录不方便，发送下面的小白指引：

   > 请用手机打开 EdgeOne Makers 控制台：`https://console.cloud.tencent.com/edgeone/pages?tab=settings`。登录腾讯云后进入“API Token”页，点击“创建 API Token”，描述可以填写“企智盒网页发布”，选择有效期并提交。创建后复制 Token，直接发给我，我会完成后面的部署。

3. 部署生产构建目录：

   ```bash
   PAGES_SOURCE=skills \
     /opt/data/.dock/web-publish-runtime/edgeone/<version>/node_modules/.bin/edgeone \
     makers deploy /opt/data/path/to/dist \
     -n <project-name>
   ```

   用户在聊天中发来 Token 时，不要要求他另行配置环境变量。用临时进程环境调用 CLI，增加 `-t "$EDGEONE_API_TOKEN"`，不要在回复里重复 Token。完整保留 CLI 返回的 URL，包括查询参数。

4. 请求部署 URL 验证页面和静态资源后交付。

预览域名可以先用于交付，不要因为用户暂时没有备案域名而放弃部署。需要长期稳定的大陆自定义域名时，再提示用户绑定已备案域名。

官方资料：`https://pages.edgeone.ai/document/edgeone-cli`

## 失败时继续

- cpolar 客户端或线路不可用：尝试用户已有的 NATAPP。
- 动态服务暂时无法建立大陆隧道：说明情况后可提供 Pinggy 或 Cloudflare Quick Tunnel 临时链接。
- EdgeOne 登录受阻：保留已验证的本地构建结果，给出唯一需要用户完成的登录动作，完成后继续部署。
- 不确定免费额度或域名规则：交付当前可用的临时链接，并把不确定性简短说明，不要因此停止整个任务。
