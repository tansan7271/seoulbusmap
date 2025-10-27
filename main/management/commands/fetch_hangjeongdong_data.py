import requests
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from main.models import HangJeongDong, HangJeongDongHistory
from main.utils import fetch_hangjeongdong_data_from_api, parse_hangjeongdong_data, save_hangjeongdong_data

class Command(BaseCommand):
    help = '서울시 행정동 이름/코드 및 평균 인구수를 수집하고 아카이빙합니다.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('[fetch_hangjeongdong_data] 행정동 정보 수집 및 아카이빙을 시작합니다...'))

        try:
            seoul_api_key = settings.SEOUL_API_KEY

            # 1. Fetch Data
            raw_data = fetch_hangjeongdong_data_from_api(seoul_api_key, self.stdout, self.style)

            # 2. Parse Data
            parsed_data = parse_hangjeongdong_data(raw_data, self.stdout, self.style)

            # 3. Save Data
            save_hangjeongdong_data(parsed_data, self.stdout, self.style)

            self.stdout.write(self.style.SUCCESS('[fetch_hangjeongdong_data] 모든 작업이 성공적으로 완료되었습니다.'))

        except Exception as e:
            raise CommandError(f'[fetch_hangjeongdong_data] 전체 작업 중 오류 발생: {e}')