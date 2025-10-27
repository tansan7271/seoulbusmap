import os
import threading
import time
from django.apps import AppConfig
from django.core.management import call_command
from django.utils import timezone

# 스케줄러 실행 간격 (초 단위)
# 실제 운영에서는 24시간(86400초) 등으로 설정
SCHEDULER_INTERVAL_BUS_DATA = 86400  # 24시간 (일일 간격)
SCHEDULER_INTERVAL_MONTHLY = 2592000 # 30일 (한 달 간격)

# 스케줄러가 중복 실행되지 않도록 관리하기 위한 플래그
scheduler_started = False
monthly_scheduler_started_once = False # 월별 스케줄러의 최초 실행 여부

def run_bus_data_scheduler():
    """
    버스 승하차 정보 수집을 위한 스케줄러.
    일일 간격으로 실행됩니다.
    """
    print(f"[{timezone.now()}] [버스 승하차] 스케줄러 작업을 시작합니다...")
    try:
        call_command('fetch_bus_data')
    except Exception as e:
        print(f"[버스 승하차] 스케줄러 작업 중 오류 발생: {e}")
    finally:
        # 다음 스케줄링을 위해 타이머를 다시 설정
        threading.Timer(SCHEDULER_INTERVAL_BUS_DATA, run_bus_data_scheduler).start()
        print(f"[{timezone.now()}] [버스 승하차] 스케줄러 작업 완료. 다음 실행은 {SCHEDULER_INTERVAL_BUS_DATA}초 후입니다.")
        
        # 버스 데이터 스케줄러의 첫 실행이 완료된 후 월별 스케줄러의 첫 실행을 트리거
        global monthly_scheduler_started_once
        if not monthly_scheduler_started_once:
            monthly_scheduler_started_once = True
            threading.Timer(1, run_monthly_scheduler).start() # 짧은 지연 후 월별 스케줄러 시작

def run_monthly_scheduler():
    """
    행정동 및 버스 정류장 정보 수집을 위한 스케줄러.
    월별 간격으로 실행됩니다.
    """
    print(f"[{timezone.now()}] [월별 데이터] 스케줄러 작업을 시작합니다...")
    try:
        call_command('fetch_hangjeongdong_data')
        call_command('fetch_busstop_data')
    except Exception as e:
        print(f"[월별 데이터] 스케줄러 작업 중 오류 발생: {e}")
    finally:
        threading.Timer(SCHEDULER_INTERVAL_MONTHLY, run_monthly_scheduler).start()
        print(f"[{timezone.now()}] [월별 데이터] 스케줄러 작업 완료. 다음 실행은 {SCHEDULER_INTERVAL_MONTHLY}초 후입니다.")

class MainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'main'

    def ready(self):
        global scheduler_started
        # Django reloader가 아닌 메인 프로세스에서만 스케줄러를 시작
        if not scheduler_started and os.environ.get('RUN_MAIN', None) != 'true':
            print("모든 스케줄러를 시작합니다...")
            scheduler_started = True
            
            # 최초 실행도 짧은 지연 후 시작하여 DB 초기화 완료를 기다림
            # 버스 데이터 스케줄러가 먼저 시작되고, 그 완료 후 월별 스케줄러가 시작되도록 체인
            threading.Timer(1, run_bus_data_scheduler).start()
