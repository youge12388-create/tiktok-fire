"""一键将整站源码与环境全自动部署到云服务器 (Zero-Touch Remote Deployer)

极速优化版：
1. 自动过滤开发依赖与临时文件；
2. 采用内存级 tar.gz 压缩包单文件毫秒级极速上传（从 5 分钟加速至 2 秒！）；
3. 远程一键解压并执行 deploy/deploy.sh 启动后台守护服务！
"""

from __future__ import annotations

import io
import os
import shlex
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from pathlib import PurePosixPath

# 确保控制台 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent

# 部署包绝不能包含服务器凭据、登录态或本地临时工作目录。
IGNORE_NAMES = {".git", "__pycache__", ".venv", "venv", ".pytest_cache", ".idea", ".vscode", "logs"}
SENSITIVE_DIRECTORY_NAMES = {"data", ".agent", ".tmp", ".impeccable"}
SENSITIVE_FILE_NAMES = {".env", "state.json"}


def should_exclude_from_archive(relative_path: PurePosixPath) -> bool:
    """Return whether a path must stay out of the source deployment archive."""
    return (
        any(part in IGNORE_NAMES or part in SENSITIVE_DIRECTORY_NAMES for part in relative_path.parts)
        or relative_path.name in SENSITIVE_FILE_NAMES
        or relative_path.name.endswith((".log", ".tmp", ".pid"))
    )


def print_banner():
    print("=" * 65)
    print("       🚀 抖音云端自动续火花 · 云服务器一键自动化极速部署工具")
    print("=" * 65)


def create_deploy_archive() -> Path:
    """打包可部署源码，排除本机凭据、运行数据和临时目录。"""
    temp_tar = Path(tempfile.gettempdir()) / "douyin_cloud_streak_deploy.tar.gz"
    
    print("[*] 正在打包项目源码（不包含本机凭据、运行数据或临时文件）...")
    with tarfile.open(temp_tar, "w:gz") as tar:
        for item in BASE_DIR.iterdir():
            if should_exclude_from_archive(PurePosixPath(item.name)):
                continue

            def _filter(tarinfo):
                if should_exclude_from_archive(PurePosixPath(tarinfo.name)):
                    return None
                if (
                    tarinfo.name.endswith(".pyc")
                    or tarinfo.name.endswith((".log", ".tmp", ".pid"))
                    or ".log." in tarinfo.name
                ):
                    return None
                return tarinfo

            tar.add(str(item), arcname=item.name, filter=_filter)

    size_kb = temp_tar.stat().st_size / 1024
    print(f"[✓] 全量打包完成！压缩包大小: {size_kb:.1f} KB\n")
    return temp_tar


def main():
    print_banner()

    server_ip = input("👉 请输入云服务器公网 IP 地址 (例如 123.45.67.89): ").strip()
    if not server_ip:
        print("[❌ 错误] 服务器 IP 不能为空！")
        input("\n按回车键退出...")
        sys.exit(1)

    server_user = input("👉 请输入 SSH 用户名 [直接回车默认 root]: ").strip() or "root"
    port_input = input("👉 请输入 SSH 端口号 [直接回车默认 22]: ").strip()
    server_port = int(port_input) if port_input.isdigit() else 22
    remote_dir = input("👉 请输入部署路径 [直接回车默认 /opt/douyin-cloud-streak]: ").strip() or "/opt/douyin-cloud-streak"
    if not remote_dir.startswith("/") or any(char in remote_dir for char in ("\r", "\n")):
        print("[❌ 错误] 部署路径必须是绝对 Linux 路径，且不能包含换行符！")
        input("\n按回车键退出...")
        sys.exit(1)

    print("-" * 65)
    password = input("🔑 请输入服务器密码 (明文可见，支持右键直接粘贴): ").strip()
    print("-" * 65)

    if not password:
        print("[❌ 错误] 密码不能为空！")
        input("\n按回车键退出...")
        sys.exit(1)

    print(f"\n[*] 正在连接到服务器 {server_user}@{server_ip}:{server_port} ...")

    try:
        import paramiko
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=server_ip,
            port=server_port,
            username=server_user,
            password=password,
            timeout=15,
            banner_timeout=15,
            auth_timeout=15
        )
        print("[✓] SSH 连接成功！\n")

        # 1. 打包并极速上传
        archive_path = create_deploy_archive()
        remote_tar = f"/tmp/douyin_cloud_streak_deploy.tar.gz"

        print(f"[*] 正在将打包文件秒级上传至服务器 /tmp ...")
        sftp = ssh.open_sftp()
        sftp.put(str(archive_path), remote_tar)
        sftp.close()
        archive_path.unlink(missing_ok=True)
        print("[✓] 上传完成！\n")

        # 2. 远程解压并部署 (强制覆盖旧版本文件)
        print(f"[*] 正在远程强制覆盖解压至 {remote_dir} 并启动部署...")
        remote_dir_q = shlex.quote(remote_dir)
        remote_tar_q = shlex.quote(remote_tar)
        extract_cmd = f"mkdir -p {remote_dir_q} && tar --overwrite -xzf {remote_tar_q} -C {remote_dir_q} && rm -f {remote_tar_q}"
        stdin, stdout, stderr = ssh.exec_command(extract_cmd)
        stdout.channel.recv_exit_status()
        print("[✓] 远程代码覆盖解压就绪！\n")

        # 3. 执行 deploy/deploy.sh
        print("=" * 65)
        print("  [*] 正在云端服务器自动安装依赖环境并启动守护进程...")
        print("  [*] 这通常需要 1~2 分钟（配置 Python 虚拟环境与 Playwright 内核）...")
        print("=" * 65)

        cmd = f"cd {remote_dir_q} && sed -i 's/\\r$//' deploy/deploy.sh deploy/*.service 2>/dev/null || true; chmod +x deploy/deploy.sh && bash deploy/deploy.sh"
        stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)

        for line in iter(stdout.readline, ""):
            print(line, end="")

        exit_status = stdout.channel.recv_exit_status()

        if exit_status == 0:
            print("\n" + "=" * 65)
            print("  🎉🎉🎉 恭喜！云服务器已全部部署完成并成功启动！")
            print("=" * 65)
            print("🌐 Web 管理后台地址: 请使用 Nginx 配置的 HTTPS 域名")
            print("🔑 请使用服务器 .env 中的 ADMIN_USERNAME / ADMIN_PASSWORD 登录。")
            print("=" * 65)
            print("【接下来只需】：")
            print("1. 配置 Nginx HTTPS 反向代理到服务器本机 127.0.0.1:8000，仅开放 80/443。")
            print("2. 浏览器打开 HTTPS 域名，在「账号」页扫码登录并在「联系人」页勾选好友。")
            print("3. 云服务器将在每天设定的时间 24 小时全自动为您维持火花！")
            print("=" * 65)
        else:
            print(f"\n[⚠️ 部署脚本返回状态码 {exit_status}] 请查看上方输出信息。")

        ssh.close()

    except Exception as e:
        print(f"\n[❌ 部署发生异常] {e}")

    input("\n按回车键退出...")


if __name__ == "__main__":
    main()
