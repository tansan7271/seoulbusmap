from django.db import models
from django.utils import timezone

class HangJeongDong(models.Model):
    """
    행정동의 코드, 이름, 인구수 정보를 모두 저장하는 모델
    """
    district_id = models.CharField(max_length=10, unique=True, help_text="행정동 ID")
    name = models.CharField(max_length=100, help_text="행정동 이름")
    population = models.IntegerField(help_text="총 생활 인구수", null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.district_id})"

class BusStop(models.Model):
    """
    버스 정류장 기본 정보를 저장하는 모델
    """
    busstop_id = models.CharField(max_length=20, unique=True, help_text="정류장 고유 ID")
    name = models.CharField(max_length=100, help_text="정류장 이름")
    longitude = models.DecimalField(max_digits=10, decimal_places=7, help_text="정류장 경도 (Longitude)")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, help_text="정류장 위도 (Latitude)")
    district_id = models.CharField(max_length=10, null=True, blank=True, help_text="정류장이 속한 행정동 ID")
    is_active = models.BooleanField(default=True, help_text="정류장 활성화 여부")

    def __str__(self):
        return f"{self.name} ({self.busstop_id})"

class BusData(models.Model):
    """
    시간대별 버스 정류장 데이터를 기록하는 모델
    """
    busstop_id = models.CharField(max_length=20, help_text="정류장 고유 ID")
    timestamp = models.DateTimeField(help_text="데이터 수집 시간")
    passengers_on = models.IntegerField(help_text="승차 인원")
    passengers_off = models.IntegerField(help_text="하차 인원")
    bus_frequency = models.IntegerField(help_text="버스 운행 횟수")

    class Meta:
        ordering = ['-timestamp', 'busstop_id']

    def __str__(self):
        return f"ID:{self.busstop_id} @ {self.timestamp.strftime('%Y-%m-%d %H:%M')}"