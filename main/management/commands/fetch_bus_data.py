import requests
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from main.models import BusData, BusDataHistory
from datetime import datetime, timedelta
import time

class Command(BaseCommand):
    """
    서울시 버스 노선/정류장별 일일 승하차 인원 정보를 수집하는 Django management command.
    """
    help = '일별 버스 노선/정류장별 승하차 인원 정보를 수집합니다.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('[fetch_bus_data] 승하차 인원 정보 수집을 시작합니다.'))

        try:
            api_key = settings.SEOUL_API_KEY
            service_name = 'CardBusStatisticsServiceNew'
            data_type = 'json'

            # 1. 최신 데이터가 있는 날짜 탐색 (최대 7일 전까지)
            target_date = None
            initial_response = None
            for i in range(1, 8):
                date_to_check = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
                self.stdout.write(f'[fetch_bus_data] {date_to_check} 날짜의 데이터 존재 여부를 확인합니다...')
                check_url = f'http://openapi.seoul.go.kr:8088/{api_key}/{data_type}/{service_name}/1/1/{date_to_check}'
                response = requests.get(check_url, timeout=10)
                if response.ok and service_name in response.json() and 'row' in response.json()[service_name]:
                    target_date = date_to_check
                    initial_response = response
                    self.stdout.write(self.style.SUCCESS(f'[fetch_bus_data] 데이터 수집 대상 날짜를 {target_date}로 확정했습니다.'))
                    break
                time.sleep(0.5)

            if not target_date:
                self.stdout.write(self.style.WARNING('[fetch_bus_data] 최근 7일 내에 유효한 데이터가 없어 작업을 종료합니다.'))
                return

            # 2. 기존 데이터 아카이빙 및 삭제
            self.stdout.write('[fetch_bus_data] 기존 데이터 아카이빙을 시작합니다...')
            records_to_archive = BusData.objects.all()
            if records_to_archive.exists():
                history_batch = [
                    BusDataHistory(
                        bus_id=record.bus_id,
                        busstop_id=record.busstop_id,
                        timestamp=record.timestamp,
                        passengers_on=record.passengers_on,
                        passengers_off=record.passengers_off,
                    )
                    for record in records_to_archive
                ]
                BusDataHistory.objects.bulk_create(history_batch)
                self.stdout.write(f'[fetch_bus_data] {len(history_batch)}건의 데이터를 BusDataHistory 테이블로 이동했습니다.')
                
                deleted_count, _ = records_to_archive.delete()
                self.stdout.write(f'[fetch_bus_data] {deleted_count}건의 데이터를 BusData 테이블에서 삭제했습니다.')
            else:
                self.stdout.write('[fetch_bus_data] 아카이빙할 기존 데이터가 없습니다.')


            # 3. 전체 데이터 수집
            aware_datetime = timezone.make_aware(datetime.strptime(target_date, '%Y%m%d'))
            data = initial_response.json()
            total_count = data[service_name]['list_total_count']
            self.stdout.write(f'[fetch_bus_data] 총 {total_count}개의 신규 승하차 데이터를 수집합니다.')

            batch_size = 1000
            processed_count = 0
            for start in range(1, total_count + 1, batch_size):
                end = start + batch_size - 1
                if end > total_count: end = total_count
                self.stdout.write(f'[fetch_bus_data] {start}~{end} 정보 수집 중...')
                
                url = f'http://openapi.seoul.go.kr:8088/{api_key}/{data_type}/{service_name}/{start}/{end}/{target_date}'
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                rows = response.json()[service_name].get('row', [])
                
                bus_data_batch = []
                for row in rows:
                    if not row.get('RTE_ID') or not row.get('STOPS_ID'):
                        continue

                    bus_data_batch.append(BusData(
                        bus_id=row['RTE_ID'],
                        busstop_id=row['STOPS_ID'],
                        timestamp=aware_datetime,
                        passengers_on=row['GTON_TNOPE'],
                        passengers_off=row['GTOFF_TNOPE'],
                    ))
                
                BusData.objects.bulk_create(bus_data_batch)
                processed_count += len(bus_data_batch)
                time.sleep(0.1)

            self.stdout.write(self.style.SUCCESS(f'[fetch_bus_data] 총 {processed_count}개의 승하차 정보를 성공적으로 저장했습니다.'))

        except requests.exceptions.RequestException as e:
            raise CommandError(f'[fetch_bus_data] API 요청 중 오류 발생: {e}')
        except KeyError as e:
            raise CommandError(f'[fetch_bus_data] 응답 데이터 처리 중 오류 발생: 잘못된 키 접근 ({e})')
        except Exception as e:
            raise CommandError(f'[fetch_bus_data] 전체 작업 중 오류 발생: {e}')

