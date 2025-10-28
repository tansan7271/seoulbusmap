from .base_command import BaseFetchCommand
from main.utils import fetch_bus_data_from_api, parse_bus_data, save_bus_data

class Command(BaseFetchCommand):
    service_name = 'fetch_bus_data'
    help = '서울시 버스 승하차 인원 정보를 수집하고 아카이빙합니다.'

    def fetch(self, api_keys):
        """API로부터 버스 승하차 인원 원본 데이터를 수집합니다."""
        return fetch_bus_data_from_api(api_keys['seoul'], self.stdout, self.style)

    def parse(self, fetch_result):
        """수집된 원본 데이터를 파싱하여 처리 가능한 형태로 변환합니다."""
        return parse_bus_data(fetch_result, self.stdout, self.style)

    def save(self, parsed_data, api_keys):
        """파싱된 데이터를 데이터베이스에 저장합니다."""
        save_bus_data(parsed_data, self.stdout, self.style)
