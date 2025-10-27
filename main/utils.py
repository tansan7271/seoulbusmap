import requests
from django.core.management.base import CommandError
from django.conf import settings
from django.utils import timezone
from main.models import BusData, BusDataHistory, BusStop, BusStopHistory, HangJeongDong, HangJeongDongHistory
from datetime import datetime, timedelta
import time

# --- Bus Data Fetching Functions ---

def fetch_bus_data_from_api(api_key, stdout_logger, style_logger):
    """
    API에서 수집 가능한 최신 일자의 모든 승하차 인원 정보를 가져옵니다.
    """
    service_name = 'CardBusStatisticsServiceNew'
    batch_size = 1000
    
    # 1. 최신 데이터 날짜 탐색
    target_date = None
    date_check_response = None
    for i in range(1, 8):
        date_to_check = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
        stdout_logger.write(f'[fetch_bus_data] {date_to_check} 날짜의 데이터 존재 여부를 확인합니다...')
        check_url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{service_name}/1/1/{date_to_check}'
        check_response = requests.get(check_url, timeout=10)
        check_response.raise_for_status()
        check_data = check_response.json()
        if service_name in check_data and 'row' in check_data.get(service_name, {}):
            target_date = date_to_check
            date_check_response = check_response
            stdout_logger.write(style_logger.SUCCESS(f'[fetch_bus_data] 데이터 수집 대상 날짜를 {target_date}로 확정했습니다.'))
            break
        time.sleep(0.5)

    if not target_date:
        return None, None

    # 2. 전체 데이터 수집
    total_count = date_check_response.json()[service_name]['list_total_count']
    stdout_logger.write(f'[fetch_bus_data] 총 {total_count}개의 신규 승하차 데이터를 수집합니다.')

    api_rows = []
    for start in range(1, total_count + 1, batch_size):
        end = min(start + batch_size - 1, total_count)
        stdout_logger.write(f'[fetch_bus_data] {start}~{end} 정보 수집 중...')
        api_url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{service_name}/{start}/{end}/{target_date}'
        api_response = requests.get(api_url, timeout=30)
        api_response.raise_for_status()
        api_data = api_response.json()
        api_rows.extend(api_data[service_name].get('row', []))
        time.sleep(0.1)
        
    return api_rows, target_date

def parse_bus_data(raw_data, stdout_logger, style_logger):
    """
    API 원본 데이터를 BusData 모델 객체 리스트로 변환합니다.
    """
    api_rows, target_date = raw_data
    stdout_logger.write('[fetch_bus_data] 수집된 데이터를 파싱합니다...')
    aware_datetime = timezone.make_aware(datetime.strptime(target_date, '%Y%m%d'))
    
    parsed_data = [
        BusData(
            bus_id=row['RTE_ID'],
            busstop_id=row['STOPS_ID'],
            timestamp=aware_datetime,
            passengers_on=row['GTON_TNOPE'],
            passengers_off=row['GTOFF_TNOPE'],
        )
        for row in api_rows if row.get('RTE_ID') and row.get('STOPS_ID')
    ]
    
    stdout_logger.write(f'[fetch_bus_data] 총 {len(parsed_data)}개의 데이터를 처리할 준비가 되었습니다.')
    return parsed_data

def save_bus_data(parsed_data, stdout_logger, style_logger):
    """
    기존 데이터를 아카이빙하고, 새로운 데이터를 DB에 저장합니다.
    새로 수집된 데이터의 날짜가 이미 DB에 있는 최신 데이터의 날짜와 같으면 저장을 건너뜁니다.
    """
    # parsed_data에서 target_date 추출 (parsed_data는 BusData 객체 리스트이므로 첫 번째 객체에서 timestamp 추출)
    if parsed_data:
        new_data_timestamp = parsed_data[0].timestamp.date() # datetime 객체에서 날짜만 비교
    else:
        stdout_logger.write(style_logger.WARNING('[fetch_bus_data] 저장할 신규 데이터가 없습니다.'))
        return

    # 1. 기존 데이터의 최신 날짜 확인
    latest_db_record = BusData.objects.order_by('-timestamp').first()
    if latest_db_record:
        latest_db_timestamp = latest_db_record.timestamp.date()
        if new_data_timestamp == latest_db_timestamp:
            stdout_logger.write(style_logger.SUCCESS(f'[fetch_bus_data] {new_data_timestamp} 날짜의 데이터가 이미 최신 상태입니다. 저장을 건너뜁니다.'))
            return

    # 2. 기존 데이터 아카이빙
    stdout_logger.write('[fetch_bus_data] 기존 데이터 아카이빙을 시작합니다...')
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
        stdout_logger.write(f'[fetch_bus_data] {len(history_batch)}건의 데이터를 BusDataHistory 테이블로 이동했습니다.')
        
        deleted_count, _ = records_to_archive.delete()
        stdout_logger.write(f'[fetch_bus_data] {deleted_count}건의 데이터를 BusData 테이블에서 삭제했습니다.')
    else:
        stdout_logger.write('[fetch_bus_data] 아카이빙할 기존 데이터가 없습니다.')

    # 3. 신규 데이터 저장
    stdout_logger.write('[fetch_bus_data] 신규 데이터 저장을 시작합니다...')
    BusData.objects.bulk_create(parsed_data)
    stdout_logger.write(style_logger.SUCCESS(f'[fetch_bus_data] 총 {len(parsed_data)}개의 승하차 정보를 성공적으로 저장했습니다.'))

# --- Bus Stop Data Fetching Functions ---

def fetch_bus_stop_data_from_api(api_key, stdout_logger, style_logger):
    """
    API에서 모든 최신 정류장 정보를 가져옵니다.
    """
    service_name = 'busStopLocationXyInfo'
    batch_size = 1000

    stdout_logger.write('[fetch_busstop_data] API에서 최신 정류장 정보를 수집합니다...')
    check_url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{service_name}/1/1/'
    check_response = requests.get(check_url, timeout=10)
    check_response.raise_for_status()
    check_data = check_response.json()
    total_count = check_data[service_name]['list_total_count']
    stdout_logger.write(f'[fetch_busstop_data] 총 {total_count}개의 정류장 정보가 있습니다.')

    api_rows = []
    for start in range(1, total_count + 1, batch_size):
        end = min(start + batch_size - 1, total_count)
        stdout_logger.write(f'[fetch_busstop_data] {start}~{end} 정보 수집 중...')
        api_url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{service_name}/{start}/{end}/'
        api_response = requests.get(api_url, timeout=30)
        api_response.raise_for_status()
        api_data = api_response.json()
        api_rows.extend(api_data[service_name].get('row', []))
        time.sleep(0.1)
    
    return api_rows

def parse_bus_stop_data(raw_data, stdout_logger, style_logger):
    """
    원본 데이터를 정제하여 정류장 ID를 키로 하는 딕셔너리 형태로 반환합니다.
    """
    stdout_logger.write('[fetch_busstop_data] 수집된 데이터를 파싱합니다...')
    parsed_data = {row['NODE_ID']: row for row in raw_data}
    return parsed_data

def save_bus_stop_data(parsed_data, kakao_api_key, stdout_logger, style_logger):
    """
    정제된 데이터를 DB에 비교, 아카이빙, 업데이트하고 카카오 API를 통해 행정동 코드를 매칭합니다.
    """
    stdout_logger.write('[fetch_busstop_data] 데이터 비교, 아카이빙, 업데이트를 시작합니다...')
    existing_stops = {s.busstop_id: s for s in BusStop.objects.all()}
    all_stop_ids = set(existing_stops.keys()) | set(parsed_data.keys())

    to_create = []
    to_update = []
    to_archive = []

    for stop_id in all_stop_ids:
        stop_in_db = existing_stops.get(stop_id)
        stop_in_api = parsed_data.get(stop_id)

        if stop_in_db and not stop_in_api:
            # C (비활성화): DB에는 있지만 API에는 없는 경우
            if stop_in_db.is_active:
                to_archive.append(BusStopHistory(busstop_id=stop_in_db.busstop_id, name=stop_in_db.name, longitude=stop_in_db.longitude, latitude=stop_in_db.latitude, district_id=stop_in_db.district_id, is_active=stop_in_db.is_active))
                stop_in_db.is_active = False
                to_update.append(stop_in_db)
        
        elif not stop_in_db and stop_in_api:
            # B (신규 추가): API에는 있지만 DB에는 없는 경우
            new_stop = BusStop(busstop_id=stop_in_api['NODE_ID'], name=stop_in_api['STOPS_NM'], longitude=stop_in_api['XCRD'], latitude=stop_in_api['YCRD'], is_active=True)
            to_create.append(new_stop)

        elif stop_in_db and stop_in_api:
            # A (정보 변경): 둘 다 있는 경우
            name_changed = stop_in_db.name != stop_in_api['STOPS_NM']
            reactivated = not stop_in_db.is_active

            if name_changed or reactivated:
                to_archive.append(BusStopHistory(busstop_id=stop_in_db.busstop_id, name=stop_in_db.name, longitude=stop_in_db.longitude, latitude=stop_in_db.latitude, district_id=stop_in_db.district_id, is_active=stop_in_db.is_active))
                stop_in_db.name = stop_in_api['STOPS_NM']
                stop_in_db.is_active = True
                to_update.append(stop_in_db)

    if to_archive:
        BusStopHistory.objects.bulk_create(to_archive)
        stdout_logger.write(style_logger.SUCCESS(f'[fetch_busstop_data] {len(to_archive)}개의 변경 전 데이터를 아카이빙했습니다.'))
    
    if to_create:
        BusStop.objects.bulk_create(to_create)
        stdout_logger.write(style_logger.SUCCESS(f'[fetch_busstop_data] {len(to_create)}개의 신규 정류장을 추가했습니다.'))

    if to_update:
        BusStop.objects.bulk_update(to_update, ['name', 'is_active'])
        stdout_logger.write(style_logger.SUCCESS(f'[fetch_busstop_data] {len(to_update)}개의 정류장 정보를 업데이트했습니다.'))

    if not any([to_archive, to_create, to_update]):
        stdout_logger.write(style_logger.SUCCESS('[fetch_busstop_data] 변경된 데이터가 없어, 모든 데이터가 최신 상태입니다.'))

    # --- 행정동 코드 업데이트 (카카오 API) ---
    # 행정동 코드가 비어있는 정류장에 대해서만 실행
    stdout_logger.write('[fetch_busstop_data] 행정동 코드 업데이트를 시작합니다...')
    stops_to_geocode = BusStop.objects.filter(district_id__isnull=True)
    stdout_logger.write(f'[fetch_busstop_data] 총 {stops_to_geocode.count()}개의 정류장에 대해 행정동 코드 매칭을 시도합니다.')
    
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
                    stdout_logger.write(f'[fetch_busstop_data] {i+1}: {stop.name}의 행정동 코드를 {stop.district_id}로 업데이트했습니다.')
                    break
            time.sleep(0.01)
        except Exception as e:
            stdout_logger.write(style_logger.WARNING(f'[fetch_busstop_data] 정류장 {stop.busstop_id}의 행정동 코드 변환 중 오류: {e}'))


# --- HangJeongDong Data Fetching Functions ---

def fetch_hangjeongdong_data_from_api(api_key, stdout_logger, style_logger):
    """
    API에서 수집 가능한 최신 일자의 행정동 이름과 인구수 원본 데이터를 가져옵니다.
    """
    name_service = 'TbgisAdstrdRelmW'
    pop_service = 'SPOP_LOCAL_RESD_DONG'
    batch_size = 1000

    # 1. 행정동 이름 데이터 수집
    stdout_logger.write('[fetch_hangjeongdong_data] API에서 최신 이름 정보를 수집합니다...')
    name_api_url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{name_service}/1/500/'
    name_api_response = requests.get(name_api_url, timeout=10)
    name_api_response.raise_for_status()
    name_api_data = name_api_response.json()
    raw_name_data = name_api_data[name_service].get('row', [])
    time.sleep(1)

    # 2. 행정동 인구 데이터 수집
    stdout_logger.write('[fetch_hangjeongdong_data] API에서 최신 인구 정보를 수집합니다...')
    raw_pop_data = []
    target_date = None

    # 2-1. 최신 데이터 날짜 탐색
    pop_check_response = None
    for i in range(1, 8):
        date_to_check = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
        stdout_logger.write(f'[fetch_hangjeongdong_data] {date_to_check} 날짜의 인구 데이터 존재 여부를 확인합니다...')
        pop_check_url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{pop_service}/1/1/{date_to_check}'
        check_response = requests.get(pop_check_url, timeout=10)
        if check_response.ok:
            pop_check_data = check_response.json()
            if pop_service in pop_check_data and 'row' in pop_check_data.get(pop_service, {}):
                target_date = date_to_check
                pop_check_response = check_response
                stdout_logger.write(style_logger.SUCCESS(f'[fetch_hangjeongdong_data] {target_date} 기준 인구 데이터를 찾았습니다.'))
                break
        time.sleep(0.5)

    if not target_date:
        stdout_logger.write(style_logger.WARNING('[fetch_hangjeongdong_data] 최근 7일 내에 유효한 인구 데이터가 없어 인구 정보 수집을 건너뜁니다.'))
        return raw_name_data, [], None

    # 2-2. 전체 데이터 수집
    total_count = pop_check_response.json()[pop_service]['list_total_count']
    for start in range(1, total_count + 1, batch_size):
        end = min(start + batch_size - 1, total_count)
        pop_api_url = f'http://openapi.seoul.go.kr:8088/{api_key}/json/{pop_service}/{start}/{end}/{target_date}'
        pop_api_response = requests.get(pop_api_url, timeout=10)
        pop_api_response.raise_for_status()
        
        pop_api_data = pop_api_response.json()
        if pop_service not in pop_api_data:
            error_message = pop_api_data.get("RESULT", {}).get("MESSAGE", "알 수 없는 API 오류")
            stdout_logger.write(style_logger.WARNING(f'[fetch_hangjeongdong_data] 인구 데이터 {start}~{end} 수집 중 오류 발생: {error_message}'))
            continue

        raw_pop_data.extend(pop_api_data[pop_service].get('row', []))
        time.sleep(0.1)
    
    return raw_name_data, raw_pop_data, target_date

def parse_hangjeongdong_data(raw_data, stdout_logger, style_logger):
    """
    원본 데이터를 정제하여 행정동 이름과 인구수 딕셔너리 형태로 반환합니다.
    """
    raw_name_data, raw_pop_data, target_date = raw_data
    stdout_logger.write('[fetch_hangjeongdong_data] 수집된 데이터를 파싱합니다...')
    
    parsed_names = {row['ADSTRD_CD']: row['ADSTRD_NM'] for row in raw_name_data}
    parsed_populations = {}

    if raw_pop_data:
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
    
    parsed_data = (parsed_names, parsed_populations)
    return parsed_data

def save_hangjeongdong_data(parsed_data, stdout_logger, style_logger):
    """
    정제된 데이터를 DB에 비교, 아카이빙, 업데이트합니다.
    """
    parsed_names, parsed_populations = parsed_data
    stdout_logger.write('[fetch_hangjeongdong_data] 데이터 비교, 아카이빙, 업데이트를 시작합니다...')
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
            # 기존 데이터가 있는 경우: 변경점 확인
            name_changed = name_from_api and hjd_in_db.name != name_from_api
            pop_changed = pop_from_api is not None and hjd_in_db.population != pop_from_api

            if name_changed or pop_changed:
                # 변경점이 하나라도 있으면, 옛날 데이터 아카이빙
                to_archive.append(HangJeongDongHistory(
                    district_id=hjd_in_db.district_id,
                    name=hjd_in_db.name,
                    population=hjd_in_db.population
                ))
                # 최신 값으로 업데이트 준비
                if name_changed: hjd_in_db.name = name_from_api
                if pop_changed: hjd_in_db.population = pop_from_api
                to_update.append(hjd_in_db)
        
        elif name_from_api:
            # 기존 데이터는 없고, 새 이름 정보만 있는 경우: 신규 생성
            to_create.append(HangJeongDong(
                district_id=district_id,
                name=name_from_api,
                population=pop_from_api # 인구 정보가 있으면 같이 생성
            ))

    if to_archive:
        HangJeongDongHistory.objects.bulk_create(to_archive)
        stdout_logger.write(style_logger.SUCCESS(f'[fetch_hangjeongdong_data] {len(to_archive)}개의 변경 전 데이터를 아카이빙했습니다.'))
    
    if to_create:
        HangJeongDong.objects.bulk_create(to_create)
        stdout_logger.write(style_logger.SUCCESS(f'[fetch_hangjeongdong_data] {len(to_create)}개의 신규 행정동을 추가했습니다.'))

    if to_update:
        HangJeongDong.objects.bulk_update(to_update, ['name', 'population'])
        stdout_logger.write(style_logger.SUCCESS(f'[fetch_hangjeongdong_data] {len(to_update)}개의 행정동 정보를 업데이트했습니다.'))

    if not any([to_archive, to_create, to_update]):
        stdout_logger.write(style_logger.SUCCESS('[fetch_hangjeongdong_data] 변경된 데이터가 없어, 모든 데이터가 최신 상태입니다.'))
