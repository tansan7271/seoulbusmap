from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

class BaseFetchCommand(BaseCommand):
    """
    데이터를 수집하고 저장하는 관리 명령어의 기본 클래스.
    상속받는 클래스는 service_name, help 속성과 fetch, parse, save 메소드를 구현해야 합니다.
    """
    service_name = ''
    help = ''

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(f'[{self.service_name}] 작업을 시작합니다...'))
        try:
            # 1. API 키 가져오기
            api_keys = self.get_api_keys()

            # 2. 데이터 수집
            fetch_result = self.fetch(api_keys)

            # 데이터가 없는 경우 처리
            if not self.is_data_valid(fetch_result):
                self.stdout.write(self.style.WARNING(f'[{self.service_name}] 수집할 유효한 데이터가 없어 작업을 종료합니다.'))
                return

            # 3. 데이터 파싱
            parsed_data = self.parse(fetch_result)

            # 4. 데이터 저장
            self.save(parsed_data, api_keys)

            self.stdout.write(self.style.SUCCESS(f'[{self.service_name}] 모든 작업이 성공적으로 완료되었습니다.'))

        except CommandError as e:
            # CommandError는 그대로 전달하여 스택 트레이스 없이 명확한 에러 메시지를 출력
            raise e
        except Exception as e:
            # 그 외 모든 예외는 CommandError로 래핑하여 상세 정보와 함께 출력
            self.stderr.write(self.style.ERROR(f'[{self.service_name}] 전체 작업 중 예상치 못한 오류 발생: {e}'))

    def get_api_keys(self):
        """
        필요한 API 키들을 딕셔너리 형태로 반환합니다.
        기본적으로 서울 API 키를 반환하며, 필요시 서브클래스에서 오버라이드합니다.
        """
        return {'seoul': settings.SEOUL_API_KEY}

    def is_data_valid(self, fetch_result):
        """
        수집된 데이터가 유효한지 확인합니다.
        기본적으로 True를 반환하며, 각 커맨드에서 필요에 따라 오버라이드하여 사용합니다.
        fetch_result가 None이거나 비어있는 경우 등을 체크할 수 있습니다.
        """
        if not fetch_result:
            return False
        # fetch_result가 튜플일 경우, 그 안의 첫 번째 요소(주요 데이터)를 확인
        if isinstance(fetch_result, tuple):
            return bool(fetch_result[0])
        return bool(fetch_result)

    def fetch(self, api_keys):
        """
        API로부터 원본 데이터를 수집합니다. 서브클래스에서 반드시 구현해야 합니다.
        """
        raise NotImplementedError("fetch() 메소드를 구현해야 합니다.")

    def parse(self, fetch_result):
        """
        수집된 원본 데이터를 파싱하여 처리 가능한 형태로 변환합니다.
        서브클래스에서 반드시 구현해야 합니다.
        """
        raise NotImplementedError("parse() 메소드를 구현해야 합니다.")

    def save(self, parsed_data, api_keys):
        """
        파싱된 데이터를 데이터베이스에 저장합니다.
        서브클래스에서 반드시 구현해야 합니다.
        """
        raise NotImplementedError("save() 메소드를 구현해야 합니다.")
