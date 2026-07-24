#!/bin/bash
# ============================================
#  MrDeng 设备管理面板 - 一键安装脚本
#  v1.0 | 2026-07-24
# ============================================

set -e

# ---- 配置 ----
INSTALL_DIR="${1:-/opt/mrdeng}"
SERVICE_NAME="mrdeng"
NGINX_CONF="/etc/nginx/conf.d/mrdeng.conf"
GUNICORN_PORT="5000"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[MrDeng]${NC} $1"; }
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC} $1"; exit 1; }

echo ""
echo "  MrDeng 设备管理面板 v1.0 安装"
echo "======================================"
echo ""

# ---- 检查 root ----
if [ "$EUID" -ne 0 ]; then err "请以 root 用户运行: sudo bash install.sh"; fi

# ---- 检测系统 ----
if [ -f /etc/redhat-release ]; then
    PKG_MGR="yum"
elif [ -f /etc/debian_version ]; then
    PKG_MGR="apt-get"
else
    err "不支持的系统，仅支持 CentOS/RHEL/Debian/Ubuntu"
fi

log "安装目录: ${INSTALL_DIR}"

# ---- 安装系统依赖 ----
log "检查系统依赖..."
for dep in python3 python3-pip nginx; do
    if ! command -v $dep &>/dev/null; then
        log "安装 $dep ..."
        $PKG_MGR install -y $dep &>/dev/null || err "无法安装 $dep"
    fi
done

# ---- 创建目录 ----
mkdir -p "${INSTALL_DIR}/templates"
mkdir -p "${INSTALL_DIR}/logs"

# ---- 复制文件 ----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
log "复制程序文件..."
cp -f "${SCRIPT_DIR}/app.py"          "${INSTALL_DIR}/"
cp -f "${SCRIPT_DIR}/harvester.py"    "${INSTALL_DIR}/"
cp -f "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/"
cp -f "${SCRIPT_DIR}/templates/index.html" "${INSTALL_DIR}/templates/"
cp -f "${SCRIPT_DIR}/templates/login.html" "${INSTALL_DIR}/templates/"

# ---- 安装 Python 依赖 ----
log "安装 Python 依赖..."
pip3 install -r "${INSTALL_DIR}/requirements.txt" -q &>/dev/null || err "Python 依赖安装失败"

# ---- 初始化数据库 ----
log "初始化数据库..."
cd "${INSTALL_DIR}"
python3 -c "
import sqlite3, os
db = os.path.join('${INSTALL_DIR}', 'mrdeng.db')
conn = sqlite3.connect(db)
conn.execute('CREATE TABLE IF NOT EXISTS licenses (code TEXT PRIMARY KEY, tier TEXT, device_limit INTEGER, expire_time INTEGER, created_at INTEGER DEFAULT 0, description TEXT DEFAULT \"\", status TEXT DEFAULT \"active\")')
conn.execute('CREATE TABLE IF NOT EXISTS devices (device_id TEXT PRIMARY KEY, license_code TEXT, ip_address TEXT, network_type TEXT, status TEXT, last_heartbeat INTEGER)')
conn.execute('CREATE TABLE IF NOT EXISTS tasks (task_id INTEGER PRIMARY KEY AUTOINCREMENT, task_type TEXT, payload TEXT, status TEXT, assigned_device TEXT)')
conn.execute('CREATE TABLE IF NOT EXISTS logs (log_id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, log_type TEXT, message TEXT, created_at INTEGER)')
conn.commit()
conn.close()
print('Database initialized.')
" || err "数据库初始化失败"

ok "文件部署完成"

# ---- 创建 systemd 服务 ----
log "创建 systemd 服务..."
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=MrDeng Device Management Panel
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
Environment="MRDENG_DB=${INSTALL_DIR}/mrdeng.db"
Environment="MRDENG_PASS=admin123"
ExecStart=/usr/local/bin/gunicorn -w 2 -b 127.0.0.1:${GUNICORN_PORT} app:app
Restart=always
RestartSec=5
StandardOutput=append:${INSTALL_DIR}/logs/gunicorn.log
StandardError=append:${INSTALL_DIR}/logs/gunicorn.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${SERVICE_NAME} &>/dev/null
systemctl restart ${SERVICE_NAME}

# 等待启动
sleep 2
if systemctl is-active --quiet ${SERVICE_NAME}; then
    ok "服务已启动"
else
    err "服务启动失败，请查看日志: journalctl -u ${SERVICE_NAME} -n 20"
fi

# ---- Nginx 配置 ----
if [ -f "${NGINX_CONF}" ]; then
    log "检测到已有 Nginx 配置，备份到 ${NGINX_CONF}.bak"
    cp -f "${NGINX_CONF}" "${NGINX_CONF}.bak"
fi

log "配置 Nginx..."

# 检测是否有域名
read -p "请输入你的域名（如 mrdeng.example.com，直接回车跳过）: " DOMAIN
if [ -z "$DOMAIN" ]; then
    DOMAIN="_"
    SERVER_NAME_LINE=""
else
    SERVER_NAME_LINE="    server_name ${DOMAIN};"
fi

cat > ${NGINX_CONF} << EOF
server {
    listen 80;
    ${SERVER_NAME_LINE}

    # 访问日志
    access_log ${INSTALL_DIR}/logs/nginx_access.log;
    error_log  ${INSTALL_DIR}/logs/nginx_error.log;

    location / {
        proxy_pass http://127.0.0.1:${GUNICORN_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# 测试并重载 nginx
if nginx -t &>/dev/null; then
    systemctl reload nginx &>/dev/null
    ok "Nginx 配置完成"
else
    err "Nginx 配置有误，请检查 ${NGINX_CONF}"
fi

# ---- 防火墙 ----
if command -v firewall-cmd &>/dev/null; then
    firewall-cmd --add-service=http --permanent &>/dev/null
    firewall-cmd --reload &>/dev/null
    log "防火墙已放行 80 端口"
elif command -v ufw &>/dev/null; then
    ufw allow 80/tcp &>/dev/null
    log "防火墙已放行 80 端口"
fi

# ---- 完成 ----
echo ""
echo "======================================"
echo -e "  ${GREEN}安装完成！${NC}"
echo ""
echo "  访问地址:  http://$(hostname -I | awk '{print $1}')"
[ -n "$DOMAIN" ] && echo "            http://${DOMAIN}"
echo ""
echo "  管理员密码: admin123"
echo "  (通过环境变量 MRDENG_PASS 修改)"
echo ""
echo "  服务管理:"
echo "    systemctl start|stop|restart ${SERVICE_NAME}"
echo "    查看日志: journalctl -u ${SERVICE_NAME} -f"
echo ""
echo "  安装目录: ${INSTALL_DIR}"
echo "  数据库:   ${INSTALL_DIR}/mrdeng.db"
echo "======================================"
