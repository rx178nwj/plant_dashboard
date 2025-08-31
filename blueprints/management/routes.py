# blueprints/management/routes.py
from flask import Blueprint, render_template, jsonify, request
import device_manager as dm
import uuid
from blueprints.dashboard.routes import requires_auth

management_bp = Blueprint('management', __name__, template_folder='../../templates')

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

        params = (
            data.get('plant_name'), data.get('library_plant_id'), 
            data.get('assigned_plant_sensor_id'), data.get('assigned_switchbot_id'), 
            managed_plant_id
        )

        if exists:
            cursor.execute("""
                UPDATE managed_plants SET plant_name=?, library_plant_id=?, assigned_plant_sensor_id=?, assigned_switchbot_id=?
                WHERE managed_plant_id=?
            """, params)
        else:
            cursor.execute("""
                INSERT INTO managed_plants (plant_name, library_plant_id, assigned_plant_sensor_id, assigned_switchbot_id, managed_plant_id)
                VALUES (?, ?, ?, ?, ?)
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