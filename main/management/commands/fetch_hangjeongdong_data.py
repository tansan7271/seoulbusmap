import requests
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from main.models import HangJeongDong, HangJeongDongHistory
from datetime import datetime, timedelta
import time

class Command(BaseCommand):
    def handle(self, *args, **options):
        seoul_api_key = settings.SEOUL_API_KEY
        self.stdout.write(self.style.SUCCESS('[fetch_hangjeongdong_data] 행정동 정보 수집 및 아카이빙을 시작합니다...'))

        try:
            # --- 1단계: API에서 최신 이름 정보 수집 ---
            self.stdout.write('[fetch_hangjeongdong_data] 최신 이름 정보를 수집합니다...')
            name_service = 'TbgisAdstrdRelmW'
            name_url = f'http://openapi.seoul.go.kr:8088/{seoul_api_key}/json/{name_service}/1/500/'
            name_response = requests.get(name_url, timeout=10)
            name_response.raise_for_status()
            name_data = name_response.json()[name_service].get('row', [])
            new_names = {row['ADSTRD_CD']: row['ADSTRD_NM'] for row in name_data}

            time.sleep(1)

            # --- 2단계: API에서 최신 인구 정보 수집 및 계산 ---
            self.stdout.write('[fetch_hangjeongdong_data] 최신 인구 정보를 수집합니다...')
            pop_service = 'SPOP_LOCAL_RESD_DONG'
            new_populations = {}
            target_date = None

            for i in range(1, 8):
                date_to_check = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
                check_url = f'http://openapi.seoul.go.kr:8088/{seoul_api_key}/json/{pop_service}/1/1/{date_to_check}'
                response = requests.get(check_url, timeout=10)
                if response.ok and pop_service in response.json() and 'row' in response.json()[pop_service]:
                    target_date = date_to_check
                    self.stdout.write(self.style.SUCCESS(f'[fetch_hangjeongdong_data] {target_date} 기준 인구 데이터를 찾았습니다.'))
                    break
                time.sleep(0.5)

            if target_date:
                total_count = response.json()[pop_service]['list_total_count']
                all_pop_rows = []
                batch_size = 1000
                for start in range(1, total_count + 1, batch_size):
                    end = start + batch_size - 1
                    if end > total_count: end = total_count
                    pop_url = f'http://openapi.seoul.go.kr:8088/{seoul_api_key}/json/{pop_service}/{start}/{end}/{target_date}'
                    pop_response = requests.get(pop_url, timeout=10)
                    pop_response.raise_for_status()
                    all_pop_rows.extend(pop_response.json()[pop_service].get('row', []))
                    time.sleep(0.1)

                district_stats = {}
                for row in all_pop_rows:
                    district_id = row['ADSTRD_CODE_SE']
                    population = float(row['TOT_LVPOP_CO'])
                    stats = district_stats.setdefault(district_id, {'total_pop': 0, 'count': 0})
                    stats['total_pop'] += population
                    stats['count'] += 1
                
                for district_id, stats in district_stats.items():
                    if stats['count'] > 0:
                        new_populations[district_id] = int(stats['total_pop'] / stats['count'])

            # --- 3단계: 데이터 비교, 아카이빙, 및 업데이트 ---
            self.stdout.write('[fetch_hangjeongdong_data] 데이터 비교, 아카이빙, 업데이트를 시작합니다...')
            existing_hjds = {h.district_id: h for h in HangJeongDong.objects.all()}
            all_district_ids = set(existing_hjds.keys()) | set(new_names.keys())

            to_create = []
            to_update = []
            to_archive = []

            for district_id in all_district_ids:
                hjd = existing_hjds.get(district_id)
                new_name = new_names.get(district_id)
                new_pop = new_populations.get(district_id)

                if hjd:
                    # 기존 데이터가 있는 경우: 변경점 확인
                    name_changed = new_name and hjd.name != new_name
                    pop_changed = new_pop is not None and hjd.population != new_pop

                    if name_changed or pop_changed:
                        # 변경점이 하나라도 있으면, 옛날 데이터 아카이빙
                        to_archive.append(HangJeongDongHistory(
                            district_id=hjd.district_id,
                            name=hjd.name,
                            population=hjd.population
                        ))
                        # 최신 값으로 업데이트 준비
                        if name_changed: hjd.name = new_name
                        if pop_changed: hjd.population = new_pop
                        to_update.append(hjd)
                
                elif new_name:
                    # 기존 데이터는 없고, 새 이름 정보만 있는 경우: 신규 생성
                    to_create.append(HangJeongDong(
                        district_id=district_id,
                        name=new_name,
                        population=new_pop # 인구 정보가 있으면 같이 생성
                    ))

            if to_archive:
                HangJeongDongHistory.objects.bulk_create(to_archive)
                self.stdout.write(self.style.SUCCESS(f'[fetch_hangjeongdong_data] {len(to_archive)}개의 변경 전 데이터를 아카이빙했습니다.'))
            
            if to_create:
                HangJeongDong.objects.bulk_create(to_create)
                self.stdout.write(self.style.SUCCESS(f'[fetch_hangjeongdong_data] {len(to_create)}개의 신규 행정동을 추가했습니다.'))

            if to_update:
                HangJeongDong.objects.bulk_update(to_update, ['name', 'population'])
                self.stdout.write(self.style.SUCCESS(f'[fetch_hangjeongdong_data] {len(to_update)}개의 행정동 정보를 업데이트했습니다.'))

            if not any([to_archive, to_create, to_update]):
                self.stdout.write(self.style.SUCCESS('[fetch_hangjeongdong_data] 변경된 데이터가 없어, 모든 데이터가 최신 상태입니다.'))

        except Exception as e:
            raise CommandError(f'[fetch_hangjeongdong_data] 전체 작업 중 오류 발생: {e}')