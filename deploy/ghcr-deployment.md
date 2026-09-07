# GHCR + 宝塔部署

生产镜像由 `.github/workflows/publish-image.yml` 在推送 `codex/optimize-login-qr` 分支后构建并推送至：

```text
ghcr.io/youge12388-create/tiktok-fire:latest
```

每次构建同时会生成不可变的 `sha-<commit>` 标签。生产环境默认使用 `latest`；若需要回滚，可将宝塔的 `DOCKER_IMAGE` 改为对应 SHA 标签后重新创建容器。

## 首次切换

1. 在 GitHub Actions 成功发布首个镜像后，为服务器创建一个只具备 `read:packages` 权限的 GitHub fine-grained personal access token。该令牌只保存在服务器，不写入仓库或宝塔编排文件。
2. 在服务器执行一次 `docker login ghcr.io`，用户名为 GitHub 用户名，密码为该令牌。
3. 将 `deploy/compose-baota.yml` 粘贴到宝塔 Docker「容器编排」的现有 `douyin-cloud-streak` 编排中；保持现有 `.env`、`/opt/douyin-cloud-streak/data` 卷和 Nginx 配置不变。
4. 在宝塔中拉取 `ghcr.io/youge12388-create/tiktok-fire:latest`，再重新创建 `douyin-cloud-streak`。确认健康检查通过后，再删除旧的本地构建镜像。

## 日常发布

1. 推送部署分支并确认 GitHub Actions 的 **Publish production image** 成功。
2. 在宝塔的该编排中执行“拉取镜像”并“重新创建”。
3. 检查容器健康状态，并访问 `https://canhuo.site/douyin-fire/`。

## 回滚

不要删除已知可用的 SHA 镜像。将宝塔编排环境变量设为：

```text
DOCKER_IMAGE=ghcr.io/youge12388-create/tiktok-fire:sha-<commit>
```

然后拉取并重新创建容器。数据始终保留在 `/opt/douyin-cloud-streak/data`，不会随着容器重建被删除。
