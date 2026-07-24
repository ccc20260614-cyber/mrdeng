#!/bin/bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/opt/mrdeng"

[ "$EUID" -ne 0 ] && { echo "Please run as root: sudo bash install-local.sh"; exit 1; }

echo "Installing MrDeng from local files..."

mkdir -p "${INSTALL_DIR}/templates" "${INSTALL_DIR}/logs"
cp -f "${DIR}/app.py" "${INSTALL_DIR}/"
cp -f "${DIR}/harvester.py" "${INSTALL_DIR}/"
cp -f "${DIR}/requirements.txt" "${INSTALL_DIR}/"
cp -f "${DIR}/templates/"*.html "${INSTALL_DIR}/templates/"

pip3 install -r "${INSTALL_DIR}/requirements.txt" -q

cd "${INSTALL_DIR}"
python3 -c "
import sqlite3
db='${INSTALL_DIR}/mrdeng.db'
c=sqlite3.connect(db)
c.execute('CREATE TABLE IF NOT EXISTS licenses(code TEXT PRIMARY KEY,tier TEXT,device_limit INTEGER,expire_time INTEGER,created_at INTEGER DEFAULT 0,description TEXT DEFAULT \"\",status TEXT DEFAULT \"active\")')
c.execute('CREATE TABLE IF NOT EXISTS devices(device_id TEXT PRIMARY KEY,license_code TEXT,ip_address TEXT,network_type TEXT,status TEXT,last_heartbeat INTEGER)')
c.execute('CREATE TABLE IF NOT EXISTS tasks(task_id INTEGER PRIMARY KEY AUTOINCREMENT,task_type TEXT,payload TEXT,status TEXT,assigned_device TEXT)')
c.execute('CREATE TABLE IF NOT EXISTS logs(log_id INTEGER PRIMARY KEY AUTOINCREMENT,device_id TEXT,log_type TEXT,message TEXT,created_at INTEGER)')
c.execute(\"INSERT OR IGNORE INTO licenses(code,tier,device_limit,expire_time,created_at,description,status) VALUES('STUDIO-PRO-8888','专业版',10,2147483647,strftime('%s','now'),'默认卡密','active')\")
c.commit();c.close()
"

cat > /etc/systemd/system/mrdeng.service << EOF
[Unit]
Description=MrDeng Panel
After=network.target
[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
Environment="MRDENG_DB=${INSTALL_DIR}/mrdeng.db"
Environment="MRDENG_PASS=admin123"
ExecStart=/usr/local/bin/gunicorn -w 2 -b 127.0.0.1:5000 app:app
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable mrdeng &>/dev/null
systemctl restart mrdeng

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo ""
echo "Done! Open http://${IP}"
echo "Password: admin123"
