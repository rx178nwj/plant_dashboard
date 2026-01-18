#!/usr/bin/env python3
"""
Temporary script to populate data_version column in devices table.
- Devices with name starting with 'PlantMonitor_30_' get data_version=2
- All other devices get data_version=1
"""

import sqlite3
import logging
from config import DATABASE_PATH

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def update_data_version():
    """Update data_version for all existing devices based on device_name pattern."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # Get all devices
        cursor.execute("SELECT device_id, device_name, data_version FROM devices")
        devices = cursor.fetchall()

        logger.info(f"Found {len(devices)} devices in database")

        updated_v2 = 0
        updated_v1 = 0

        for device_id, device_name, current_version in devices:
            # Determine data_version based on device_name
            if device_name and device_name.startswith('PlantMonitor_30_'):
                new_version = 2
            else:
                new_version = 1

            # Update if different or NULL
            if current_version != new_version:
                cursor.execute(
                    "UPDATE devices SET data_version = ? WHERE device_id = ?",
                    (new_version, device_id)
                )
                logger.info(f"Updated device '{device_name}' (ID: {device_id}): data_version = {new_version}")

                if new_version == 2:
                    updated_v2 += 1
                else:
                    updated_v1 += 1

        conn.commit()
        logger.info(f"Update complete: {updated_v2} devices set to v2, {updated_v1} devices set to v1")

        # Show final status
        cursor.execute("""
            SELECT data_version, COUNT(*)
            FROM devices
            GROUP BY data_version
            ORDER BY data_version
        """)
        summary = cursor.fetchall()

        logger.info("Current data_version distribution:")
        for version, count in summary:
            version_label = version if version is not None else "NULL"
            logger.info(f"  data_version {version_label}: {count} device(s)")

    except Exception as e:
        logger.error(f"Error updating data_version: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    update_data_version()
