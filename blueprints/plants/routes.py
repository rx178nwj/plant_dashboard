# blueprints/plants/routes.py
from flask import Blueprint, render_template, jsonify, request, current_app
import device_manager as dm
import json
import uuid
import httpx
import asyncio
from blueprints.dashboard.routes import requires_auth

plants_bp = Blueprint('plants', __name__, template_folder='../../templates', static_folder='../../static')

@plants_bp.route('/plants')
@requires_auth
def plants():
    """植物ライブラリページを表示します。"""
    return render_template('plants.html')

@plants_bp.route('/api/plants/lookup', methods=['POST'])
@requires_auth
def api_plant_lookup():
    """AIを使用して植物情報を検索します。"""
    data = request.json
    plant_name = f"{data.get('genus', '')} {data.get('species', '')} {data.get('variety', '')}".strip()
    if not plant_name:
        return jsonify({'success': False, 'message': 'Plant name is required.'}), 400

    async def get_lookup_data():
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
        api_key = current_app.config['GEMINI_API_KEY']
        if not api_key or api_key == 'YOUR_API_KEY_HERE':
            raise ValueError("Gemini API key is not configured")
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"response_mime_type": "application/json"}}
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(api_url, json=payload)
            response.raise_for_status()
            result = response.json()
            try:
                content = result['candidates'][0]['content']['parts'][0]['text']
                if content.strip().startswith("```json"):
                    content = content.strip()[7:-3]
                return json.loads(content)
            except (KeyError, IndexError, json.JSONDecodeError):
                raise ValueError("Could not parse Gemini API response.")
    try:
        response_data = asyncio.run(get_lookup_data())
        return jsonify({'success': True, 'data': response_data})
    except Exception as e:
        # logger.error(f"Plant lookup failed: {e}")
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
            cursor.execute("""
                UPDATE plants SET genus=?, species=?, variety=?, image_url=?, origin_country=?, origin_region=?, monthly_temps_json=?, 
                growing_fast_temp_high=?, growing_fast_temp_low=?, growing_slow_temp_high=?, growing_slow_temp_low=?, 
                hot_dormancy_temp_high=?, hot_dormancy_temp_low=?, cold_dormancy_temp_high=?, cold_dormancy_temp_low=?, 
                lethal_temp_high=?, lethal_temp_low=?, watering_growing=?, watering_slow_growing=?, watering_hot_dormancy=?, watering_cold_dormancy=?
                WHERE plant_id=?
            """, params)
        else:
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
