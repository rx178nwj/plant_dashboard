# blueprints/plants/routes.py
from flask import Blueprint, render_template, jsonify, request, current_app, url_for
import device_manager as dm
import json
import uuid
import os
import httpx 
from werkzeug.utils import secure_filename
from blueprints.dashboard.routes import requires_auth

plants_bp = Blueprint('plants', __name__, template_folder='../../templates')

@plants_bp.route('/plants')
@requires_auth
def plants():
    """植物ライブラリページを表示します。"""
    conn = dm.get_db_connection()
    rows = conn.execute("SELECT * FROM plants ORDER BY genus, species").fetchall()
    conn.close()
    
    plants_list = [dict(row) for row in rows]
    
    for plant in plants_list:
        if 'monthly_temps_json' in plant and plant['monthly_temps_json']:
            try:
                plant['monthly_temps'] = json.loads(plant['monthly_temps_json'])
            except json.JSONDecodeError:
                plant['monthly_temps'] = None
    
    plants_json = json.dumps(plants_list)
    return render_template('plants.html', plants=plants_list, plants_json=plants_json)

@plants_bp.route('/watering-profiles')
@requires_auth
def watering_profiles():
    """水やり閾値設定ページを表示します。"""
    conn = dm.get_db_connection()
    plants_with_sensors = conn.execute("""
        SELECT
            mp.managed_plant_id,
            mp.plant_name,
            mp.assigned_plant_sensor_id,
            p.plant_id as library_plant_id
        FROM managed_plants mp
        JOIN plants p ON mp.library_plant_id = p.plant_id
        WHERE mp.assigned_plant_sensor_id IS NOT NULL AND mp.assigned_plant_sensor_id != ''
        ORDER BY mp.plant_name
    """).fetchall()
    conn.close()
    return render_template('watering_profiles.html', plants_with_sensors=plants_with_sensors)


@plants_bp.route('/api/plant-watering-profile/<plant_id>', methods=['GET', 'POST'])
@requires_auth
def api_plant_watering_profile(plant_id):
    """特定の植物の水やり閾値を取得または更新します。"""
    conn = dm.get_db_connection()
    if request.method == 'POST':
        data = request.json
        try:
            conn.execute("""
                UPDATE plants
                SET soil_moisture_dry_threshold_voltage = ?,
                    soil_moisture_wet_threshold_voltage = ?,
                    watering_days_fast_growth = ?,
                    watering_days_slow_growth = ?,
                    watering_days_hot_dormancy = ?,
                    watering_days_cold_dormancy = ?
                WHERE plant_id = ?
            """, (
                data.get('soil_moisture_dry_threshold_voltage'),
                data.get('soil_moisture_wet_threshold_voltage'),
                data.get('watering_days_fast_growth'),
                data.get('watering_days_slow_growth'),
                data.get('watering_days_hot_dormancy'),
                data.get('watering_days_cold_dormancy'),
                plant_id
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
        FROM plants
        WHERE plant_id = ?
    """, (plant_id,)).fetchone()
    conn.close()
    if profile:
        return jsonify(dict(profile))
    else:
        return jsonify({}), 404

@plants_bp.route('/api/plants/upload-image', methods=['POST'])
@requires_auth
def api_upload_image():
    if 'plant-image-upload' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'}), 400
    file = request.files['plant-image-upload']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400

    allowed_extensions = current_app.config['ALLOWED_EXTENSIONS']
    if file and '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
        filename = secure_filename(f"plant_{uuid.uuid4().hex[:12]}.{file.filename.rsplit('.', 1)[1].lower()}")
        upload_folder = current_app.config['UPLOAD_FOLDER']
        
        os.makedirs(upload_folder, exist_ok=True)
        
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        
        file_url = url_for('static', filename=os.path.join('uploads/plant_images', filename))
        return jsonify({'success': True, 'url': file_url})
    else:
        return jsonify({'success': False, 'message': 'File type not allowed'}), 400


@plants_bp.route('/api/plants/lookup', methods=['POST'])
@requires_auth
def api_plant_lookup():
    """AIを使用して植物情報を検索します。"""
    data = request.json
    plant_name = f"{data.get('genus', '')} {data.get('species', '')} {data.get('variety', '')}".strip()
    if not plant_name:
        return jsonify({'success': False, 'message': 'Plant name is required.'}), 400

    try:
        prompt = f"""
        Search the web to find the most accurate and detailed information for the plant '{plant_name}'.
        Identify a single, representative native region. Provide monthly climate data for that region.
        Also, provide distinct temperature ranges for its fast growth, slow growth, hot dormancy, and cold dormancy periods.
        Provide separate watering instructions for each of these four periods.
        Also, find a representative, high-quality image of the plant from the web and provide a direct URL to it.
        I need all information in a structured JSON format. If a value is unknown, use null. All temperatures are in Celsius.

        JSON format: {{
          "origin_country": "string", "origin_region": "string",
          "monthly_temps": {{ "jan": {{"avg": integer, "high": integer, "low": integer}}, ...11 more months... }},
          "growing_fast_temp_high": integer, "growing_fast_temp_low": integer,
          "growing_slow_temp_high": integer, "growing_slow_temp_low": integer,
          "hot_dormancy_temp_high": integer, "hot_dormancy_temp_low": integer,
          "cold_dormancy_temp_high": integer, "cold_dormancy_temp_low": integer,
          "lethal_temp_high": integer, "lethal_temp_low": integer,
          "watering_growing": "string", "watering_slow_growing": "string",
          "watering_hot_dormancy": "string", "watering_cold_dormancy": "string",
          "image_url": "string (a direct URL to a representative image)"
        }}
        """
        api_key = current_app.config.get('GEMINI_API_KEY')
        if not api_key or api_key == 'YOUR_API_KEY_HERE':
            raise ValueError("Gemini API key is not configured")

        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"response_mime_type": "application/json"}}
        
        with httpx.Client(timeout=45.0) as client:
            response = client.post(api_url, json=payload)
            response.raise_for_status()
            result = response.json()

        content = result['candidates'][0]['content']['parts'][0]['text']
        if content.strip().startswith("```json"):
            content = content.strip()[7:-3]
        response_data = json.loads(content)

        image_url = response_data.get('image_url')
        if not image_url or image_url == 'null':
            response_data.pop('image_url', None)

        return jsonify({'success': True, 'data': response_data})
        
    except httpx.HTTPStatusError as e:
        return jsonify({'success': False, 'message': f'AI service returned an error: {e.response.status_code}'}), 500
    except (KeyError, IndexError, json.JSONDecodeError):
        return jsonify({'success': False, 'message': 'Could not parse Gemini API response.'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@plants_bp.route('/api/plants', methods=['GET', 'POST'])
@requires_auth
def api_plants():
    """植物ライブラリのデータを取得または保存します。"""
    conn = dm.get_db_connection()
    if request.method == 'POST':
        data = request.json
        plant_id = data.get('plant_id') or f"plant_{uuid.uuid4().hex[:8]}"
        monthly_temps_str = json.dumps(data.get('monthly_temps'))
        
        cursor = conn.cursor()
        cursor.execute("SELECT plant_id FROM plants WHERE plant_id = ?", (plant_id,))
        exists = cursor.fetchone()

        columns = [
            'genus', 'species', 'variety', 'image_url', 'origin_country', 'origin_region', 'monthly_temps_json',
            'growing_fast_temp_high', 'growing_fast_temp_low', 'growing_slow_temp_high', 'growing_slow_temp_low',
            'hot_dormancy_temp_high', 'hot_dormancy_temp_low', 'cold_dormancy_temp_high', 'cold_dormancy_temp_low',
            'lethal_temp_high', 'lethal_temp_low', 'watering_growing', 'watering_slow_growing',
            'watering_hot_dormancy', 'watering_cold_dormancy', 'soil_moisture_dry_threshold_voltage',
            'soil_moisture_wet_threshold_voltage', 
            'watering_days_fast_growth', 'watering_days_slow_growth', 
            'watering_days_hot_dormancy', 'watering_days_cold_dormancy'
        ]
        
        data['monthly_temps_json'] = monthly_temps_str
        
        if exists:
            set_clause = ", ".join([f"{col}=?" for col in columns])
            params = [data.get(col) for col in columns] + [plant_id]
            cursor.execute(f"UPDATE plants SET {set_clause} WHERE plant_id=?", params)
        else:
            all_columns = columns + ['plant_id']
            placeholders = ", ".join(["?" for _ in all_columns])
            params = [data.get(col) for col in columns] + [plant_id]
            cursor.execute(f"INSERT INTO plants ({', '.join(all_columns)}) VALUES ({placeholders})", params)
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'plant_id': plant_id})

    # GET request
    plants_list = conn.execute("SELECT * FROM plants ORDER BY genus, species").fetchall()
    conn.close()
    results = []
    for row in plants_list:
        plant_dict = dict(row)
        if plant_dict.get('monthly_temps_json'):
            plant_dict['monthly_temps'] = json.loads(plant_dict['monthly_temps_json'])
        results.append(plant_dict)
    return jsonify(results)

@plants_bp.route('/api/plants/<plant_id>', methods=['DELETE'])
@requires_auth
def delete_plant(plant_id):
    """植物ライブラリから植物を削除します。"""
    try:
        conn = dm.get_db_connection()
        conn.execute("DELETE FROM plants WHERE plant_id = ?", (plant_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Plant deleted successfully.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

