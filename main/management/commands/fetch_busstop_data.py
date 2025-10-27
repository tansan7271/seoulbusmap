import requests
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from main.models import BusStop, BusStopHistory
import time

class Command(BaseCommand):
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('[fetch_busstop_data] 버스 정류장 정보 수집 및 아카이빙을 시작합니다...'))

        try:
            seoul_api_key = settings.SEOUL_API_KEY
            kakao_api_key = settings.KAKAO_API_KEY
            service_name = 'busStopLocationXyInfo'
            data_type = 'json'

            # --- 1단계: API에서 모든 최신 정류장 정보 수집 ---
            self.stdout.write('[fetch_busstop_data] API에서 최신 정류장 정보를 수집합니다...')
            url = f'http://openapi.seoul.go.kr:8088/{seoul_api_key}/{data_type}/{service_name}/1/1/'
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            total_count = data[service_name]['list_total_count']
            self.stdout.write(f'[fetch_busstop_data] 총 {total_count}개의 정류장 정보가 있습니다.')

            api_rows = []
            batch_size = 1000
            for start in range(1, total_count + 1, batch_size):
                end = start + batch_size - 1
                if end > total_count: end = total_count
                self.stdout.write(f'[fetch_busstop_data] {start}~{end} 정보 수집 중...')
                api_url = f'http://openapi.seoul.go.kr:8088/{seoul_api_key}/{data_type}/{service_name}/{start}/{end}/'
                api_response = requests.get(api_url, timeout=30)
                api_response.raise_for_status()
                api_rows.extend(api_response.json()[service_name].get('row', []))
                time.sleep(0.1)
            
            api_stops = {row['NODE_ID']: row for row in api_rows}

            # --- 2단계: 데이터 비교, 아카이빙, 및 업데이트 ---
            self.stdout.write('[fetch_busstop_data] 데이터 비교, 아카이빙, 업데이트를 시작합니다...')
            existing_stops = {s.busstop_id: s for s in BusStop.objects.all()}
            all_stop_ids = set(existing_stops.keys()) | set(api_stops.keys())

            to_create = []
            to_update = []
            to_archive = []

            for stop_id in all_stop_ids:
                stop = existing_stops.get(stop_id)
                api_data = api_stops.get(stop_id)

                if stop and not api_data:
                    # C (비활성화): DB에는 있지만 API에는 없는 경우
                    if stop.is_active:
                        to_archive.append(BusStopHistory(busstop_id=stop.busstop_id, name=stop.name, longitude=stop.longitude, latitude=stop.latitude, district_id=stop.district_id, is_active=stop.is_active))
                        stop.is_active = False
                        to_update.append(stop)
                
                elif not stop and api_data:
                    # B (신규 추가): API에는 있지만 DB에는 없는 경우
                    new_stop = BusStop(busstop_id=api_data['NODE_ID'], name=api_data['STOPS_NM'], longitude=api_data['XCRD'], latitude=api_data['YCRD'], is_active=True)
                    to_create.append(new_stop)

                elif stop and api_data:
                    # A (정보 변경): 둘 다 있는 경우
                    name_changed = stop.name != api_data['STOPS_NM']
                    reactivated = not stop.is_active

                    if name_changed or reactivated:
                        to_archive.append(BusStopHistory(busstop_id=stop.busstop_id, name=stop.name, longitude=stop.longitude, latitude=stop.latitude, district_id=stop.district_id, is_active=stop.is_active))
                        stop.name = api_data['STOPS_NM']
                        stop.is_active = True
                        to_update.append(stop)

            if to_archive:
                BusStopHistory.objects.bulk_create(to_archive)
                self.stdout.write(self.style.SUCCESS(f'[fetch_busstop_data] {len(to_archive)}개의 변경 전 데이터를 아카이빙했습니다.'))
            
            if to_create:
                BusStop.objects.bulk_create(to_create)
                self.stdout.write(self.style.SUCCESS(f'[fetch_busstop_data] {len(to_create)}개의 신규 정류장을 추가했습니다.'))

            if to_update:
                BusStop.objects.bulk_update(to_update, ['name', 'is_active'])
                self.stdout.write(self.style.SUCCESS(f'[fetch_busstop_data] {len(to_update)}개의 정류장 정보를 업데이트했습니다.'))

            if not any([to_archive, to_create, to_update]):
                self.stdout.write(self.style.SUCCESS('[fetch_busstop_data] 변경된 데이터가 없어, 모든 데이터가 최신 상태입니다.'))

            # --- 3단계: 행정동 코드 업데이트 (카카오 API) ---
            # 행정동 코드가 비어있는 정류장에 대해서만 실행
            self.stdout.write('[fetch_busstop_data] 행정동 코드 업데이트를 시작합니다...')
            stops_to_geocode = BusStop.objects.filter(district_id__isnull=True)
            self.stdout.write(f'[fetch_busstop_data] 총 {stops_to_geocode.count()}개의 정류장에 대해 행정동 코드 매칭을 시도합니다.')
            
            for i, stop in enumerate(stops_to_geocode):
                try:
                    headers = {'Authorization': f'KakaoAK {kakao_api_key}'}
                    params = {'x': stop.longitude, 'y': stop.latitude}
                    kakao_api_url = 'https://dapi.kakao.com/v2/local/geo/coord2regioncode.json'
                    
                    kakao_response = requests.get(kakao_api_url, headers=headers, params=params, timeout=5)
                    kakao_response.raise_for_status()
                    kakao_data = kakao_response.json()
                    
                    for doc in kakao_data['documents']:
                        if doc['region_type'] == 'H':
                            stop.district_id = doc['code'][:-2]
                            stop.save()
                            self.stdout.write(f'[fetch_busstop_data] {i+1}: {stop.name}의 행정동 코드를 {stop.district_id}로 업데이트했습니다.')
                            break
                    time.sleep(0.01)
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'[fetch_busstop_data] 정류장 {stop.busstop_id}의 행정동 코드 변환 중 오류: {e}'))

        except Exception as e:
            raise CommandError(f'[fetch_busstop_data] 전체 작업 중 오류 발생: {e}')