from flask import Flask, render_template, jsonify, request
import subprocess
import os
import yaml
from datetime import datetime

app = Flask(__name__)
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")

with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

bridge_ip = config["bridge_ip"]

SERVICES = {
    "poller": "hue-poller.service",
    "monitor": "monitor.service",
    "dashboard": "sensors.service"
}

def run_cmd(cmd):
    try:
        print(f"[DEBUG] Running command: {cmd}")
        result = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode().strip()
        return result
    except subprocess.CalledProcessError as e:
        result = e.output.decode().strip()
        if result in ["inactive", "disabled", "enabled", "active"]:
            return result
        return "[ERROR] Command failed: " + result

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/status")
def status():
    status_data = {}
    for key, svc in SERVICES.items():
        status_data[key] = {
            "status": run_cmd(f"systemctl is-active {svc}"),
            "enabled": run_cmd(f"systemctl is-enabled {svc}"),
            "log": run_cmd(f"journalctl -u {svc} -n 10 --no-pager")
        }

    bridge_reachable = os.system(f"ping -c 1 -W 1 {bridge_ip} > /dev/null") == 0

    return jsonify({
        "services": status_data,
        "bridge": bridge_reachable
    })

@app.route("/control", methods=["POST"])
def control():
    action = request.json.get("action")
    target = request.json.get("service")

    service_name = SERVICES.get(target)
    if not service_name:
        return jsonify({"result": "Unknown service"}), 400

    if action in ["start", "stop", "restart"]:
        out = run_cmd(f"sudo systemctl {action} {service_name}")
    else:
        out = "Invalid action"

    return jsonify({"result": out})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081, debug=True)
