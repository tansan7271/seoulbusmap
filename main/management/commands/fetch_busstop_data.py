import requests
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from main.models import BusStop, HangJeongDong
import time

class Command(BaseCommand):
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('[fetch_busstop_data] 버스 정류장 정보 수집 및 행정동 코드 매칭을 시작합니다...'))

        # 1. 모든 정류장을 비활성 상태로 초기화
        self.stdout.write('[fetch_busstop_data] 기존 모든 정류장을 비활성 상태로 초기화합니다...')
        num_deactivated = BusStop.objects.all().update(is_active=False)
        self.stdout.write(f'[fetch_busstop_data] 총 {num_deactivated}개의 정류장을 비활성 처리했습니다.')

        try:
            seoul_api_key = settings.SEOUL_API_KEY
            kakao_api_key = settings.KAKAO_API_KEY
            service_name = 'busStopLocationXyInfo'
            data_type = 'json'
            
            # 2. 전체 데이터 개수 확인을 위한 최초 호출
            url = f'http://openapi.seoul.go.kr:8088/{seoul_api_key}/{data_type}/{service_name}/1/1/'
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            total_count = data[service_name]['list_total_count']
            self.stdout.write(f'[fetch_busstop_data] 총 {total_count}개의 버스 정류장 정보가 있습니다.')

            # 3. 페이지네이션을 통한 전체 데이터 수집 및 활성 상태 업데이트
            batch_size = 1000 # 한 번에 1000개씩 요청
            processed_count = 0
            for start_index in range(1, total_count + 1, batch_size):
                end_index = start_index + batch_size - 1
                if end_index > total_count:
                    end_index = total_count
                
                self.stdout.write(f'[fetch_busstop_data] {start_index}부터 {end_index}까지의 정류장 정보를 수집합니다...')
                
                url = f'http://openapi.seoul.go.kr:8088/{seoul_api_key}/{data_type}/{service_name}/{start_index}/{end_index}/'
                seoul_api_response = requests.get(url, timeout=10)
                seoul_api_response.raise_for_status()

                stop_data = seoul_api_response.json()
                rows = stop_data[service_name].get('row', [])

                for row in rows:
                    bus_stop, created = BusStop.objects.update_or_create(
                        busstop_id=row['STOPS_NO'],
                        defaults={
                            'name': row['STOPS_NM'],
                            'longitude': row['XCRD'],
                            'latitude': row['YCRD'],
                            'is_active': True
                        }
                    )
                    processed_count += 1

                    # 4. 카카오 API를 이용해 행정동 코드(district_id) 업데이트
                    try:
                        headers = {'Authorization': f'KakaoAK {kakao_api_key}'}
                        params = {'x': bus_stop.longitude, 'y': bus_stop.latitude}
                        kakao_api_url = 'https://dapi.kakao.com/v2/local/geo/coord2regioncode.json'
                        
                        kakao_response = requests.get(kakao_api_url, headers=headers, params=params, timeout=5)
                        kakao_response.raise_for_status()
                        
                        kakao_data = kakao_response.json()
                        
                        # 행정동(region_type='H') 정보만 필터링
                        for doc in kakao_data['documents']:
                            if doc['region_type'] == 'H':
                                bus_stop.district_id = doc['code'][:-2]
                                bus_stop.save()
                                self.stdout.write(f'[fetch_busstop_data] {processed_count}: {bus_stop.name}의 지도상 위치는 {bus_stop.district_id}에 속함을 알아냈습니다.')
                                break # 첫 번째 행정동 정보만 사용
                        
                        # API 과부하 방지를 위한 딜레이
                        time.sleep(0.0001)

                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'[fetch_busstop_data] 정류장 {bus_stop.busstop_id}의 행정동 코드 변환 중 오류 발생: {e}'))

                
            self.stdout.write(self.style.SUCCESS(f'[fetch_busstop_data] 총 {processed_count}개의 버스 정류장 정보를 성공적으로 처리했습니다.'))

        except Exception as e:
            raise CommandError(f'[fetch_busstop_data] 전체 작업 중 오류 발생: {e}')