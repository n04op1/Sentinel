# hue_motion_logger.py — V2-Only Unified Version

import requests
import time
import os
import yaml
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dateutil.parser import isoparse

# === Load Configuration ===
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

bridge_ip = config["bridge_ip"]
app_key = config["username"]  # v2: API key is stored under "username"
poll_interval = config.get("poll_interval", 3)
sensors = config["sensors"]
log_folder = config.get("log_folder", "logs")

# Initialize paths
script_dir = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(script_dir, "sensor_data.db")
LOG_DIR = os.path.join(script_dir, log_folder)
os.makedirs(LOG_DIR, exist_ok=True)

# Timezone setup
local_tz = ZoneInfo("Europe/Ljubljana")
last_motion_times = {str(sensor["id"]): None for sensor in sensors}
last_contact_time = None

# Resource ID to sensor name mapping (based on config.yaml)
id_to_name = {str(sensor["id"]): sensor["name"] for sensor in sensors}

print(f"Polling Hue v2 sensors every {poll_interval} seconds...")
print(f"Database: {DB_PATH}")
print(f"Log directory: {LOG_DIR}\n")

def log_to_both(target, sensor_name, sensor_id, utc_timestamp, data_type, value=None):
    try:
        dt_utc = isoparse(utc_timestamp).replace(tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone(local_tz)
        local_time_str = dt_local.strftime("%Y-%m-%d %H:%M:%S")

        if target == "motion":
            log_line = f"[Motion] {sensor_name} (ID: {sensor_id}) {local_time_str}"
        else:
            unit = "\u00b0C" if data_type == "temperature" else ""
            log_line = f"[Sensor] {sensor_name} (ID: {sensor_id}) {local_time_str} => {data_type.capitalize()}: {value}{unit}"

        log_path = os.path.join(LOG_DIR, f"{target}_{dt_local.strftime('%Y-%m-%d')}.txt")
        with open(log_path, "a") as f:
            f.write(log_line + "\n")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        if target == "motion":
            cursor.execute('''INSERT INTO raw_sensor_data (sensor_id, room, sensor_type, timestamp, raw_log_line)
                              VALUES (?, ?, ?, ?, ?)''',
                           (sensor_id, sensor_name, "motion", utc_timestamp, log_line))
        else:
            cursor.execute('''INSERT INTO raw_sensor_data (sensor_id, room, sensor_type, value, timestamp, raw_log_line)
                              VALUES (?, ?, ?, ?, ?, ?)''',
                           (sensor_id, sensor_name, data_type, value, utc_timestamp, log_line))

        conn.commit()
        conn.close()
        print(log_line)

    except Exception as e:
        print(f"Error in log_to_both: {str(e)}")

# Disable SSL warnings for local Hue Bridge
requests.packages.urllib3.disable_warnings()
base_url = f"https://{bridge_ip}/clip/v2/resource"

while True:
    try:
        now = datetime.now(local_tz)

        for sensor_type in ["motion", "temperature", "light_level", "contact"]:
            url = f"{base_url}/{sensor_type}"
            resp = requests.get(url, headers={"hue-application-key": app_key}, verify=False)
            data = resp.json()

            for item in data.get("data", []):
                sid = item.get("id")
                if not sid:
                    continue

                if sensor_type == "motion":
                    state = item.get("motion", {}).get("motion")
                    changed = item.get("motion", {}).get("motion_report", {}).get("changed")
                    if state and changed:
                        name = id_to_name.get(item.get("id_v1", "").split("/")[-1], f"motion_{sid[:6]}")
                        if last_motion_times.get(sid) is None or changed > last_motion_times[sid]:
                            log_to_both("motion", name, sid, changed, None)
                            last_motion_times[sid] = changed

                elif sensor_type == "temperature":
                    val = item.get("temperature", {}).get("temperature")
                    changed = item.get("temperature", {}).get("temperature_report", {}).get("changed")
                    if val is not None and changed:
                        name = id_to_name.get(item.get("id_v1", "").split("/")[-1], f"temp_{sid[:6]}")
                        log_to_both("sensor_metrics", name, sid, changed, "temperature", val)

                elif sensor_type == "light_level":
                    val = item.get("light", {}).get("light_level")
                    changed = item.get("light", {}).get("light_level_report", {}).get("changed")
                    if val is not None and changed:
                        name = id_to_name.get(item.get("id_v1", "").split("/")[-1], f"light_{sid[:6]}")
                        log_to_both("sensor_metrics", name, sid, changed, "brightness", val)

                elif sensor_type == "contact":
                    state = item.get("contact_report", {}).get("state")
                    changed = item.get("contact_report", {}).get("changed")
                    if state and changed and changed != last_contact_time:
                        value = 1 if state == "no_contact" else 0
                        log_to_both("sensor_metrics", "Door Sensor", sid, changed, "open", value)
                        last_contact_time = changed

    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

    time.sleep(poll_interval)

