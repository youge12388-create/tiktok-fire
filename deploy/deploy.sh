#!/usr/bin/env bash
set -euo pipefail

echo "======================================================"
echo "    🔥 抖音云端自动续火花助手 · Linux 一键安装部署"
echo "======================================================"

if [ "$(id -u)" -ne 0 ]; then
  echo "[错误] 请以 root 用户运行：sudo bash deploy/deploy.sh"
  exit 1
fi

SERVICE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$SERVICE_DIR/.venv"
UNIT_SRC="$SERVICE_DIR/deploy/douyin-cloud-streak.service"
UNIT_DST="/etc/systemd/system/douyin-cloud-streak.service"

echo "==> 1. 安装系统依赖..."
if command -v apt-get &>/dev/null; then
    apt-get update -y
    apt-get install -y python3 python3-venv python3-pip xvfb libnss3 libnspr4 libasound2 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2t64 2>/dev/null || apt-get install -y python3 python3-venv python3-pip xvfb
elif command -v dnf &>/dev/null; then
    dnf install -y python3 python3-pip
elif command -v yum &>/dev/null; then
    yum install -y python3 python3-pip
fi

echo "==> 2. 创建 Python 虚拟环境..."
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi

echo "==> 3. 安装 Python 依赖..."
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$SERVICE_DIR/requirements.txt"

echo "==> 4. 安装 Playwright Chromium 浏览器内核与依赖..."
"$VENV/bin/playwright" install --with-deps chromium || "$VENV/bin/playwright" install chromium

echo "==> 5. 检查并配置 4G 交换空间 (Swap，防止小内存服务器被系统 OOM 崩溃)..."
if ! swapon --show | grep -q 'swap'; then
  fallocate -l 4G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=4096
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "[✓] 4G Swap 已成功创建并启用"
else
  echo "[✓] 检测到已有 Swap 空间，跳过"
fi

echo "==> 6. 设置时区为 Asia/Shanghai..."
timedatectl set-timezone Asia/Shanghai 2>/dev/null || true

echo "==> 7. 配置管理员登录与会话密钥..."
generate_secret() {
  # 十六进制格式可直接安全写入 dotenv 文件，且有 64 位随机字符。
  head -c 48 /dev/urandom | sha256sum | cut -d ' ' -f 1
}

GENERATED_ADMIN_PASSWORD=""
if [ ! -f "$SERVICE_DIR/.env" ]; then
  GENERATED_ADMIN_PASSWORD="$(generate_secret)"
  SESSION_SECRET_VALUE="$(generate_secret)"
  (
    umask 077
    cat > "$SERVICE_DIR/.env" <<EOF
ADMIN_USERNAME=admin
ADMIN_PASSWORD=$GENERATED_ADMIN_PASSWORD
SESSION_SECRET=$SESSION_SECRET_VALUE
PORT=8000
HOST=127.0.0.1
TZ=Asia/Shanghai
COOKIE_SECURE=true
EOF
  )
fi

chmod 600 "$SERVICE_DIR/.env"

if ! grep -q '^ADMIN_USERNAME=.' "$SERVICE_DIR/.env"; then
  printf '\nADMIN_USERNAME=admin\n' >> "$SERVICE_DIR/.env"
fi
if ! grep -q '^ADMIN_PASSWORD=.' "$SERVICE_DIR/.env"; then
  GENERATED_ADMIN_PASSWORD="$(generate_secret)"
  printf '\nADMIN_PASSWORD=%s\n' "$GENERATED_ADMIN_PASSWORD" >> "$SERVICE_DIR/.env"
fi
if ! grep -q '^SESSION_SECRET=.' "$SERVICE_DIR/.env"; then
  printf '\nSESSION_SECRET=%s\n' "$(generate_secret)" >> "$SERVICE_DIR/.env"
fi

if ! "$VENV/bin/python" -c 'from app_config import security_problems; import sys; problems = security_problems(); print("\\n".join(problems)); sys.exit(bool(problems))'; then
  echo "[错误] .env 未通过安全校验；请修正上方问题后重新运行部署脚本。"
  exit 1
fi

echo "==> 8. 注册并启动 systemd 开机自启服务..."
systemctl stop douyin-spark 2>/dev/null || true
systemctl disable douyin-spark 2>/dev/null || true
systemctl stop douyin-cloud-streak 2>/dev/null || true
# 不再用 pkill/fuser 强制杀掉整台机器上的 Python 或 8000 端口进程，
# 避免误伤同机其他服务；若端口仍被占用，让 systemd 启动失败并保留现场供排查。
sed "s|__DIR__|$SERVICE_DIR|g; s|__VENV__|$VENV|g" "$UNIT_SRC" > "$UNIT_DST"
systemctl daemon-reload
systemctl enable --now douyin-cloud-streak
systemctl restart douyin-cloud-streak
sleep 2

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [ -z "$IP" ]; then
  IP="你的服务器公网IP"
fi

echo ""
echo "======================================================"
echo "  🎉 恭喜！抖音云端续火花助手服务部署完成并已启动！"
echo "======================================================"
echo "应用已绑定本机: http://127.0.0.1:8000"
echo "管理员账号:       $(grep '^ADMIN_USERNAME=' "$SERVICE_DIR/.env" | cut -d= -f2-)"
if [ -n "$GENERATED_ADMIN_PASSWORD" ]; then
  echo "管理员密码（仅本次显示，请立即妥善保存）: $GENERATED_ADMIN_PASSWORD"
else
  echo "管理员密码:       已保留现有 .env 中的 ADMIN_PASSWORD"
fi
echo "配置文件位置:     $SERVICE_DIR/.env"
echo "======================================================"
echo "【下一步操作】"
echo "1. 请配置 Nginx HTTPS 反向代理到 127.0.0.1:8000，仅开放 80/443；不要放行 8000；"
echo "2. 在电脑上运行「1.本地提取通行证.bat」扫码获取登录态；"
echo "3. 运行「4.同步登录态到服务器.bat」上传登录态（或直接在 HTTPS 后台扫码）；"
echo "4. 浏览器访问你的 HTTPS 域名，使用管理员账号密码登录并勾选好友开启每日自动续火花！"
echo "======================================================"
