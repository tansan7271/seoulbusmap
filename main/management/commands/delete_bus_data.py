from django.core.management.base import BaseCommand
from main.models import BusData, BusDataHistory
from datetime import datetime

class Command(BaseCommand):
    help = '특정 날짜의 버스 승하차 데이터를 삭제합니다.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            required=True,
            help='삭제할 날짜 (YYYYMMDD 형식)',
        )

    def handle(self, *args, **options):
        target_date_str = options['date']
        
        try:
            target_date = datetime.strptime(target_date_str, '%Y%m%d').date()
        except ValueError:
            self.stdout.write(self.style.ERROR('날짜 형식이 올바르지 않습니다. YYYYMMDD 형식으로 입력해주세요.'))
            return

        self.stdout.write(self.style.WARNING(f'[delete_bus_data] {target_date} 날짜의 데이터를 삭제합니다...'))

        # BusData 삭제
        deleted_count_hot, _ = BusData.objects.filter(timestamp__date=target_date).delete()
        self.stdout.write(self.style.SUCCESS(f'[delete_bus_data] BusData (Hot) 삭제 완료: {deleted_count_hot}건'))

        # BusDataHistory 삭제
        deleted_count_cold, _ = BusDataHistory.objects.filter(timestamp__date=target_date).delete()
        self.stdout.write(self.style.SUCCESS(f'[delete_bus_data] BusDataHistory (Cold) 삭제 완료: {deleted_count_cold}건'))

        total_deleted = deleted_count_hot + deleted_count_cold
        self.stdout.write(self.style.SUCCESS(f'[delete_bus_data] 총 {total_deleted}건의 데이터가 삭제되었습니다.'))
