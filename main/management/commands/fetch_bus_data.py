import requests
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from main.models import BusStop
import time

class Command(BaseCommand):
    help = '서울시 공공데이터 포털에서 버스 정류장 위치 정보를 수집하여 데이터베이스에 저장합니다.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('버스 정류장 정보 수집을 시작합니다...'))

        try:
            api_key = settings.SEOUL_API_KEY
            service_name = 'busStopLocationXyInfo'
            data_type = 'json'
            
            # 1. 전체 데이터 개수 확인을 위한 최초 호출
            url = f'http://openapi.seoul.go.kr:8088/{api_key}/{data_type}/{service_name}/1/1/'
            response = requests.get(url, timeout=10)
            response.raise_for_status() # 요청 실패 시 예외 발생
            
            data = response.json()
            total_count = data[service_name]['list_total_count']
            self.stdout.write(f'총 {total_count}개의 정류장 정보가 있습니다.')

            # 2. 페이지네이션을 통한 전체 데이터 수집
            batch_size = 1000 # 한 번에 1000개씩 요청
            processed_count = 0
            for start_index in range(1, total_count + 1, batch_size):
                end_index = start_index + batch_size - 1
                if end_index > total_count:
                    end_index = total_count
                
                self.stdout.write(f'{start_index}부터 {end_index}까지의 정류장 정보를 수집합니다...')
                
                url = f'http://openapi.seoul.go.kr:8088/{api_key}/{data_type}/{service_name}/{start_index}/{end_index}/'
                response = requests.get(url, timeout=10)
                response.raise_for_status()

                stop_data = response.json()
                rows = stop_data[service_name].get('row', [])

                for row in rows:
                    # update_or_create: api_id가 존재하면 업데이트, 없으면 새로 생성
                    BusStop.objects.update_or_create(
                        api_id=row['STOPS_NO'],
                        defaults={
                            'name': row['STOPS_NM'],
                            'longitude': row['XCRD'],
                            'latitude': row['YCRD'],
                        }
                    )
                    processed_count += 1
                
                # API 과부하 방지를 위한 약간의 딜레이
                time.sleep(0.1)

            self.stdout.write(self.style.SUCCESS(f'총 {processed_count}개의 정류장 정보를 성공적으로 처리했습니다.'))

        except requests.exceptions.RequestException as e:
            raise CommandError(f'API 요청 중 오류 발생: {e}')
        except KeyError as e:
            raise CommandError(f'응답 데이터에서 예상치 못한 키를 발견했습니다: {e}')
        except Exception as e:
            raise CommandError(f'알 수 없는 오류 발생: {e}')