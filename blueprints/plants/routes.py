# blueprints/plants/routes.py
from flask import Blueprint, render_template, jsonify, request, current_app, url_for
import device_manager as dm
import json
import uuid
import os
import httpx # httpxをインポート
from werkzeug.utils import secure_filename
# from lib.gemini_client import lookup_plant_info # 不要になったため削除
from blueprints.dashboard.routes import requires_auth
# import asyncio # 不要になったため削除

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
        
        # 同期httpxクライアントを使用
        with httpx.Client(timeout=45.0) as client:
            response = client.post(api_url, json=payload)
            response.raise_for_status()
            result = response.json()

        # 結果をパース
        content = result['candidates'][0]['content']['parts'][0]['text']
        if content.strip().startswith("```json"):
            content = content.strip()[7:-3]
        response_data = json.loads(content)

        # AIが有効な画像URLを返さなかった場合（Noneや文字列"null"の場合を含む）、
        # image_urlキーを削除してフロントエンドで既存の画像が上書きされないようにする
        image_url = response_data.get('image_url')
        if not image_url or image_url == 'null':
            response_data.pop('image_url', None)

        return jsonify({'success': True, 'data': response_data})
        
    except httpx.HTTPStatusError as e:
        # より具体的なエラーハンドリング
        return jsonify({'success': False, 'message': f'AI service returned an error: {e.response.status_code}'}), 500
    except (KeyError, IndexError, json.JSONDecodeError):
        return jsonify({'success': False, 'message': 'Could not parse Gemini API response.'}), 500
    except Exception as e:
        # 一般的な例外
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

