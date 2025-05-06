PRAGMA foreign_keys=off;

BEGIN TRANSACTION;

-- Step 1: Drop old indexes (if they exist)
DROP INDEX IF EXISTS idx_sensor_timestamp;
DROP INDEX IF EXISTS idx_sensor_room;

-- Step 2: Rename the old table
ALTER TABLE raw_sensor_data RENAME TO raw_sensor_data_old;

-- Step 3: Create the new table
CREATE TABLE raw_sensor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id TEXT NOT NULL,
    room TEXT NOT NULL,
    sensor_type TEXT NOT NULL CHECK(sensor_type IN ('temperature', 'brightness', 'motion', 'open')),
    value REAL,
    timestamp DATETIME NOT NULL,
    raw_log_line TEXT
);

-- Step 4: Copy data over
INSERT INTO raw_sensor_data (id, sensor_id, room, sensor_type, value, timestamp, raw_log_line)
SELECT id, sensor_id, room, sensor_type, value, timestamp, raw_log_line
FROM raw_sensor_data_old;

-- Step 5: Recreate indexes
CREATE INDEX idx_sensor_timestamp ON raw_sensor_data(timestamp);
CREATE INDEX idx_sensor_room ON raw_sensor_data(room);

-- Step 6: Drop old table
DROP TABLE raw_sensor_data_old;

COMMIT;

PRAGMA foreign_keys=on;

