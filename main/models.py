from django.db import models

class HangJeongDong(models.Model):
    """
    서울시 행정동 정보를 저장하는 모델
    """
    name = models.CharField(max_length=100, unique=True, help_text="행정동 이름")
    population = models.IntegerField(help_text="거주 인구 수", null=True, blank=True)

    def __str__(self):
        return self.name

class BusStop(models.Model):
    """
    버스 정류장 기본 정보를 저장하는 모델
    """
    api_id = models.CharField(max_length=20, unique=True, help_text="API에서 사용하는 정류장 고유 ID")
    name = models.CharField(max_length=100, help_text="정류장 이름")
    longitude = models.DecimalField(max_digits=10, decimal_places=7, help_text="정류장 경도 (Longitude)")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, help_text="정류장 위도 (Latitude)")
    district = models.ForeignKey(
        HangJeongDong,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="정류장이 속한 행정동"
    )
    is_active = models.BooleanField(default=True, help_text="정류장 활성화 여부")

    def __str__(self):
        return f"{self.name} ({self.api_id})"

class BusData(models.Model):
    """
    시간대별 버스 정류장 데이터를 기록하는 모델 (시계열 데이터)
    """
    bus_stop = models.ForeignKey(BusStop, on_delete=models.CASCADE, help_text="대상 버스 정류장")
    timestamp = models.DateTimeField(help_text="데이터 수집 시간")
    passengers_on = models.IntegerField(help_text="승차 인원")
    passengers_off = models.IntegerField(help_text="하차 인원")
    bus_frequency = models.IntegerField(help_text="버스 운행 횟수")

    class Meta:
        unique_together = ('bus_stop', 'timestamp')
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.bus_stop} @ {self.timestamp.strftime('%Y-%m-%d %H:%M')}"