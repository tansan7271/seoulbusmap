from .base_command import BaseFetchCommand
from main.utils import fetch_hangjeongdong_data_from_api, parse_hangjeongdong_data, save_hangjeongdong_data

class Command(BaseFetchCommand):
    service_name = 'fetch_hangjeongdong_data'
    help = '서울시 행정동 이름/코드 및 평균 인구수를 수집하고 아카이빙합니다.'

    def fetch(self, api_keys):
        """API로부터 행정동 원본 데이터를 수집합니다."""
        return fetch_hangjeongdong_data_from_api(api_keys['seoul'], self.stdout, self.style)

    def parse(self, fetch_result):
        """수집된 원본 데이터를 파싱하여 처리 가능한 형태로 변환합니다."""
        return parse_hangjeongdong_data(fetch_result, self.stdout, self.style)

    def save(self, parsed_data, api_keys):
        """파싱된 데이터를 데이터베이스에 저장합니다."""
        # 파싱된 데이터가 없을 경우 저장을 건너뜀
        if not parsed_data or (not parsed_data[0] and not parsed_data[1]):
            self.stdout.write(self.style.WARNING(f'[{self.service_name}] 파싱된 데이터가 없어 저장을 건너뜁니다.'))
            return
        save_hangjeongdong_data(parsed_data, self.stdout, self.style)