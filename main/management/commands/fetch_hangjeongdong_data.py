import requests
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from main.models import HangJeongDong
from datetime import datetime, timedelta
import time

class Command(BaseCommand):
    def handle(self, *args, **options):
        api_key = settings.SEOUL_API_KEY

        # 1단계: 행정동 코드와 이름 정보 수집
        self.stdout.write(self.style.SUCCESS('[fetch_hangjeongdong_data] 행정동 이름/코드 정보 수집을 시작합니다...'))
        try:
            service_name_info = 'TbgisAdstrdRelmW'
            data_type = 'json'
            url = f'http://openapi.seoul.go.kr:8088/{api_key}/{data_type}/{service_name_info}/1/500/'
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            total_count = data[service_name_info]['list_total_count']
            self.stdout.write(f'[fetch_hangjeongdong_data] 총 {total_count}개의 행정동 정보를 발견했습니다.')

            rows = data[service_name_info].get('row', [])
            for row in rows:
                HangJeongDong.objects.update_or_create(
                    district_id=row['ADSTRD_CD'],
                    defaults={'name': row['ADSTRD_NM']}
                )
            self.stdout.write(self.style.SUCCESS(f'[fetch_hangjeongdong_data] 총 {len(rows)}개의 행정동 이름/코드 정보를 성공적으로 처리했습니다.'))

        except Exception as e:
            raise CommandError(f'[fetch_hangjeongdong_data] 행정동 이름/코드 처리 중 오류 발생: {e}')

        # API 과부하 방지를 위한 딜레이
        time.sleep(1)

        # 2단계: 행정동별 평균 인구수 계산 및 업데이트
        self.stdout.write(self.style.SUCCESS('[fetch_hangjeongdong_data] 행정동 평균 인구수 계산 및 업데이트를 시작합니다...'))
        try:
            service_name_pop = 'SPOP_LOCAL_RESD_DONG'
            target_date = None
            all_pop_rows = []

            # 최신 데이터가 있는 날짜 탐색
            for i in range(1, 8):
                date_to_check = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
                self.stdout.write(f'[fetch_hangjeongdong_data] {date_to_check} 기준 인구수 데이터를 탐색합니다...')
                check_url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{service_name_pop}/1/1/{date_to_check}'
                response = requests.get(check_url, timeout=10)
                if response.ok and service_name_pop in response.json() and 'row' in response.json()[service_name_pop]:
                    target_date = date_to_check
                    self.stdout.write(self.style.SUCCESS(f'[fetch_hangjeongdong_data] {target_date}에서 데이터를 발견했습니다. 전체 데이터 수집을 시작합니다.'))
                    break

                # API 과부하 방지를 위한 딜레이
                time.sleep(0.5)

            if not target_date:
                self.stdout.write(self.style.WARNING('[fetch_hangjeongdong_data] 최근 7일 내에 유효한 인구 데이터가 없습니다. 2단계를 건너뜁니다.'))
                return

            # 해당 날짜의 모든 시간대 데이터 수집
            total_count = response.json()[service_name_pop]['list_total_count']
            batch_size = 1000
            for start_index in range(1, total_count + 1, batch_size):
                end_index = start_index + batch_size - 1
                if end_index > total_count:
                    end_index = total_count
                
                url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{service_name_pop}/{start_index}/{end_index}/{target_date}'
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                all_pop_rows.extend(response.json()[service_name_pop].get('row', []))

                # API 과부하 방지를 위한 딜레이
                time.sleep(0.1)

            # 행정동별로 평균 인구수 계산
            self.stdout.write('[fetch_hangjeongdong_data] 수집된 데이터로 평균 인구수를 계산합니다...')
            district_stats = {}
            for row in all_pop_rows:
                district_id = row['ADSTRD_CODE_SE']
                population = float(row['TOT_LVPOP_CO'])
                if district_id not in district_stats:
                    district_stats[district_id] = {'total_pop': 0, 'count': 0}
                district_stats[district_id]['total_pop'] += population
                district_stats[district_id]['count'] += 1

            # 계산된 평균값으로 DB 업데이트
            updated_count = 0
            for district_id, stats in district_stats.items():
                if stats['count'] > 0:
                    average_pop = stats['total_pop'] / stats['count']
                    num_updated = HangJeongDong.objects.filter(district_id=district_id).update(
                        population=int(average_pop)
                    )
                    if num_updated > 0:
                        updated_count += num_updated
            
            self.stdout.write(self.style.SUCCESS(f'[fetch_hangjeongdong_data] 총 {updated_count}개 행정동의 평균 인구수 정보를 성공적으로 업데이트했습니다.'))

        except Exception as e:
            raise CommandError(f'[fetch_hangjeongdong_data] 행정동 인구수 처리 중 오류 발생: {e}')