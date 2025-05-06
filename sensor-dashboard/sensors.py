#!/usr/bin/env python3
from flask import Flask, render_template, jsonify, request
import os
import yaml
from datetime import datetime, timedelta
from collections import defaultdict
import re
import bisect

app = Flask(__name__)

CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config.yaml'))
with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)

LOG_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', config.get("log_folder", "logs")))

def parse_metrics_file(filepath):
    print(f"[DEBUG] Parsing metrics file: {filepath}")
    sensor_data = defaultdict(lambda: {"brightness": [], "temperature": [], "timestamps": []})
    if not os.path.exists(filepath):
        print(f"[WARNING] Metrics file not found: {filepath}")
        return sensor_data

    with open(filepath, 'r') as f:
        for line in f:
            try:
                parts = line.strip().split(" => ")
                if len(parts) < 2:
                    continue
                
                # Parse sensor header
                header_match = re.match(r"\[Sensor\] (.+) \(ID: (\d+)\) (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", parts[0])
                if not header_match:
                    continue
                    
                name, sensor_id, timestamp = header_match.groups()
                room = name.strip().split(" - ")[0]
                sensor_data[room]["timestamps"].append(timestamp)
                
                # Parse sensor values
                if "Light" in parts[1]:
                    brightness = int(parts[1].split(":")[1].strip())
                    sensor_data[room]["brightness"].append(brightness)
                elif "Temp" in parts[1]:
                    temperature = float(parts[1].split(":")[1].strip().replace("°C", ""))
                    sensor_data[room]["temperature"].append(temperature)
            except Exception as e:
                print(f"[WARNING] Error parsing line: {line.strip()}\nError: {str(e)}")

    # Debug output
    for room, data in sensor_data.items():
        print(f"[DEBUG] Room '{room}' parsed - "
              f"Timestamps: {len(data['timestamps'])}, "
              f"Temp: {len(data['temperature'])}, "
              f"Brightness: {len(data['brightness'])}")
              
    return sensor_data

def parse_motion_file(filepath):
    print(f"[DEBUG] Parsing motion file: {filepath}")
    motion_events = defaultdict(list)
    if not os.path.exists(filepath):
        print(f"[WARNING] Motion file not found: {filepath}")
        return motion_events

    with open(filepath, 'r') as f:
        for line in f:
            match = re.match(r"\[Motion\] (.+) \(ID: (\d+)\) (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line.strip())
            if match:
                name, sensor_id, timestamp = match.groups()
                room = name.strip().split(" - ")[0]
                motion_events[room].append(timestamp)
    
    print(f"[DEBUG] Motion events parsed - Rooms: {list(motion_events.keys())}")
    return motion_events

def align_and_bucket_data(sensor_data, motion_data, bucket_size_minutes):
    print(f"[DEBUG] Aligning data with bucket size: {bucket_size_minutes} minutes")
    all_data = {}
    bucket_size = timedelta(minutes=bucket_size_minutes)

    for room in set(sensor_data.keys()).union(motion_data.keys()):
        # Convert all timestamps to datetime objects
        sensor_times = [datetime.strptime(t, "%Y-%m-%d %H:%M:%S") 
                       for t in sensor_data.get(room, {}).get("timestamps", [])]
        motion_times = [datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
                       for t in motion_data.get(room, [])]

        if not sensor_times and not motion_times:
            print(f"[DEBUG] Skipping room '{room}' - no data")
            continue

        # Create unified time range
        all_times = sensor_times + motion_times
        min_time = min(all_times).replace(second=0, microsecond=0)
        max_time = max(all_times).replace(second=0, microsecond=0) + timedelta(minutes=1)

        # Generate bucket edges
        buckets = []
        current = min_time
        while current <= max_time:
            buckets.append(current)
            current += bucket_size

        # Initialize storage
        temp_vals = [None] * (len(buckets)-1)
        bright_vals = [None] * (len(buckets)-1)
        motion_counts = [0] * (len(buckets)-1)

        # Assign sensor readings (last value in each bucket)
        for i, t in enumerate(sensor_times):
            idx = bisect.bisect_right(buckets, t) - 1
            if 0 <= idx < len(temp_vals):
                if i < len(sensor_data[room]["temperature"]):
                    temp_vals[idx] = sensor_data[room]["temperature"][i]
                if i < len(sensor_data[room]["brightness"]):
                    bright_vals[idx] = sensor_data[room]["brightness"][i]

        # Assign motion events (count per bucket)
        for t in motion_times:
            idx = bisect.bisect_right(buckets, t) - 1
            if 0 <= idx < len(motion_counts):
                motion_counts[idx] += 1

        # Forward-fill None values
        last_temp = None
        last_bright = None
        filled_temp = []
        filled_bright = []
        
        for t, b in zip(temp_vals, bright_vals):
            if t is not None:
                last_temp = t
            if b is not None:
                last_bright = b
            filled_temp.append(last_temp if last_temp is not None else None)
            filled_bright.append(last_bright if last_bright is not None else None)

        # Convert None to 0 for frontend
        final_temp = [t if t is not None else 0 for t in filled_temp]
        final_bright = [b if b is not None else 0 for b in filled_bright]

        all_data[room] = {
            "temperature": final_temp,
            "brightness": final_bright,
            "motion": motion_counts,
            "timestamps": [buckets[i].strftime("%H:%M:%S") for i in range(len(buckets)-1)]
        }

        print(f"[DEBUG] Room '{room}' processed - "
              f"Buckets: {len(motion_counts)}, "
              f"Temp samples: {len([t for t in final_temp if t != 0])}, "
              f"Bright samples: {len([b for b in final_bright if b != 0])}, "
              f"Motion events: {sum(motion_counts)}")

    return all_data

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/data")
def data():
    try:
        bucket_size = int(request.args.get("bucket", 5))
        date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
        
        print(f"\n[REQUEST] Data request - Date: {date}, Bucket: {bucket_size}min")
        
        metrics_file = os.path.join(LOG_FOLDER, f"sensor_metrics_{date}.txt")
        motion_file = os.path.join(LOG_FOLDER, f"motion_{date}.txt")

        sensor_data = parse_metrics_file(metrics_file)
        motion_data = parse_motion_file(motion_file)
        unified_data = align_and_bucket_data(sensor_data, motion_data, bucket_size)
        
        print(f"[REQUEST] Returning data for rooms: {list(unified_data.keys())}\n")
        return jsonify(unified_data)
        
    except Exception as e:
        print(f"[ERROR] Data endpoint failed: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("[INFO] Starting sensor dashboard on port 8080")
    app.run(host="0.0.0.0", port=8080, debug=True)
