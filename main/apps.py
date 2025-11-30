import os
import threading
import time
import sys
from django.apps import AppConfig
from django.core.management import call_command
from django.utils import timezone

# 스케줄러 실행 간격 (초 단위)
SCHEDULER_INTERVAL_BUS_DATA = 86400      # 24시간 (일일 간격)
SCHEDULER_INTERVAL_BUS_STOP = 604800     # 7일 (주간 간격)
SCHEDULER_INTERVAL_HANGJEONGDONG = 2592000 # 30일 (월간 간격)

# 스케줄러가 중복 실행되지 않도록 관리하기 위한 플래그
scheduler_started = False

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

def run_busstop_scheduler():
    """
    버스 정류장 정보 수집을 위한 스케줄러.
    주간 간격으로 실행됩니다.
    """
    print(f"[{timezone.now()}] [버스 정류장] 스케줄러 작업을 시작합니다...")
    try:
        call_command('fetch_busstop_data')
    except Exception as e:
        print(f"[버스 정류장] 스케줄러 작업 중 오류 발생: {e}")
    finally:
        threading.Timer(SCHEDULER_INTERVAL_BUS_STOP, run_busstop_scheduler).start()
        print(f"[{timezone.now()}] [버스 정류장] 스케줄러 작업 완료. 다음 실행은 {SCHEDULER_INTERVAL_BUS_STOP}초 후입니다.")

def run_hangjeongdong_scheduler():
    """
    행정동 정보 수집을 위한 스케줄러.
    월간 간격으로 실행됩니다.
    """
    print(f"[{timezone.now()}] [행정동] 스케줄러 작업을 시작합니다...")
    try:
        call_command('fetch_hangjeongdong_data')
    except Exception as e:
        print(f"[행정동] 스케줄러 작업 중 오류 발생: {e}")
    finally:
        threading.Timer(SCHEDULER_INTERVAL_HANGJEONGDONG, run_hangjeongdong_scheduler).start()
        print(f"[{timezone.now()}] [행정동] 스케줄러 작업 완료. 다음 실행은 {SCHEDULER_INTERVAL_HANGJEONGDONG}초 후입니다.")

class MainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'main'

    def ready(self):
        global scheduler_started
        # Django reloader가 아닌 메인 프로세스에서만 스케줄러를 시작
        if not scheduler_started and os.environ.get('RUN_MAIN', None) != 'true' and len(sys.argv) > 1 and sys.argv[1] == 'runserver':
            print("모든 스케줄러를 시작합니다...")
            scheduler_started = True
            
            # DB 초기화 및 다른 앱의 준비를 기다리기 위해 짧은 지연 후 순차적으로 시작
            threading.Timer(1, run_bus_data_scheduler).start()
            threading.Timer(2, run_busstop_scheduler).start()
            threading.Timer(3, run_hangjeongdong_scheduler).start()
