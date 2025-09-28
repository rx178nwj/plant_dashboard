# blueprints/management/routes.py
from flask import Blueprint, render_template, jsonify, request, Response
import device_manager as dm
import uuid
import json
from blueprints.dashboard.routes import requires_auth
from ble_manager import PlantDeviceBLE
import asyncio

management_bp = Blueprint('management', __name__, template_folder='../../templates')

COMMAND_PIPE_PATH = "/tmp/plant_dashboard_cmd_pipe.jsonl"

@management_bp.route('/management')
@requires_auth
def management():
    """植物管理ページを表示します。"""
    conn = dm.get_db_connection()
    managed_plants = conn.execute("SELECT * FROM managed_plants").fetchall()
    plant_sensors = conn.execute("SELECT device_id, device_name FROM devices WHERE device_type = 'plant_sensor'").fetchall()
    switchbots = conn.execute("SELECT device_id, device_name FROM devices WHERE device_type LIKE 'switchbot_%'").fetchall()
    plant_library = conn.execute("SELECT plant_id, genus, species, variety FROM plants").fetchall()
    conn.close()
    
    return render_template('management.html', 
                           managed_plants=managed_plants,
                           plant_sensors=plant_sensors,
                           switchbots=switchbots,
                           plant_library=plant_library)

@management_bp.route('/watering-profiles')
@requires_auth
def watering_profiles():
    """水やり閾値設定ページを表示します。"""
    conn = dm.get_db_connection()
    plants_with_sensors = conn.execute("""
        SELECT
            mp.managed_plant_id,
            mp.plant_name,
            mp.assigned_plant_sensor_id
        FROM managed_plants mp
        WHERE mp.assigned_plant_sensor_id IS NOT NULL AND mp.assigned_plant_sensor_id != ''
        ORDER BY mp.plant_name
    """).fetchall()
    conn.close()
    return render_template('watering_profiles.html', plants_with_sensors=plants_with_sensors)

@management_bp.route('/api/device/<device_id>/write-watering-profile', methods=['POST'])
@requires_auth
def api_write_watering_profile(device_id):
    """
    指定されたデバイスに水やり閾値を書き込むためのコマンドを送信します。
    """
    data = request.json
    dry_threshold = data.get('dry_threshold')
    wet_threshold = data.get('wet_threshold')

    if dry_threshold is None or wet_threshold is None:
        return jsonify({'success': False, 'message': 'Missing threshold data.'}), 400

    command = {
        "command": "set_watering_thresholds",
        "device_id": device_id,
        "payload": {
            "dry_threshold": dry_threshold,
            "wet_threshold": wet_threshold
        }
    }

    try:
        # コマンドパイプにコマンドを追記
        with open(COMMAND_PIPE_PATH, "a") as f:
            f.write(json.dumps(command) + "\n")
        return jsonify({'success': True, 'message': 'Command sent to daemon.'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to write command to pipe: {e}'}), 500


@management_bp.route('/api/managed-plant-watering-profile/<managed_plant_id>', methods=['GET', 'POST'])
@requires_auth
def api_managed_plant_watering_profile(managed_plant_id):
    """特定の管理植物の水やり閾値を取得または更新します。"""
    conn = dm.get_db_connection()
    if request.method == 'POST':
        data = request.json
        try:
            conn.execute("""
                UPDATE managed_plants
                SET soil_moisture_dry_threshold_voltage = ?,
                    soil_moisture_wet_threshold_voltage = ?,
                    watering_days_fast_growth = ?,
                    watering_days_slow_growth = ?,
                    watering_days_hot_dormancy = ?,
                    watering_days_cold_dormancy = ?
                WHERE managed_plant_id = ?
            """, (
                data.get('soil_moisture_dry_threshold_voltage'),
                data.get('soil_moisture_wet_threshold_voltage'),
                data.get('watering_days_fast_growth'),
                data.get('watering_days_slow_growth'),
                data.get('watering_days_hot_dormancy'),
                data.get('watering_days_cold_dormancy'),
                managed_plant_id
            ))
            conn.commit()
            return jsonify({'success': True, 'message': 'Watering profile updated successfully.'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            conn.close()

    # GET request
    profile = conn.execute("""
        SELECT
            soil_moisture_dry_threshold_voltage,
            soil_moisture_wet_threshold_voltage,
            watering_days_fast_growth,
            watering_days_slow_growth,
            watering_days_hot_dormancy,
            watering_days_cold_dormancy
        FROM managed_plants
        WHERE managed_plant_id = ?
    """, (managed_plant_id,)).fetchone()
    conn.close()
    if profile:
        return jsonify(dict(profile))
    else:
        # Return empty object with default null values if no profile exists yet
        return jsonify({
            'soil_moisture_dry_threshold_voltage': None,
            'soil_moisture_wet_threshold_voltage': None,
            'watering_days_fast_growth': None,
            'watering_days_slow_growth': None,
            'watering_days_hot_dormancy': None,
            'watering_days_cold_dormancy': None
        })


@management_bp.route('/api/managed-plants', methods=['GET', 'POST'])
@requires_auth
def api_managed_plants():
    """管理対象の植物データを取得または保存します。"""
    conn = dm.get_db_connection()
    if request.method == 'POST':
        data = request.json
        managed_plant_id = data.get('managed_plant_id') or f"mp_{uuid.uuid4().hex[:8]}"
        
        cursor = conn.cursor()
        cursor.execute("SELECT managed_plant_id FROM managed_plants WHERE managed_plant_id = ?", (managed_plant_id,))
        exists = cursor.fetchone()

        # Include watering profile fields, defaulting to None if not provided
        params = (
            data.get('plant_name'), data.get('library_plant_id'), 
            data.get('assigned_plant_sensor_id'), data.get('assigned_switchbot_id'), 
            data.get('soil_moisture_dry_threshold_voltage'), data.get('soil_moisture_wet_threshold_voltage'),
            data.get('watering_days_fast_growth'), data.get('watering_days_slow_growth'),
            data.get('watering_days_hot_dormancy'), data.get('watering_days_cold_dormancy'),
            managed_plant_id
        )

        if exists:
            cursor.execute("""
                UPDATE managed_plants SET 
                    plant_name=?, library_plant_id=?, assigned_plant_sensor_id=?, assigned_switchbot_id=?,
                    soil_moisture_dry_threshold_voltage=?, soil_moisture_wet_threshold_voltage=?,
                    watering_days_fast_growth=?, watering_days_slow_growth=?,
                    watering_days_hot_dormancy=?, watering_days_cold_dormancy=?
                WHERE managed_plant_id=?
            """, params)
        else:
            cursor.execute("""
                INSERT INTO managed_plants (
                    plant_name, library_plant_id, assigned_plant_sensor_id, assigned_switchbot_id,
                    soil_moisture_dry_threshold_voltage, soil_moisture_wet_threshold_voltage,
                    watering_days_fast_growth, watering_days_slow_growth,
                    watering_days_hot_dormancy, watering_days_cold_dormancy,
                    managed_plant_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, params)
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'managed_plant_id': managed_plant_id})

    # GET request
    plants_list = conn.execute("SELECT * FROM managed_plants").fetchall()
    conn.close()
    return jsonify([dict(row) for row in plants_list])

@management_bp.route('/api/managed-plants/<managed_plant_id>', methods=['DELETE'])
@requires_auth
def api_delete_managed_plant(managed_plant_id):
    """管理対象の植物を削除します。"""
    try:
        conn = dm.get_db_connection()
        conn.execute("DELETE FROM managed_plants WHERE managed_plant_id = ?", (managed_plant_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Plant deleted successfully.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

