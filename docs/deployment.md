# 服务器部署与排障指南

本指南面向第一次把项目部署到 Linux 服务器的用户。目标是完成一条可验证的路径：从 GitHub 拉取源码、构建容器、配置 HTTPS、登录后台并安全地升级或回滚。

> 默认部署只监听服务器本机 `127.0.0.1:8011`。这是有意的安全设计：管理后台应通过 Nginx 或同类反向代理以 HTTPS 对外提供，而不是直接暴露应用端口。

## 开始前

准备一台已安装 Git、Docker Engine 和 Docker Compose v2 的 Linux 服务器。建议提前准备域名和 HTTPS 证书；如果暂时没有域名，也可以先在服务器本机完成健康检查，但不要把 `8011` 端口开放到公网。

以下命令以项目目录 `/opt/tiktok-fire` 为例；可替换为自己的目录。

## 1. 拉取源码并创建配置

```bash
git clone https://github.com/youge12388-create/tiktok-fire.git /opt/tiktok-fire
cd /opt/tiktok-fire
cp .env.example .env
```

编辑 `.env`，至少设置：

```dotenv
ADMIN_USERNAME=admin
ADMIN_PASSWORD=请设置强密码
SESSION_SECRET=请设置至少32位随机字符串
COOKIE_SECURE=false
```

配置文件、`data/` 目录、浏览器登录态和二维码都属于私密数据。不要将它们提交到 Git、上传到问题帖，或发送给不可信的人。

## 2. 首次构建与启动

```bash
docker compose up -d --build
docker compose ps
```

首次构建需要下载运行依赖和 Chromium 浏览器，等待时间通常比后续升级更长。若命令失败，先查看完整日志：

```bash
docker compose logs --tail=200 douyin-cloud-streak
```

## 3. 验证后端健康状态

在服务器中执行：

```bash
curl http://127.0.0.1:8011/api/v1/system/health
```

成功时响应中应有 `"ok": true`，并且 `database`、`scheduler` 都为 `true`。容器状态与健康检查也可通过以下命令查看：

```bash
docker compose ps
```

若健康检查未通过，不要继续配置外网访问；先按本文的“常见问题”排查。

## 4. 配置 Nginx 与 HTTPS

项目提供根路径反向代理模板：[nginx-example.conf](../deploy/nginx-example.conf)。复制它到 Nginx 的站点配置目录后：

1. 把 `your-domain.com` 替换为自己的域名。
2. 把证书和私钥路径替换为自己的 HTTPS 证书路径。
3. 保持 `proxy_pass http://127.0.0.1:8011;` 不变。
4. 检查并重载 Nginx：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

确认能通过 `https://你的域名/` 打开登录页后，将 `.env` 中的 `COOKIE_SECURE` 改为 `true`，再重建应用：

```bash
docker compose up -d --build
```

如果要部署到既有网站的子路径，请使用 [nginx-subpath-example.conf](../deploy/nginx-subpath-example.conf)，并在 `.env` 中同步设置 `PUBLIC_BASE_PATH`、独立的 `SESSION_COOKIE_NAME` 和 `COOKIE_SECURE=true`。前端路径与反代路径不一致会导致页面资源加载失败。

## 5. 完成首次设置

1. 打开 HTTPS 域名，以 `.env` 中的管理员账号登录。
2. 在“账号管理”中完成扫码登录，并确认账号状态。
3. 在“联系人”中同步并选择目标。
4. 在“任务配置”中设置时间和消息；第一次先运行 Dry Run。
5. 仅在 Dry Run 结果符合预期后，再开启自动执行。

扫码、联系人同步和发送结果受抖音页面、Cookie 和风控影响，不能由部署成功替代验证。建议始终先用小号验证。

## 升级

```bash
cd /opt/tiktok-fire
git pull --ff-only
docker compose up -d --build
curl http://127.0.0.1:8011/api/v1/system/health
```

升级时保留 `.env` 和 `data/` 目录。不要执行会删除数据卷或数据目录的 Docker 清理命令。

## 回滚

先找到上一个可用提交：

```bash
git log --oneline -10
```

记录目标提交号后，在维护窗口内切换并重新构建：

```bash
git checkout <已验证可用的提交号>
docker compose up -d --build
curl http://127.0.0.1:8011/api/v1/system/health
```

回滚只替换应用代码和镜像，不应删除 `.env` 或 `data/`。回滚后建议重新跑一次 Dry Run。

## 常见问题

### 容器启动后立刻退出

优先运行 `docker compose logs --tail=200 douyin-cloud-streak`。常见原因是 `.env` 中未设置 `ADMIN_PASSWORD`、密码过弱，或 `SESSION_SECRET` 少于 32 位；应用会主动拒绝以不安全配置启动。

### 健康检查返回 503

说明进程还未达到就绪状态，或数据库、调度器初始化失败。等待首次启动完成后重试；若持续失败，保留日志并检查容器是否反复重启。

### 域名能打开但无法登录

确认 Nginx 转发到 `127.0.0.1:8011`，并检查 `COOKIE_SECURE` 是否与实际访问协议一致：HTTP 使用 `false`，已经配置 HTTPS 后使用 `true`。

### 页面样式丢失或资源 404

根路径部署时保持 `PUBLIC_BASE_PATH` 为空。子路径部署时，应用的 `PUBLIC_BASE_PATH`、Nginx 的 location 和构建后的前端路径必须完全一致；修改后重新执行 `docker compose up -d --build`。

### 如何查看运行日志

```bash
docker compose logs -f douyin-cloud-streak
```

网页中的“执行记录”用于查看业务执行结果；容器日志用于排查应用启动、浏览器自动化和基础设施问题。
