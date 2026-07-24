import sqlite3
import time
import json
import os
from flask import Flask, render_template, request, jsonify, send_file, redirect
from flask_cors import CORS
import qrcode
from io import BytesIO

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
CORS(app)

def get_real_ip():
    """获取真实客户端IP，穿透nginx代理"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    if request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    return get_real_ip()


import os

# ====== 部署配置 ======
# 可通过环境变量覆盖，例如: export MRDENG_DB=/data/mrdeng/db.sqlite
DB_FILE = os.environ.get('MRDENG_DB', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mrdeng.db'))
ADMIN_PASSWORD = os.environ.get('MRDENG_PASS', 'admin123')
# ====================

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS licenses (code TEXT PRIMARY KEY, tier TEXT, device_limit INTEGER, expire_time INTEGER, created_at INTEGER DEFAULT 0, description TEXT DEFAULT '', status TEXT DEFAULT 'active')"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS devices (device_id TEXT PRIMARY KEY, license_code TEXT, ip_address TEXT, network_type TEXT, status TEXT, last_heartbeat INTEGER)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS tasks (task_id INTEGER PRIMARY KEY AUTOINCREMENT, task_type TEXT, payload TEXT, status TEXT, assigned_device TEXT)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS logs (log_id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, log_type TEXT, message TEXT, created_at INTEGER)"
    )
    cursor.execute(
        "INSERT OR IGNORE INTO licenses (code, tier, device_limit, expire_time, created_at, description, status) VALUES ('STUDIO-PRO-8888', 'studio', 5, ?, ?, '默认管理员卡密', 'active')",
        (int(time.time()) + 86400 * 30, int(time.time())),
    )
    conn.commit()
    conn.close()

init_db()


@app.route('/api/device/bind-qrcode', methods=['GET'])
def device_bind_qrcode():
    """Generate QR code for device binding"""
    device_id = request.args.get('device_id', 'AUTO-' + str(int(time.time())))
    license_code = request.args.get('license_code', 'STUDIO-PRO-8888')
    
    # Generate payload: this is what the mobile app would parse
    bind_payload = {
        'server': 'https://mrdeng.site',
        'heartbeat_endpoint': '/api/device/heartbeat',
        'device_id': device_id,
        'license_code': license_code,
        'bind_time': int(time.time())
    }
    
    qr_data = json.dumps(bind_payload)
    img = qrcode.make(qr_data)
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')



@app.route('/api/device/quick-register', methods=['GET'])
def device_quick_register():
    """Quick device registration via GET (for browser link click)"""
    import uuid
    device_id = request.args.get('device_id', '')
    license_code = request.args.get('license_code', 'STUDIO-PRO-8888')
    network_type = request.args.get('network_type', 'wifi')
    
    if not device_id:
        device_id = 'WEB-' + uuid.uuid4().hex[:8].upper()
    
    ip = get_real_ip()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = int(time.time())
    c.execute('''INSERT OR REPLACE INTO devices (device_id, license_code, ip_address, network_type, last_heartbeat, status)
                 VALUES (?, ?, ?, ?, ?, 'online')''',
              (device_id, license_code, ip, network_type, now))
    c.execute('''INSERT INTO logs (device_id, log_type, message, created_at) 
                 VALUES (?, 'info', ?, ?)''',
              (device_id, f'设备 {device_id} 通过链接快速注册', now))
    conn.commit()
    conn.close()
    
    return redirect(f"/?registered={device_id}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM devices")
    total_devices = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM devices WHERE status='online'")
    online_devices = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'")
    pending_tasks = cursor.fetchone()[0]
    cursor.execute("SELECT * FROM devices")
    devices = [
        dict(zip([column[0] for column in cursor.description], row))
        for row in cursor.fetchall()
    ]
    cursor.execute("SELECT * FROM logs ORDER BY created_at DESC LIMIT 10")
    logs = [
        dict(zip([column[0] for column in cursor.description], row))
        for row in cursor.fetchall()
    ]
    conn.close()
    return jsonify({
        "total_devices": total_devices,
        "online_devices": online_devices,
        "pending_tasks": pending_tasks,
        "devices": devices,
        "logs": logs,
    })

@app.route('/api/device/heartbeat', methods=['POST'])
def device_heartbeat():
    data = request.json
    device_id = data.get('device_id')
    ip = get_real_ip()
    net_type = data.get('network_type', 'wifi')
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO devices (device_id, license_code, ip_address, network_type, status, last_heartbeat) VALUES (?, ?, ?, ?, 'online', ?)",
        (device_id, data.get('license_code'), ip, net_type, int(time.time())),
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "Heartbeat received"})


@app.route('/api/device/register', methods=['POST'])
def device_register():
    """Simple one-click device registration"""
    data = request.get_json() or {}
    device_name = data.get('device_name', '').strip()
    if not device_name:
        return jsonify({'status': 'error', 'message': '请输入设备名称'}), 400
    
    # Generate device_id from name + timestamp
    device_id = f"SIMPLE-{device_name.upper().replace(' ','-')}-{int(time.time())%10000}"
    ip = get_real_ip()
    license_code = data.get('license_code', 'STUDIO-PRO-8888')
    network_type = data.get('network_type', 'wifi')
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = int(time.time())
    c.execute('''INSERT OR REPLACE INTO devices (device_id, license_code, ip_address, network_type, last_heartbeat, status)
                 VALUES (?, ?, ?, ?, ?, 'online')''',
              (device_id, license_code, ip, network_type, now))
    c.execute('''INSERT INTO logs (device_id, log_type, message, created_at) 
                 VALUES (?, 'info', ?, ?)''',
              (device_id, f'设备 "{device_name}" 通过快速注册加入', now))
    conn.commit()
    conn.close()
    
    return jsonify({
        'status': 'success',
        'message': f'设备 {device_name} 注册成功',
        'device_id': device_id
    })
@app.route('/api/task/pull', methods=['POST'])
def pull_task():
    data = request.json
    device_id = data.get('device_id')
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT task_id, task_type, payload FROM tasks WHERE status = 'pending' LIMIT 1"
    )
    task = cursor.fetchone()
    if task:
        task_id, task_type, payload = task
        cursor.execute(
            "UPDATE tasks SET status = 'running', assigned_device = ? WHERE task_id = ?",
            (device_id, task_id),
        )
        conn.commit()
        conn.close()
        return jsonify({
            "has_task": True,
            "task_id": task_id,
            "task_type": task_type,
            "payload": json.loads(payload),
        })
    conn.close()
    return jsonify({"has_task": False})


# ============================================================
# 工具箱 API
# ============================================================

@app.route('/api/tools/fetch', methods=['POST'])
def tool_fetch():
    """curl_cffi URL 抓取"""
    data = request.json
    url = data.get('url', '')
    impersonate = data.get('impersonate', 'chrome110')
    if not url:
        return jsonify({'error': 'URL 不能为空'}), 400
    try:
        from curl_cffi import requests as cffi_requests
        resp = cffi_requests.get(url, impersonate=impersonate, timeout=30)
        return jsonify({
            'status': resp.status_code,
            'content': resp.text[:50000],
            'content_length': len(resp.text)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tools/markitdown', methods=['POST'])
def tool_markitdown():
    """MarkItDown 格式转换"""
    data = request.json
    url = data.get('url', '')
    if not url:
        return jsonify({'error': 'URL 不能为空'}), 400
    try:
        from markitdown import MarkItDown
        import tempfile, os
        md = MarkItDown()
        result = md.convert(url)
        return jsonify({
            'markdown': result.text_content[:100000],
            'length': len(result.text_content)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tools/autoscrape', methods=['POST'])
def tool_autoscrape():
    """AutoScraper 智能爬取"""
    data = request.json
    url = data.get('url', '')
    wanted_list = data.get('wanted_list', [])
    if not url or not wanted_list:
        return jsonify({'error': 'URL 和 wanted_list 不能为空'}), 400
    try:
        from autoscraper import AutoScraper
        scraper = AutoScraper()
        results = scraper.build(url, wanted_list)
        return jsonify({
            'results': results,
            'count': len(results)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tools/scrapling', methods=['POST'])
def tool_scrapling():
    """Scrapling 自适应爬取"""
    data = request.json
    url = data.get('url', '')
    selector = data.get('selector', '')
    if not url:
        return jsonify({'error': 'URL 不能为空'}), 400
    try:
        from scrapling import PlayWrightFetcher
        fetcher = PlayWrightFetcher()
        html = fetcher.fetch(url, auto_match=True)
        if selector:
            html = html.css(selector)
        return jsonify({
            'html': str(html)[:50000],
            'length': len(str(html))
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500



# ============================================================
# 任务管理
# ============================================================

@app.route('/api/tasks/list', methods=['GET'])
def tasks_list():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks ORDER BY task_id DESC")
    tasks = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'tasks': tasks})

@app.route('/api/task/<int:task_id>/complete', methods=['POST'])
def task_complete(task_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET status='completed' WHERE task_id=?", (task_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})

@app.route('/api/task/<int:task_id>/cancel', methods=['POST'])
def task_cancel(task_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET status='cancelled' WHERE task_id=?", (task_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})

@app.route('/api/task/create', methods=['POST'])
def task_create():
    data = request.json
    task_type = data.get('task_type', 'crawl')
    target = data.get('target', '')
    duration = data.get('duration', 60)
    payload = json.dumps({'target': target, 'duration': duration, 'created_by': 'web'})
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tasks (task_type, payload, status) VALUES (?, ?, 'pending')", (task_type, payload))
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return jsonify({'status': 'ok', 'task_id': task_id})


# ============================================================
# 设备操作
# ============================================================

@app.route('/api/device/<device_id>/detail', methods=['GET'])
def device_detail(device_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM devices WHERE device_id=?", (device_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': '设备不存在'}), 404
    device = dict(zip([column[0] for column in cursor.description], row))
    cursor.execute("SELECT * FROM logs WHERE device_id=? ORDER BY created_at DESC LIMIT 20", (device_id,))
    logs = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'device': device, 'logs': logs})

@app.route('/api/device/<device_id>/unbind', methods=['POST'])
def device_unbind(device_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM devices WHERE device_id=?", (device_id,))
    cursor.execute("INSERT INTO logs (device_id, log_type, message, created_at) VALUES (?, 'info', ?, ?)",
                   (device_id, f'设备 {device_id} 已被手动解绑', int(time.time())))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'message': f'设备 {device_id} 已解绑'})


# ============================================================
# 卡密管理（完整授权系统）
# ============================================================

LICENSE_TIERS = {
    'basic':    {'name': '基础版', 'devices': 3,  'days': 30,  'color': '#6b7280'},
    'studio':   {'name': '专业版', 'devices': 10, 'days': 180, 'color': '#3b82f6'},
    'pro':      {'name': '旗舰版', 'devices': 50, 'days': 365, 'color': '#8b5cf6'},
    'ultimate': {'name': '至尊版', 'devices': -1, 'days': 0,   'color': '#f59e0b'},
}

@app.route('/api/licenses', methods=['GET'])
def licenses_list():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT l.*, (SELECT COUNT(*) FROM devices WHERE license_code=l.code) as used_count FROM licenses l ORDER BY l.expire_time DESC")
    licenses = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'licenses': licenses, 'tiers': LICENSE_TIERS})

@app.route('/api/license/create', methods=['POST'])
def license_create():
    import random, string
    data = request.json
    tier = data.get('tier', 'basic')
    device_limit = data.get('device_limit')
    days = data.get('days')
    description = data.get('description', '')
    code = data.get('code', '')

    # Use tier defaults if not specified
    tdef = LICENSE_TIERS.get(tier, LICENSE_TIERS['basic'])
    if device_limit is None:
        device_limit = tdef['devices']
    if days is None:
        days = tdef['days']

    if not code:
        prefix = {'basic':'BASIC-','studio':'STUDIO-','pro':'PRO-','ultimate':'ULT-'}.get(tier, 'LIC-')
        code = prefix + ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    expire_time = int(time.time()) + days * 86400 if days > 0 else 0
    created_at = int(time.time())
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO licenses VALUES (?, ?, ?, ?, ?, ?, 'active')",
                   (code, tier, device_limit, expire_time, created_at, description))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'code': code, 'tier': tier, 'device_limit': device_limit,
                    'expire_time': expire_time, 'created_at': created_at, 'description': description})

@app.route('/api/license/<code>/delete', methods=['POST'])
def license_delete(code):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM devices WHERE license_code=?", (code,))
    used = cursor.fetchone()[0]
    if used > 0:
        conn.close()
        return jsonify({'status': 'error', 'message': '该卡密下有 ' + str(used) + ' 台设备，请先解绑再删除'}), 400
    cursor.execute("DELETE FROM licenses WHERE code=?", (code,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'message': '卡密 ' + code + ' 已删除'})

@app.route('/api/license/<code>/update', methods=['POST'])
def license_update(code):
    data = request.json
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    allowed = ['tier', 'device_limit', 'expire_time', 'description', 'status']
    sets = []
    vals = []
    for k in allowed:
        if k in data:
            sets.append(k + '=?')
            vals.append(data[k])
    if not sets:
        conn.close()
        return jsonify({'status': 'error', 'message': '无可更新字段'}), 400
    vals.append(code)
    cursor.execute("UPDATE licenses SET " + ', '.join(sets) + " WHERE code=?", vals)
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})

@app.route('/api/license/<code>/detail', methods=['GET'])
def license_detail(code):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT l.*, (SELECT COUNT(*) FROM devices WHERE license_code=l.code) as used_count FROM licenses l WHERE l.code=?", (code,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': '卡密不存在'}), 404
    lic = dict(zip([column[0] for column in cursor.description], row))
    cursor.execute("SELECT device_id, ip_address, status, last_heartbeat FROM devices WHERE license_code=?", (code,))
    devices = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'license': lic, 'devices': devices})


# ============================================================
# 登录保护
# ============================================================

LOGIN_PASSWORD = 'admin123'

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'GET':
        # Check if already logged in
        if request.cookies.get('mrdeng_auth') == LOGIN_PASSWORD:
            return redirect('/')
        return render_template('login.html')
    # POST
    pw = request.json.get('password', '') if request.is_json else request.form.get('password', '')
    if pw == LOGIN_PASSWORD:
        resp = jsonify({'status': 'ok'})
        resp.set_cookie('mrdeng_auth', LOGIN_PASSWORD, max_age=86400*7, httponly=True)
        return resp
    return jsonify({'status': 'error', 'message': '密码错误'}), 401


@app.before_request
def check_auth():
    if request.path == '/login' or request.path.startswith('/api/device/heartbeat') or request.path.startswith('/api/device/register') or request.path.startswith('/api/device/quick-register') or request.path.startswith('/api/device/bind-qrcode') or request.path.startswith('/static/'):
        return None
    if request.path.startswith('/api/') or request.path == '/':
        if request.cookies.get('mrdeng_auth') != LOGIN_PASSWORD:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'unauthorized'}), 401
            return redirect('/login')
    return None

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
