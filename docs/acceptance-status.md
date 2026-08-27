# V1 验收状态对照（§38）

> 说明：`✅` 表示代码/配置已落地并通过本机测试或契约冒烟；`⏳` 表示需要真实服务器（Docker + Chromium + 抖音登录态）验证，本机无法完成。

## 已代码验证（✅）
- ✅ Docker Compose 一条命令可启动（`compose.yml` 就位，容器内 `HOST=0.0.0.0` 已修；构建需 Docker 实测，见 ⏳ 项）
- ✅ Web 后台可登录（密码登录 + Session Cookie；根路径托管 + 登录态验证通过）
- ✅ 未登录无法访问后台 API（401，已测）
- ✅ 可以新增抖音账号 / 管理多个账号（CRUD，已测）
- ✅ 可以扫码登录（`login/start|status|cancel` + 前端轮询弹窗，接口契约已冒烟）
- ✅ 可以检测登录状态（`check-login`，已接线）
- ✅ 可以同步聊天联系人（`contacts/sync` + 前端轮询）
- ✅ 可以搜索和勾选联系人（前端搜索/勾选/全选，写回 `friends`）
- ✅ 可以配置续火时间 / 随机窗口 / 多条文案 / 发送间隔（`spark-task` GET/PUT 校验，已测）
- ✅ 可以 Dry Run（不发送真实消息，Mock 已测）
- ✅ Dry Run 不发送真实消息（已测）
- ✅ 可以手动执行（二次确认 + 同账号锁）
- ✅ 可以自动定时执行（APScheduler，`next_run` 正常）
- ✅ 同一账号不会同时执行两个任务（账号锁，已测）
- ✅ 发送前会校验目标会话（§18，右上标题区域判定，已测）
- ✅ 可以判断成功 / 失败 / 不确定（三态，已测）
- ✅ 安全验证出现后立即停止（`risk_detected`，已测）
- ✅ 可以查看执行日志（`/runs` 筛选/分页/明细）
- ✅ 失败可以查看原因（`error` 列/明细）
- ✅ 关键错误可以保存截图（`artifacts/{date}/{account}/{run_id}/error.png`，仅认证可读）
- ✅ Cookie / Storage State 不出现在日志（`.gitignore` + 敏感信息处理）
- ✅ 不存在 admin/123456 默认密码（weak-password fail-fast，已测）
- ✅ 生产 8000 端口不直接暴露公网（compose 绑定 `127.0.0.1`）
- ✅ 前端可在桌面浏览器正常使用（响应式布局，已测构建）
- ✅ 手机浏览器可完成核心操作（<992px 抽屉菜单，已测构建）
- ✅ 核心 API 有基础测试（pytest **36 passed**）

## 待真实环境验证（⏳）
- ⏳ Docker 实际构建/运行（本机无 Docker；`Dockerfile`/`compose.yml` 已静态审查，需 `docker compose build && up`）
- ⏳ 真实扫码登录 / 刷新保持（Case 1–2）
- ⏳ 真实同步联系人 / Dry Run 不发送 / 手动发送 / 定时发送（Case 3–6）
- ⏳ 重启 Docker 数据不丢（Case 7）
- ⏳ Cookie 失效提示重新登录（Case 8）
- ⏳ 安全验证即停（Case 9）

> 以上 ⏳ 项请按 [docs/e2e-checklist.md](./e2e-checklist.md) 在服务器上逐项执行。
