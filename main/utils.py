"""
이 모듈은 서울시 오픈 API와 연동하여 버스 및 행정동 데이터를 수집, 정제, 적재(ETL)하는 유틸리티 함수들을 정의합니다.

[주요 기능]
1. 버스 승하차 데이터(BusData) 수집 및 저장
2. 버스 정류장 데이터(BusStop) 수집 및 업데이트 (Kakao Geocoding 포함)
3. 행정동 인구 데이터(HangJeongDong) 수집 및 동기화
"""

import requests
import time
from datetime import datetime, timedelta
from django.core.management.base import CommandError
from django.conf import settings
from django.utils import timezone
from main.models import BusData, BusDataHistory, BusStop, BusStopHistory, HangJeongDong, HangJeongDongHistory

# ========================================================
# [섹션 1] 버스 승하차 데이터 수집 (Bus Data Fetching)
# ========================================================

def fetch_bus_data_from_api(api_key, stdout_logger, style_logger, target_date=None):
    """
    서울시 버스 승하차 인원 정보를 API로부터 수집합니다.
    
    Args:
        api_key (str): 서울시 Open API 인증 키
        stdout_logger: 표준 출력 로거 (management command)
        style_logger: 스타일 로거
        target_date (str, optional): 수집할 특정 날짜 (YYYYMMDD). None일 경우 최신 데이터를 자동 탐색.
        
    Returns:
        tuple: (수집된 원본 데이터 리스트, 확정된 수집 기준 날짜)
    """
    service_name = 'CardBusStatisticsServiceNew'
    batch_size = 1000
    
    date_check_response = None

    if target_date:
        # [단계 1-A] 사용자가 지정한 특정 날짜 검증
        stdout_logger.write(f'[BusData] 지정된 날짜 {target_date}의 데이터를 확인합니다...')
        check_url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{service_name}/1/1/{target_date}'
        check_response = requests.get(check_url, timeout=10)
        check_response.raise_for_status()
        check_data = check_response.json()
        
        if service_name in check_data and 'row' in check_data.get(service_name, {}):
            date_check_response = check_response
            stdout_logger.write(style_logger.SUCCESS(f'[BusData] {target_date} 데이터가 존재합니다.'))
        else:
            stdout_logger.write(style_logger.WARNING(f'[BusData] {target_date}에 해당하는 데이터가 없습니다.'))
            return None, None
            
    else:
        # [단계 1-B] 최신 데이터 자동 탐색 (최근 7일 기준)
        for i in range(1, 8):
            date_to_check = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
            stdout_logger.write(f'[BusData] {date_to_check} 날짜의 데이터 존재 여부를 확인합니다...')
            check_url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{service_name}/1/1/{date_to_check}'
            check_response = requests.get(check_url, timeout=10)
            check_response.raise_for_status()
            check_data = check_response.json()
            
            if service_name in check_data and 'row' in check_data.get(service_name, {}):
                target_date = date_to_check
                date_check_response = check_response
                stdout_logger.write(style_logger.SUCCESS(f'[BusData] 수집 대상 날짜를 {target_date}로 확정했습니다.'))
                break
            time.sleep(0.5)

    if not target_date or not date_check_response:
        return None, None

    # [단계 2] 전체 데이터 일괄 수집 (페이지네이션)
    total_count = date_check_response.json()[service_name]['list_total_count']
    stdout_logger.write(f'[BusData] 총 {total_count}건의 승하차 데이터를 수집합니다.')

    api_rows = []
    for start in range(1, total_count + 1, batch_size):
        end = min(start + batch_size - 1, total_count)
        stdout_logger.write(f'[BusData] {start}~{end} 구간 수집 중...')
        
        api_url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{service_name}/{start}/{end}/{target_date}'
        api_response = requests.get(api_url, timeout=30)
        api_response.raise_for_status()
        
        api_data = api_response.json()
        api_rows.extend(api_data[service_name].get('row', []))
        time.sleep(0.1)  # API 부하 조절
        
    return api_rows, target_date

def parse_bus_data(raw_data, stdout_logger, style_logger):
    """
    API 원본(JSON) 데이터를 Django BusData 모델 객체 리스트로 변환합니다.
    """
    api_rows, target_date = raw_data
    stdout_logger.write('[BusData] 수집된 데이터를 파싱(객체 변환)합니다...')
    
    # 시간대(Aware Datetime) 정보 생성
    aware_datetime = timezone.make_aware(datetime.strptime(target_date, '%Y%m%d'))
    
    parsed_data = [
        BusData(
            bus_id=row['RTE_ID'],
            busstop_id=row['STOPS_ID'],
            timestamp=aware_datetime,
            passengers_on=row['GTON_TNOPE'],
            passengers_off=row['GTOFF_TNOPE'],
        )
        for row in api_rows 
        if row.get('RTE_ID') and row.get('STOPS_ID') # 필수 ID가 있는 경우만 처리
    ]
    
    stdout_logger.write(f'[BusData] 총 {len(parsed_data)}개의 유효 데이터가 준비되었습니다.')
    return parsed_data

def save_bus_data(parsed_data, stdout_logger, style_logger):
    """
    데이터베이스에 버스 승하차 정보를 저장합니다.
    - 중복 데이터(동일 날짜)가 있다면 저장을 건너뜁니다.
    - 새로운 날짜의 데이터라면, 기존 데이터는 History 테이블로 아카이빙(이동)합니다.
    """
    if not parsed_data:
        stdout_logger.write(style_logger.WARNING('[BusData] 저장할 데이터가 없습니다.'))
        return

    # 수집된 데이터의 날짜 추출
    new_data_timestamp = parsed_data[0].timestamp.date() 

    # [단계 1] 중복 검사 (이미 최신 데이터가 해당 날짜인지 확인)
    latest_db_record = BusData.objects.order_by('-timestamp').first()
    if latest_db_record:
        latest_db_timestamp = latest_db_record.timestamp.date()
        if new_data_timestamp == latest_db_timestamp:
            stdout_logger.write(style_logger.SUCCESS(f'[BusData] {new_data_timestamp} 데이터는 이미 최신 상태입니다. (저장 생략)'))
            return

    # [단계 2] 기존 Hot 데이터 아카이빙 (Cold Storage로 이동)
    stdout_logger.write('[BusData] 기존 Hot 데이터를 Cold 영역으로 아카이빙합니다...')
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
        stdout_logger.write(f'[BusData] {len(history_batch)}건을 이관 완료했습니다.')
        
        deleted_count, _ = records_to_archive.delete()
        stdout_logger.write(f'[BusData] {deleted_count}건을 Hot 테이블에서 삭제했습니다.')
    else:
        stdout_logger.write('[BusData] 아카이빙할 기존 데이터가 없습니다.')

    # [단계 3] 신규 데이터 적재 (Bulk Insert)
    stdout_logger.write('[BusData] 신규 데이터를 적재합니다...')
    BusData.objects.bulk_create(parsed_data)
    stdout_logger.write(style_logger.SUCCESS(f'[BusData] 총 {len(parsed_data)}건 저장 완료.'))

# ========================================================
# [섹션 2] 버스 정류장 데이터 데이터 수집 (Bus Stop Fetching)
# ========================================================

def fetch_bus_stop_data_from_api(api_key, stdout_logger, style_logger):
    """
    서울시 버스 상세 위치 정보(BIT)를 수집합니다.
    """
    service_name = 'busStopLocationXyInfo'
    batch_size = 1000

    stdout_logger.write('[BusStop] API에서 최신 정류장 정보를 요청합니다...')
    
    # 총 개수 확인
    check_url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{service_name}/1/1/'
    check_response = requests.get(check_url, timeout=10)
    check_response.raise_for_status()
    total_count = check_response.json()[service_name]['list_total_count']
    
    stdout_logger.write(f'[BusStop] 총 {total_count}개의 정류장이 조회되었습니다.')

    api_rows = []
    for start in range(1, total_count + 1, batch_size):
        end = min(start + batch_size - 1, total_count)
        stdout_logger.write(f'[BusStop] {start}~{end} 구간 수집 중...')
        
        api_url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{service_name}/{start}/{end}/'
        api_response = requests.get(api_url, timeout=30)
        api_response.raise_for_status()
        
        api_data = api_response.json()
        api_rows.extend(api_data[service_name].get('row', []))
        time.sleep(0.1)
    
    return api_rows

def parse_bus_stop_data(raw_data, stdout_logger, style_logger):
    """
    정류장 데이터를 ID를 Key로 하는 딕셔너리로 변환하여 검색 속도를 높입니다.
    """
    stdout_logger.write('[BusStop] 데이터를 파싱하여 딕셔너리로 변환합니다...')
    parsed_data = {row['NODE_ID']: row for row in raw_data}
    return parsed_data

def save_bus_stop_data(parsed_data, kakao_api_key, stdout_logger, style_logger):
    """
    정류장 데이터 동기화 로직입니다.
    - 신규 정류장: 생성 (Create)
    - 정보 변경/재활성화: 업데이트 (Update) 및 기존 정보 아카이빙
    - 사라진 정류장: 비활성화 (Soft Delete) 및 아카이빙
    - 행정동 코드 결측치: 카카오 로컬 API를 통해 주소 좌표 변환 (Geocoding)
    """
    stdout_logger.write('[BusStop] 데이터 동기화(변경/추가/삭제)를 분석합니다...')
    
    existing_stops = {s.busstop_id: s for s in BusStop.objects.all()}
    all_stop_ids = set(existing_stops.keys()) | set(parsed_data.keys())

    to_create = []
    to_update = []
    to_archive = []

    for stop_id in all_stop_ids:
        stop_in_db = existing_stops.get(stop_id)
        stop_in_api = parsed_data.get(stop_id)

        if stop_in_db and not stop_in_api:
            # [삭제됨] DB에는 있으나, API 목록에서 사라짐 -> 비활성화 처리
            if stop_in_db.is_active:
                to_archive.append(BusStopHistory(
                    busstop_id=stop_in_db.busstop_id, name=stop_in_db.name, 
                    longitude=stop_in_db.longitude, latitude=stop_in_db.latitude, 
                    district_id=stop_in_db.district_id, is_active=stop_in_db.is_active, 
                    timestamp=stop_in_db.timestamp
                ))
                stop_in_db.is_active = False
                to_update.append(stop_in_db)
        
        elif not stop_in_db and stop_in_api:
            # [신규] API에서 새로 발견됨 -> 생성
            new_stop = BusStop(
                busstop_id=stop_in_api['NODE_ID'], 
                name=stop_in_api['STOPS_NM'], 
                longitude=stop_in_api['XCRD'], 
                latitude=stop_in_api['YCRD'], 
                is_active=True
            )
            to_create.append(new_stop)

        elif stop_in_db and stop_in_api:
            # [변경] 둘 다 존재함 -> 이름 변경 또는 재활성화 여부 확인
            name_changed = stop_in_db.name != stop_in_api['STOPS_NM']
            reactivated = not stop_in_db.is_active

            if name_changed or reactivated:
                to_archive.append(BusStopHistory(
                    busstop_id=stop_in_db.busstop_id, name=stop_in_db.name, 
                    longitude=stop_in_db.longitude, latitude=stop_in_db.latitude, 
                    district_id=stop_in_db.district_id, is_active=stop_in_db.is_active, 
                    timestamp=stop_in_db.timestamp
                ))
                stop_in_db.name = stop_in_api['STOPS_NM']
                stop_in_db.is_active = True
                to_update.append(stop_in_db)

    # 일괄 처리 (Batch Processing)
    if to_archive:
        BusStopHistory.objects.bulk_create(to_archive)
        stdout_logger.write(style_logger.SUCCESS(f'[BusStop] {len(to_archive)}건의 변경 전 이력을 아카이빙했습니다.'))
    
    if to_create:
        BusStop.objects.bulk_create(to_create)
        stdout_logger.write(style_logger.SUCCESS(f'[BusStop] {len(to_create)}건의 신규 정류장을 등록했습니다.'))

    if to_update:
        BusStop.objects.bulk_update(to_update, ['name', 'is_active'])
        stdout_logger.write(style_logger.SUCCESS(f'[BusStop] {len(to_update)}건의 정류장 정보를 현행화했습니다.'))

    if not any([to_archive, to_create, to_update]):
        stdout_logger.write(style_logger.SUCCESS('[BusStop] 변경 사항이 없습니다.'))

    # [Kakao API 연동] 행정동 코드가 없는 정류장 채우기
    stdout_logger.write('[BusStop] 결측된 행정동 코드 채우기를 시도합니다 (Kakao API)...')
    stops_to_geocode = BusStop.objects.filter(district_id__isnull=True)
    
    if stops_to_geocode.exists():
        stdout_logger.write(f'[BusStop] 대상: {stops_to_geocode.count()}개 정류장')
        for i, stop in enumerate(stops_to_geocode):
            try:
                headers = {'Authorization': f'KakaoAK {kakao_api_key}'}
                params = {'x': stop.longitude, 'y': stop.latitude}
                kakao_api_url = 'https://dapi.kakao.com/v2/local/geo/coord2regioncode.json'
                
                kakao_response = requests.get(kakao_api_url, headers=headers, params=params, timeout=5)
                kakao_response.raise_for_status()
                kakao_data = kakao_response.json()
                
                # 법정동 대신 행정동(H) 코드를 사용
                for doc in kakao_data['documents']:
                    if doc['region_type'] == 'H':
                        stop.district_id = doc['code'][:-2] # 뒤 2자리는 세부 코드라 제외할 수 있음 (상황에 따라 조정)
                        stop.save()
                        stdout_logger.write(f'  - {stop.name} -> {stop.district_id} 매칭 성공')
                        break
                time.sleep(0.01) # API 제한 준수
            except Exception as e:
                stdout_logger.write(style_logger.WARNING(f'  - {stop.busstop_id} 좌표 변환 실패: {e}'))
    else:
        stdout_logger.write('[BusStop] 행정동 코드가 비어있는 정류장이 없습니다.')

# ========================================================
# [섹션 3] 행정동 인구 데이터 수집 (District Population Fetching)
# ========================================================

def fetch_hangjeongdong_data_from_api(api_key, stdout_logger, style_logger):
    """
    행정동 이름 및 생활 인구 데이터를 수집합니다.
    """
    name_service = 'TbgisAdstrdRelmW'
    pop_service = 'SPOP_LOCAL_RESD_DONG'
    batch_size = 1000

    # [단계 1] 행정동 이름 수집
    stdout_logger.write('[HangJeongDong] 행정동 이름 데이터를 요청합니다...')
    name_api_url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{name_service}/1/500/'
    name_api_response = requests.get(name_api_url, timeout=10)
    name_api_response.raise_for_status()
    raw_name_data = name_api_response.json()[name_service].get('row', [])
    time.sleep(1)

    # [단계 2] 인구 데이터 수집 (날짜 탐색 포함)
    stdout_logger.write('[HangJeongDong] 최신 인구 데이터를 탐색합니다...')
    raw_pop_data = []
    target_date = None
    pop_check_response = None

    for i in range(1, 8):
        date_to_check = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
        stdout_logger.write(f'  - {date_to_check} 데이터 확인 중...')
        pop_check_url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{pop_service}/1/1/{date_to_check}'
        check_response = requests.get(pop_check_url, timeout=10)
        
        if check_response.ok:
            pop_check_data = check_response.json()
            if pop_service in pop_check_data and 'row' in pop_check_data.get(pop_service, {}):
                target_date = date_to_check
                pop_check_response = check_response
                stdout_logger.write(style_logger.SUCCESS(f'  - {target_date} 데이터가 확인되었습니다.'))
                break
        time.sleep(0.5)

    if not target_date:
        stdout_logger.write(style_logger.WARNING('[HangJeongDong] 유효한 인구 데이터를 찾을 수 없어 수집을 건너뜁니다.'))
        return raw_name_data, [], None

    # 전체 인구 데이터 수집
    total_count = pop_check_response.json()[pop_service]['list_total_count']
    for start in range(1, total_count + 1, batch_size):
        end = min(start + batch_size - 1, total_count)
        pop_api_url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{pop_service}/{start}/{end}/{target_date}'
        resp = requests.get(pop_api_url, timeout=10)
        resp.raise_for_status()
        
        data = resp.json()
        if pop_service in data:
            raw_pop_data.extend(data[pop_service].get('row', []))
        time.sleep(0.1)
    
    return raw_name_data, raw_pop_data, target_date

def parse_hangjeongdong_data(raw_data, stdout_logger, style_logger):
    """
    행정동 이름과 인구 데이터를 매핑하여 구조화합니다.
    인구 데이터는 시간대별로 여러 건이 올 수 있으므로 평균을 내거나 합산하여 1일 기준 값으로 변환합니다.
    """
    raw_name_data, raw_pop_data, target_date = raw_data
    stdout_logger.write('[HangJeongDong] 수집된 데이터를 구조화합니다...')
    
    parsed_names = {row['ADSTRD_CD']: row['ADSTRD_NM'] for row in raw_name_data}
    parsed_populations = {}

    if raw_pop_data:
        # 행정동별 인구수 집계 (평균 계산)
        district_stats = {}
        for row in raw_pop_data:
            district_id = row['ADSTRD_CODE_SE']
            population = float(row['TOT_LVPOP_CO'])
            
            stats = district_stats.setdefault(district_id, {'total_pop': 0, 'count': 0})
            stats['total_pop'] += population
            stats['count'] += 1
        
        for district_id, stats in district_stats.items():
            if stats['count'] > 0:
                parsed_populations[district_id] = int(stats['total_pop'] / stats['count'])
    
    return parsed_names, parsed_populations

def save_hangjeongdong_data(parsed_data, stdout_logger, style_logger):
    """
    행정동 정보를 DB에 반영합니다.
    이름이나 인구수가 변경된 경우 이력을 남기고(Archiving) 최신 값을 업데이트합니다.
    """
    parsed_names, parsed_populations = parsed_data
    stdout_logger.write('[HangJeongDong] DB 업데이트 및 이력 관리를 수행합니다...')
    
    existing_hjds = {h.district_id: h for h in HangJeongDong.objects.all()}
    all_district_ids = set(existing_hjds.keys()) | set(parsed_names.keys())

    to_create = []
    to_update = []
    to_archive = []

    for district_id in all_district_ids:
        hjd_in_db = existing_hjds.get(district_id)
        name_from_api = parsed_names.get(district_id)
        pop_from_api = parsed_populations.get(district_id)

        if hjd_in_db:
            # 변경 여부 확인
            name_changed = name_from_api and hjd_in_db.name != name_from_api
            pop_changed = pop_from_api is not None and hjd_in_db.population != pop_from_api

            if name_changed or pop_changed:
                # [이력 보관] 변경 전 상태 저장
                to_archive.append(HangJeongDongHistory(
                    district_id=hjd_in_db.district_id,
                    name=hjd_in_db.name,
                    population=hjd_in_db.population,
                    timestamp=hjd_in_db.timestamp
                ))
                
                # [업데이트]
                if name_changed: hjd_in_db.name = name_from_api
                if pop_changed: hjd_in_db.population = pop_from_api
                to_update.append(hjd_in_db)
        
        elif name_from_api:
            # [신규 생성]
            to_create.append(HangJeongDong(
                district_id=district_id,
                name=name_from_api,
                population=pop_from_api
            ))

    if to_archive:
        HangJeongDongHistory.objects.bulk_create(to_archive)
        stdout_logger.write(style_logger.SUCCESS(f'[HangJeongDong] {len(to_archive)}건의 변경 전 데이터를 아카이빙했습니다.'))
    
    if to_create:
        HangJeongDong.objects.bulk_create(to_create)
        stdout_logger.write(style_logger.SUCCESS(f'[HangJeongDong] {len(to_create)}건의 신규 행정동을 등록했습니다.'))

    if to_update:
        HangJeongDong.objects.bulk_update(to_update, ['name', 'population'])
        stdout_logger.write(style_logger.SUCCESS(f'[HangJeongDong] {len(to_update)}건의 행정동 정보를 갱신했습니다.'))

    if not any([to_archive, to_create, to_update]):
        stdout_logger.write(style_logger.SUCCESS('[HangJeongDong] 정보가 이미 최신 상태입니다.'))
