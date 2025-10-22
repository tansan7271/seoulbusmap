import requests
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from main.models import BusStop
import time

class Command(BaseCommand):
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('[fetch_busstop_data] 버스 정류장 정보 수집을 시작합니다...'))

        # 1. 모든 정류장을 비활성 상태로 초기화
        self.stdout.write('[fetch_busstop_data] 기존 모든 정류장을 비활성 상태로 초기화합니다...')
        num_deactivated = BusStop.objects.all().update(is_active=False)
        self.stdout.write(f'[fetch_busstop_data] 총 {num_deactivated}개의 정류장을 비활성 처리했습니다.')

        try:
            api_key = settings.SEOUL_API_KEY
            service_name = 'busStopLocationXyInfo'
            data_type = 'json'
            
            # 2. 전체 데이터 개수 확인을 위한 최초 호출
            url = f'http://openapi.seoul.go.kr:8088/{api_key}/{data_type}/{service_name}/1/1/'
            response = requests.get(url, timeout=10)
            response.raise_for_status() # 요청 실패 시 예외 발생
            
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
                
                url = f'http://openapi.seoul.go.kr:8088/{api_key}/{data_type}/{service_name}/{start_index}/{end_index}/'
                response = requests.get(url, timeout=10)
                response.raise_for_status()

                stop_data = response.json()
                rows = stop_data[service_name].get('row', [])

                for row in rows:
                    # update_or_create: busstop_id가 존재하면 업데이트, 없으면 새로 생성
                    # 이 때, is_active를 True로 설정하여 활성 상태로 만듭니다.
                    BusStop.objects.update_or_create(
                        busstop_id=row['STOPS_NO'],
                        defaults={
                            'name': row['STOPS_NM'],
                            'longitude': row['XCRD'],
                            'latitude': row['YCRD'],
                            'is_active': True
                        }
                    )
                    processed_count += 1
                
                # API 과부하 방지를 위한 딜레이
                time.sleep(0.1)

            self.stdout.write(self.style.SUCCESS(f'[fetch_busstop_data] 총 {processed_count}개의 버스 정류장 정보를 성공적으로 처리했습니다.'))

        except Exception as e:
            raise CommandError(f'[fetch_busstop_data] 버스 정류장 처리 중 오류 발생: {e}')