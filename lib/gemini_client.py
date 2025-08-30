# plant_dashboard/gemini_client.py

import httpx
import asyncio
import json
import logging
from flask import current_app

logger = logging.getLogger(__name__)

async def lookup_plant_info(plant_name: str) -> dict:
    """
    Gemini APIを使用して植物の情報を検索し、JSON形式で返す。

    Args:
        plant_name: 検索する植物名

    Returns:
        APIから返された植物情報の辞書

    Raises:
        ValueError: APIキーが設定されていない場合や、APIからのレスポンスが無効な場合
    """
    # config.py経由で環境変数からAPIキーを取得
    api_key = current_app.config.get('GEMINI_API_KEY')
    if not api_key:
        logger.error("Gemini API key is not configured. Please set GEMINI_API_KEY in your .env file.")
        # ユーザーに表示するエラーメッセージ
        raise ValueError("The AI search feature is not configured on the server.")

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}"
    
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
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(api_url, json=payload)
            response.raise_for_status()
            result = response.json()
            
            content_part = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0]
            content_text = content_part.get('text', '')
            
            if not content_text:
                raise ValueError("Received an empty response from the AI service.")
                
            if content_text.strip().startswith("```json"):
                content_text = content_text.strip()[7:-3]
            
            return json.loads(content_text)

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error occurred while calling Gemini API: {e.response.status_code} - {e.response.text}")
        raise ValueError(f"Failed to communicate with the AI service (HTTP {e.response.status_code}).")
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        logger.error(f"Failed to parse Gemini API response: {e}. Full response: {result}")
        raise ValueError("The AI service returned an unexpected response format.")
    except Exception as e:
        logger.error(f"An unexpected error occurred in lookup_plant_info: {e}")
        raise ValueError("An unexpected error occurred while contacting the AI service.")
