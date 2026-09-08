# 可选：通过 GHCR 发布和部署镜像

从源码执行 `docker compose up -d --build` 是新用户的默认部署方式，见 [服务器部署与排障指南](../docs/deployment.md)。它不依赖镜像仓库权限。

本页只适合项目维护者，或已经为自己 Fork 配置 GitHub Actions、GitHub Container Registry（GHCR）和镜像访问权限的用户。

## 何时使用 GHCR

GHCR 适合需要在多台服务器重复部署、希望用不可变镜像标签回滚，或由维护者统一发布镜像的场景。它不是首次部署的前置条件。

使用前确认：

- 工作流已在你选择的发布分支上运行，并具有 `packages: write` 权限。
- 镜像包的可见性符合预期；私有包需要具备 `read:packages` 权限的访问令牌才能拉取。
- 服务器已安装 Docker Compose，并仍通过 Nginx/HTTPS 对外提供后台。

## 发布镜像

工作流会生成两类标签：

- `latest`：最近一次成功发布的镜像，不适合作为唯一的回滚依据。
- `sha-<commit>`：与某次提交对应的不可变镜像标签，适合生产部署和回滚。

Fork 项目后，请先审阅 `.github/workflows/publish-image.yml` 中的触发分支、前端基础路径和包权限，再启用自动发布。不要把某个维护者的部署分支、域名或服务器路径当作自己的发布配置。

## 在服务器拉取镜像

私有 GHCR 包需要先登录；令牌只保存在服务器，不要写入仓库、Compose 文件或截图：

```bash
docker login ghcr.io
```

为服务器的 `.env` 增加所需的运行配置，并显式指定镜像，不要依赖示例文件中的默认镜像名：

```dotenv
DOCKER_IMAGE=ghcr.io/<owner>/<repository>:sha-<commit>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=请设置强密码
SESSION_SECRET=请设置至少32位随机字符串
COOKIE_SECURE=true
```

使用 [compose-baota.yml](compose-baota.yml) 或等价的 Compose 配置创建容器。保留以下原则：

- 应用端口只绑定服务器本机；由 Nginx 处理 HTTPS。
- 数据目录必须使用持久化卷；重新创建容器不应删除 `data/`。
- 每次更新后都检查 `/api/v1/system/health`，再登录后台确认总览加载正常。

## 更新与回滚

更新到指定镜像标签：

```bash
docker compose pull
docker compose up -d
```

回滚时，将 `DOCKER_IMAGE` 改为此前已验证可用的 `sha-<commit>` 标签，再执行同样的拉取和重建命令。不要为了回滚删除数据卷、`.env` 或登录态。

## 公开发布前检查

- 镜像中不应包含 `.env`、`data/`、Cookie、二维码、日志或运行截图。
- 维护者应确认 Docker 构建上下文受 `.dockerignore` 保护。
- 发布工作流应先通过后端测试、前端类型检查和构建，再推送镜像。
