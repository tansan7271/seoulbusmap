from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'SQLite 데이터베이스의 용량을 최적화(VACUUM)합니다.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('[vacuum_db] 데이터베이스 최적화(VACUUM) 작업을 시작합니다...'))
        self.stdout.write(self.style.WARNING('[vacuum_db] 데이터 양에 따라 시간이 걸릴 수 있습니다.'))

        with connection.cursor() as cursor:
            cursor.execute("VACUUM")
            
        self.stdout.write(self.style.SUCCESS('[vacuum_db] 데이터베이스 최적화가 완료되었습니다.'))
        self.stdout.write(self.style.SUCCESS('[vacuum_db] 이제 db.sqlite3 파일 용량이 줄어들었을 것입니다.'))
