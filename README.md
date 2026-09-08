# 抖音续火花助手

一个面向自用场景的抖音私信续火管理后台。通过网页控制台管理多个账号、同步联系人、配置定时任务，并查看每次执行的结果与异常状态。

> 本项目依赖抖音网页端的实际页面、登录状态和风控策略。请先用小号完成 Dry Run，再决定是否启用自动任务；不要把它用于违反平台规则或干扰他人的场景。

## 界面预览

### 控制台登录

![登录页：控制台登录与功能概览](docs/images/login.png)

### 总览与账号管理

| 总览 | 多账号管理 |
| --- | --- |
| ![总览页：执行统计、账号状态与最近记录](docs/images/dashboard.png) | ![账号管理页：账号列表与扫码登录入口](docs/images/accounts.png) |

### 联系人与任务配置

| 联系人管理 | 任务配置 |
| --- | --- |
| ![联系人页：同步、选择与清理联系人](docs/images/contacts.png) | ![任务配置页：发送时间、随机延迟与消息内容](docs/images/tasks.png) |

截图来自本地隔离演示环境，不含真实账号、联系人、二维码或登录态。

## 功能

- 多账号管理：每个账号独立保存登录态、联系人、任务配置和运行数据；支持新增、启停与删除非默认账号。
- 网页扫码登录：在账号页发起、查询或取消扫码会话，并检查当前登录状态。
- 联系人闭环：同步联系人、补充未完成的扫描、选择发送目标，以及清理部分或全部联系人。
- 任务控制：配置每日执行时间、随机延迟、发送间隔、单次上限和候选消息；支持 Dry Run、立即执行、停止与自动执行开关。
- 运行可观测：记录运行历史和明细，任务产物可按记录查看；总览展示当天统计、账号状态与最近执行结果。
- 安全与可靠性：管理员会话认证、登录限流、CSRF 防护、健康检查、SQLite 持久化及账号级运行互斥。

## 技术栈

- 后端：Python、FastAPI、APScheduler、Playwright、SQLite
- 前端：Vue 3、Vite、TypeScript、Element Plus、Pinia
- 部署：Docker、Nginx、GitHub Container Registry（GHCR）

## 本地启动

### 1. 配置环境

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，至少设置以下值：

```dotenv
ADMIN_USERNAME=admin
ADMIN_PASSWORD=请使用强密码
SESSION_SECRET=请填写至少32位随机字符串
COOKIE_SECURE=false
```

生产 HTTPS 环境应设置 `COOKIE_SECURE=true`。`.env`、`data/` 和登录态均为私密数据，不能提交到仓库。

### 2. 启动后端

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

后端默认运行于 `http://127.0.0.1:8000`。

### 3. 启动前端开发服务器

另开一个终端：

```powershell
Set-Location frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`，前端会将 `/api` 请求代理到本地后端。

## 使用流程

1. 使用 `.env` 中的管理员凭证登录控制台。
2. 在“账号管理”中选择默认账号或新建账号，完成扫码登录并确认登录状态。
3. 在“联系人”中同步列表，确认后选择需要维护的联系人。
4. 在“任务配置”中设置发送时间、间隔和消息内容，先执行 Dry Run 检查结果。
5. 确认无误后开启自动执行；在“执行记录”和总览持续关注结果，登录失效或异常时停止任务并人工处理。

## 部署

生产部署使用 GHCR 镜像、Docker 与 Nginx HTTPS。应用端口应仅绑定服务器本机，由 Nginx 对外提供 HTTPS；不要直接暴露应用端口。

具体的镜像发布、宝塔容器编排、Nginx 配置和更新流程见 [部署说明](deploy/ghcr-deployment.md)。如需部署在既有站点的子路径下，请同时配置 `PUBLIC_BASE_PATH`、独立的 `SESSION_COOKIE_NAME` 以及 `COOKIE_SECURE=true`。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall app.py api core db services
Set-Location frontend
npm run typecheck
npm run build
```

## 目录说明

| 路径 | 职责 |
| --- | --- |
| `app.py` | FastAPI 应用入口、生命周期与静态资源挂载 |
| `api/` | 认证、账号、联系人、任务、运行记录和系统接口 |
| `services/` | 业务编排、任务运行与状态管理 |
| `core/` | 浏览器自动化、登录会话、调度、联系人台账等核心能力 |
| `db/` | SQLite 初始化与运行记录仓储 |
| `frontend/` | Vue 3 管理后台 |
| `deploy/` | 容器、Nginx 与生产部署文档 |
| `tests/` | 后端回归测试 |

## 使用边界

- 抖音页面结构、登录 Cookie 生命周期和风控规则均可能变化；请将外部平台异常视为需要人工确认的信号。
- 不保存或上传真实账号密码、Cookie、二维码、联系人或运行日志到公开仓库。
- 本项目不提供绕过验证码、人脸校验或平台安全策略的能力。
