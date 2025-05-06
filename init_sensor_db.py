#!/usr/bin/env python3
import sqlite3
import os

# Paths relative to project root
DB_PATH = os.path.join(os.path.dirname(__file__), "sensor_data.db")

def initialize_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS raw_sensor_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sensor_id INTEGER NOT NULL,
        room TEXT NOT NULL,
        sensor_type TEXT NOT NULL CHECK(sensor_type IN ('temperature', 'brightness', 'motion')),
        value REAL,
        timestamp DATETIME NOT NULL,
        raw_log_line TEXT
    )''')
    
    # Indexes
    c.execute('''CREATE INDEX IF NOT EXISTS idx_sensor_timestamp ON raw_sensor_data(timestamp)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_sensor_room ON raw_sensor_data(room)''')
    
    # Retention policy
    c.execute('''CREATE TABLE IF NOT EXISTS retention_policy (
        policy_name TEXT PRIMARY KEY,
        retention_days INTEGER NOT NULL
    )''')
    c.execute('''INSERT OR IGNORE INTO retention_policy VALUES ('default', 90)''')
    
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

if __name__ == "__main__":
    initialize_db()
