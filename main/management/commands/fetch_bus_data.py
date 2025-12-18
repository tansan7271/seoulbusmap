import requests
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from main.models import BusData, BusDataHistory
from main.utils import fetch_bus_data_from_api, parse_bus_data, save_bus_data

class Command(BaseCommand):
    help = '서울시 버스 승하차 인원 정보를 수집하고 아카이빙합니다.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='수집할 날짜 (YYYYMMDD 형식)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('[fetch_bus_data] 승하차 인원 정보 수집 및 아카이빙을 시작합니다...'))
        
        target_date = options.get('date')

        try:
            seoul_api_key = settings.SEOUL_API_KEY

            # 1. Fetch Data
            # raw_data = (api_rows, confirmed_date)
            raw_data = fetch_bus_data_from_api(seoul_api_key, self.stdout, self.style, target_date=target_date)
            if not raw_data or not raw_data[0]:
                self.stdout.write(self.style.WARNING('[fetch_bus_data] 수집할 데이터가 없어 작업을 종료합니다.'))
                return

            # 2. Parse Data
            parsed_data = parse_bus_data(raw_data, self.stdout, self.style)

            # 3. Save Data
            save_bus_data(parsed_data, self.stdout, self.style)
            
            self.stdout.write(self.style.SUCCESS('[fetch_bus_data] 모든 작업이 성공적으로 완료되었습니다.'))

        except requests.exceptions.RequestException as e:
            raise CommandError(f'[fetch_bus_data] API 요청 중 오류 발생: {e}')
        except KeyError as e:
            raise CommandError(f'[fetch_bus_data] 응답 데이터 처리 중 오류 발생: 잘못된 키 접근 ({e})')
        except Exception as e:
            raise CommandError(f'[fetch_bus_data] 전체 작업 중 오류 발생: {e}')


