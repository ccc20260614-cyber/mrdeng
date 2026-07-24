import sqlite3
import time
import json
import os
import logging

# ====== 部署配置 ======
DB_FILE = os.environ.get('MRDENG_DB', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mrdeng.db'))
# ====================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [Harvester] - %(levelname)s - %(message)s')

def fetch_external_tasks():
    mock_harvested_data = [
        {
            "task_type": "ai_browse",
            "payload": json.dumps({"target_url": "https://mrdeng.site/target_a", "action": "gaussian_scroll", "duration": 25})
        },
        {
            "task_type": "matrix_interact",
            "payload": json.dumps({"target_url": "https://mrdeng.site/target_b", "action": "bezier_click_and_stay", "duration": 40})
        }
    ]
    return mock_harvested_data

def sync_tasks_to_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        new_tasks = fetch_external_tasks()
        added_count = 0
        for task in new_tasks:
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE payload = ? AND status = 'pending'", (task['payload'],))
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO tasks (task_type, payload, status, assigned_device) VALUES (?, ?, 'pending', NULL)",
                               (task['task_type'], task['payload']))
                added_count += 1
        conn.commit()
        conn.close()
        if added_count > 0:
            logging.info(f"New tasks injected: {added_count}")
    except Exception as e:
        logging.error(f"Harvester sync failed: {e}")

if __name__ == '__main__':
    logging.info("Harvester daemon started...")
    while True:
        sync_tasks_to_db()
        time.sleep(600)
