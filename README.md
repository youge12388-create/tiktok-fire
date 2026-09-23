# 抖音续火花助手

> 把「今天谁还没续上」变成一眼可见的事。

一个自托管的抖音私信续火管理后台：多个账号的登录态、联系人勾选、定时发送、结果核对与失败补发，都集中在一个网页控制台里完成。

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-3776ab.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-2496ed.svg)](compose.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3-42b883.svg)](https://vuejs.org/)

![控制台登录页](docs/images/login.png)

## 这是什么

续火花本身是个很轻的动作，麻烦的是「别漏人」和「别重复发」。用手机手动点，好友一多就容易乱；用现成脚本，又不知道今天到底发给了谁、谁失败了。

这个项目把这件事做成一个有界面的后台：先在网页里勾选要维护的好友，设定每天的执行时间，服务按计划自动发送；跑完给你一份对账结果，明确区分**成功 / 失败 / 待确认 / 跳过 / 未执行**，失败的人可以只补发他一个，不会把已经成功的名单重发一遍。

它面向**自用场景**——一个人、一台服务器、自己的一批好友。没有注册入口，没有多租户，也没有云端服务：所有数据都在你自己的机器上。

## 核心功能

**账号与登录**

- 多账号管理：每个账号的登录态、联系人、任务配置和运行数据彼此隔离，互不干扰。
- 网页扫码登录：在后台直接发起扫码，手机抖音确认即可；支持取消并随时检查登录状态。
- 登录态持久化：登录状态按账号保存到本地，重启服务不用重新扫码。

**联系人与目标**

- 同步聊天联系人列表，支持中断后继续扫描，不必一次跑完。
- 搜索、勾选、全选、清空，自由决定每天维护哪些人。
- 联系人列表直接显示**今日结果**：谁成功了、谁失败了、失败原因是什么。

**发送与调度**

- 定时执行：设定每天的运行时间，可加随机延迟窗口，避免固定时间点过于机械。
- 发送间隔随机化：在区间内随机间隔，降低账号风险。
- 多条候选文案：每次随机选取，避免每天都发同一句。
- 测试运行（Dry Run）：完整走一遍流程但不真正发送消息，正式开启前先用它验证。
- 手动执行与随时停止，同一账号不会并发跑两个任务。

**结果核对与补发**

- 「今日续火核对」按当前勾选名单核对今天的真实发送记录，一眼看清谁没续上。
- 失败名单一键**按人补发**（界面上是「只补发失败/漏发」），只针对失败者，已成功的不重复发送。
- 补发前会再次核对，风控或登录失效时不会自动重试，交给人工处理。
- Dry Run 记录不参与核对，避免演练被误判成成功。

**运维与告警**

- 执行记录：可筛选、分页、查看明细，指标卡片可直接下钻到对应记录。
- 关键错误自动截图，仅登录后可读，方便事后定位。
- 账号掉线告警：接入钉钉机器人（支持加签），可在后台「系统信息」页直接配置，密钥只写入数据卷、接口不回显明文。
- 健康检查接口，便于容器编排判断服务是否就绪。

## 界面预览

| 总览 | 账号管理 |
| --- | --- |
| ![总览：执行统计、账号状态和最近记录](docs/images/dashboard.png) | ![账号管理：账号列表和扫码登录入口](docs/images/accounts.png) |

| 联系人管理 | 任务配置 |
| --- | --- |
| ![联系人：同步、选择和清理联系人](docs/images/contacts.png) | ![任务：执行时间、随机延迟和消息内容](docs/images/tasks.png) |

> 以上截图来自隔离演示环境，不包含真实账号、联系人、二维码或登录态。

## 快速开始（Docker，推荐）

需要先装好 **Git**、**Docker Engine** 和 **Docker Compose v2**。

### 1. 克隆并创建配置

```bash
git clone https://github.com/youge12388-create/tiktok-fire.git
cd tiktok-fire
cp .env.example .env
```

Windows PowerShell 用户把最后一行换成：

```powershell
Copy-Item .env.example .env
```

### 2. 填写两个必填项

打开 `.env`，**下面两项不填服务会拒绝启动**（这是防止弱口令的刻意设计）：

```dotenv
ADMIN_PASSWORD=你的管理员密码
SESSION_SECRET=至少32位的随机字符串
```

生成一个随机密钥：

```bash
# Linux / macOS
openssl rand -hex 32
```

```powershell
# Windows PowerShell
-join ((1..64) | ForEach-Object { '{0:x}' -f (Get-Random -Max 16) })
```

密码不能使用 `admin`、`123456`、`password` 这类弱口令。本机用 HTTP 访问时保持 `COOKIE_SECURE=false`，配好 HTTPS 后再改成 `true`。

### 3. 构建并启动

```bash
docker compose up -d --build
```

> 首次构建会下载 Python、Node.js 和 Playwright Chromium 浏览器，**通常需要几分钟**，取决于网络环境。请勿中途关闭终端。

### 4. 打开控制台

```bash
curl http://127.0.0.1:8011/api/v1/system/health
```

看到 `"ok": true` 且 `database`、`scheduler` 都为 `true` 后，在浏览器打开：

```text
http://127.0.0.1:8011
```

用刚写入 `.env` 的账号密码登录。

### 5. 完成首次设置

按这个顺序走一遍，**最后一步先点「测试运行」验证**：

```text
账号管理 → 扫码登录 → 联系人 → 同步并勾选 → 任务配置 → 测试运行 → 开启自动执行
```

服务默认只绑定本机 `127.0.0.1`，不会直接暴露到公网。需要在服务器上对外提供访问，请继续看下一节。

## Windows 本机运行（不想用 Docker）

仓库自带几个双击即用的脚本，适合在自己电脑上跑：

| 脚本 | 用途 |
| --- | --- |
| `1.本地提取通行证.bat` | 打开浏览器扫码登录，生成登录凭证（会自动装依赖和 Chromium） |
| `2.桌面端立即运行.bat` | 选择正式发送 / 演练模式 / 仅同步联系人 |
| `4.同步登录态到服务器.bat` | 登录态过期后，把新凭证同步到服务器 |
| `5.一键部署整站到服务器.bat` | 打包整站并上传到服务器完成部署 |

首次使用请从脚本 `1` 开始。没有 Python 环境也没关系，脚本会引导你安装。

## 部署到服务器

生产环境请通过 Nginx 反向代理以 HTTPS 对外提供，**不要直接把应用端口暴露到公网**。

- [服务器部署与排障指南](docs/deployment.md)：从拉取源码、配置 HTTPS、升级到回滚的完整流程。
- [Nginx 根路径示例](deploy/nginx-example.conf) 与 [子路径示例](deploy/nginx-subpath-example.conf)：按自己的域名和证书路径修改后使用。
- [Linux 一键安装脚本](deploy/deploy.sh)：以 systemd 方式部署到 Linux 服务器。
- [可选的 GHCR 镜像发布说明](deploy/ghcr-deployment.md)：面向项目维护者，或希望自行维护 GitHub Actions 与镜像仓库的用户。
- [宝塔面板 Compose 示例](deploy/compose-baota.yml)：使用宝塔「Docker → 容器编排」时可直接参考。

## 常见问题

**服务启动后立刻退出，或日志提示配置有问题**

优先看日志：

```bash
docker compose logs --tail=100 douyin-cloud-streak
```

最常见的原因是 `.env` 里没填 `ADMIN_PASSWORD`、密码过弱，或 `SESSION_SECRET` 少于 32 位。应用检测到不安全配置会主动拒绝启动。

**打开 8000 端口没有反应**

Docker 部署时，容器内部监听 `8000`，映射到宿主机的 `8011`。请访问 <http://127.0.0.1:8011>。直接跑 `app.py`（不走 Docker）时才是 `8000`。

**首次构建特别慢**

需要下载 Playwright Chromium 及其系统依赖，这一步无法跳过。构建完成后再次启动会很快。

**扫码登录后仍显示未登录**

可能是登录态已过期。回到「账号管理」重新扫码即可；如果服务部署在服务器上，也可以用脚本 `4` 把本机新提取的凭证同步上去。

**页面样式丢失或静态资源 404**

多半是子路径部署时路径没对齐。应用的 `PUBLIC_BASE_PATH`、Nginx 的 `location` 前缀、以及前端构建路径三者必须完全一致，改完重新执行 `docker compose up -d --build`。

**数据存在哪里？怎么备份？**

全部在 `data/` 目录（Docker 部署时映射到宿主机同目录）。登录态、联系人、任务配置、执行记录、告警密钥都在这里。备份就是备份这个目录，升级时也不要删除它。

**怎么升级？**

```bash
git pull --ff-only
docker compose up -d --build
curl http://127.0.0.1:8011/api/v1/system/health
```

`.env` 和 `data/` 会被保留。回滚方式见 [部署指南](docs/deployment.md)。

## 安全与隐私

- **凭证不出本机**：登录凭证等同于账号密码，只保存在 `data/` 目录，`.gitignore` 已排除，不会被提交。
- **强制强口令**：不设置强密码和随机会话密钥，服务不会启动。
- **默认不暴露公网**：容器只绑定 `127.0.0.1`，由 Nginx 处理 HTTPS。
- **密钥不回显**：告警 Webhook 与加签密钥存入数据卷后，任何接口都不返回明文，日志中也不会出现。
- **截图受保护**：异常截图仅认证后的请求可读。

如果你发现了安全漏洞或潜在的隐私泄露风险，请不要公开创建 Issue，按 [SECURITY.md](SECURITY.md) 的方式联系维护者。

## 使用边界

本项目依赖抖音网页端、登录状态和平台风控策略，**外部平台的任何异常都需要人工确认**。

- 请仅用于维护你自己的账号与好友关系，不要用于批量营销、违规引流或骚扰他人。
- 本项目不提供绕过验证码、人脸校验或平台安全策略的能力。
- 请合理控制每日发送人数、保留随机间隔，以降低账号风险。
- 首次使用、账号异常或平台页面改版后，请先用小号执行 Dry Run，确认无误再恢复自动任务。
- 因使用本项目导致的账号异常、数据丢失或法律纠纷，由使用者自行承担。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.11 · FastAPI · Uvicorn · APScheduler |
| 浏览器自动化 | Playwright（Chromium） |
| 前端 | Vue 3 · Vite · Element Plus · Pinia · Vue Router |
| 数据库 | SQLite |
| 部署 | Docker · Docker Compose · Nginx · systemd |

## 项目结构

| 路径 | 说明 |
| --- | --- |
| `app.py` | FastAPI 应用入口、生命周期和静态页面服务 |
| `api/` | 认证、账号、联系人、任务、运行记录和系统接口 |
| `services/` | 业务编排、任务运行与状态管理 |
| `core/` | 浏览器自动化、登录会话、调度和联系人台账 |
| `db/` | SQLite 初始化与运行记录仓储 |
| `frontend/` | Vue 3 管理后台 |
| `deploy/` | Nginx、Compose、systemd 与 GHCR 部署辅助文件 |
| `docs/` | 部署指南与界面截图 |
| `tests/` | 后端回归测试 |

## 本地开发

后端：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

前端（另开一个终端）：

```powershell
Set-Location frontend
npm install
npm run dev
```

浏览器打开 <http://127.0.0.1:5173>，开发服务器会把 `/api` 代理到后端 `127.0.0.1:8000`。

## 贡献与测试

提交改动前请确保以下检查通过：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall app.py api core db services
Set-Location frontend
npm run typecheck
npm run build
```

> 注意：`npm run typecheck`（`tsc --noEmit`）不会检查 `.vue` 文件，前端改动务必跑一次 `npm run build`。

欢迎提交 Issue 反馈问题或建议。涉及安全问题的，请改用 [SECURITY.md](SECURITY.md) 中的私下渠道。

## 许可证

[MIT](LICENSE)
