import requests
from datetime import datetime
from .env import *
from .models import AirQualityData

def fetch_air_data():
    try:
        headers = {
            # 내 존재 뻥침. 난 파폭이에요~ 난. 사파리에요~
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        params = {
            'returnType': 'json',
            'numOfRows': 1,
            'pageNo': 1,
            'stationName': '공도읍',
            'dataTerm': 'DAILY',
            'ver': '1.0',
            'serviceKey': WEATHER_API_KEY  # requests가 자동으로 인코딩
        }
        
        response = requests.get(WEATHER_API_ENDPOINT, 
                                headers=headers,
                                params=params, 
                                timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print(f"API 응답 성공: {data}")
            return parse_air_data(data)
        else:
            print(f"API 요청 실패: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"Error: {e}")
        return None

def parse_air_data(raw_data):
    try:
        body = raw_data.get('response', {}).get('body', {})
        items = body.get('items', [])
        
        if not items:
            print("No data in response")
            return None
            
        item = items[0] 
        
        data_time_str = item.get('dataTime', '')
        data_time = datetime.strptime(data_time_str, '%Y-%m-%d %H:%M') 
    
        parsed_data = {
            'pm10_value': float(item.get('pm10Value')),
            'pm25_value': float(item.get('pm25Value')), 
            'o3_value': float(item.get('o3Value')),
            'no2_value': float(item.get('no2Value')),
            'data_time': data_time, 
        }
        return parsed_data
            
    except Exception as e:
        print(f"Error while parsing: {e}")
        return None

def save_air_data():
    data = fetch_air_data()
    if not data:
        print("Data collection failure")
        return False
    
    if not AirQualityData.time_exists(data['data_time']):
        try:
            AirQualityData.objects.create(**data)
            print(f"New data saved: {data['data_time']}")
            return True
        except Exception as e:
            print(f"Error while saving: {e}")
            return False
    else:
        print(f"Already exists: {data['data_time']}")
        return False