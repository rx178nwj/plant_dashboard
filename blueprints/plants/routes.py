# blueprints/plants/routes.py
from flask import Blueprint, render_template, jsonify, request, current_app, url_for
import device_manager as dm
import json
import uuid
import os
from werkzeug.utils import secure_filename
from lib.gemini_client import lookup_plant_info
from blueprints.dashboard.routes import requires_auth
import asyncio # AI検索のためにインポート

plants_bp = Blueprint('plants', __name__, template_folder='../../templates')

@plants_bp.route('/plants')
@requires_auth
def plants():
    """植物ライブラリページを表示します。"""
    conn = dm.get_db_connection()
    rows = conn.execute("SELECT * FROM plants ORDER BY genus, species").fetchall()
    conn.close()
    
    # DBから取得したデータを辞書のリストに変換
    plants_list = [dict(row) for row in rows]
    
    # 埋め込み用JSONデータを作成（ネストされたJSON文字列をオブジェクトに変換）
    for plant in plants_list:
        if 'monthly_temps_json' in plant and plant['monthly_temps_json']:
            try:
                plant['monthly_temps'] = json.loads(plant['monthly_temps_json'])
            except json.JSONDecodeError:
                plant['monthly_temps'] = None # パース失敗時はnullにする
    
    # テンプレートにリストとJSONの両方を渡す
    plants_json = json.dumps(plants_list)
    return render_template('plants.html', plants=plants_list, plants_json=plants_json)

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
        
        # Make sure the upload folder exists
        os.makedirs(upload_folder, exist_ok=True)
        
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        
        # Return the URL to the uploaded file
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
        # gemini_clientから関数を呼び出す
        response_data = asyncio.run(lookup_plant_info(plant_name))
        return jsonify({'success': True, 'data': response_data})
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
        
        params = (
            data.get('genus'), data.get('species'), data.get('variety'), data.get('image_url'),
            data.get('origin_country'), data.get('origin_region'), monthly_temps_str,
            data.get('growing_fast_temp_high'), data.get('growing_fast_temp_low'),
            data.get('growing_slow_temp_high'), data.get('growing_slow_temp_low'),
            data.get('hot_dormancy_temp_high'), data.get('hot_dormancy_temp_low'),
            data.get('cold_dormancy_temp_high'), data.get('cold_dormancy_temp_low'),
            data.get('lethal_temp_high'), data.get('lethal_temp_low'),
            data.get('watering_growing'), data.get('watering_slow_growing'),
            data.get('watering_hot_dormancy'), data.get('watering_cold_dormancy'),
            plant_id
        )

        if exists:
            # Update
            cursor.execute("""
                UPDATE plants SET genus=?, species=?, variety=?, image_url=?, origin_country=?, origin_region=?, monthly_temps_json=?, 
                growing_fast_temp_high=?, growing_fast_temp_low=?, growing_slow_temp_high=?, growing_slow_temp_low=?, 
                hot_dormancy_temp_high=?, hot_dormancy_temp_low=?, cold_dormancy_temp_high=?, cold_dormancy_temp_low=?, 
                lethal_temp_high=?, lethal_temp_low=?, watering_growing=?, watering_slow_growing=?, watering_hot_dormancy=?, watering_cold_dormancy=?
                WHERE plant_id=?
            """, params)
        else:
            # Insert
            cursor.execute("""
                INSERT INTO plants (genus, species, variety, image_url, origin_country, origin_region, monthly_temps_json, 
                growing_fast_temp_high, growing_fast_temp_low, growing_slow_temp_high, growing_slow_temp_low, 
                hot_dormancy_temp_high, hot_dormancy_temp_low, cold_dormancy_temp_high, cold_dormancy_temp_low, 
                lethal_temp_high, lethal_temp_low, watering_growing, watering_slow_growing, watering_hot_dormancy, watering_cold_dormancy, plant_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, params)
        
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