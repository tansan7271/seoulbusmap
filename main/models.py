from django.db import models
from django.utils import timezone

# Hot 모델: 최신 정보만을 담고 있는 데이터셋.

class HangJeongDong(models.Model):
    # 행정동의 코드, 이름, 인구수 정보를 모두 저장하는 모델
    district_id = models.CharField(max_length=10, unique=True, help_text="행정동 ID")
    name = models.CharField(max_length=100, help_text="행정동 이름")
    population = models.IntegerField(help_text="총 생활 인구수", null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.district_id})"

class BusStop(models.Model):
    # 버스 정류장 기본 정보를 저장하는 모델
    busstop_id = models.CharField(max_length=20, unique=True, help_text="정류장 ID")
    name = models.CharField(max_length=100, help_text="정류장 이름")
    longitude = models.DecimalField(max_digits=10, decimal_places=7, help_text="정류장 경도 (Longitude)")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, help_text="정류장 위도 (Latitude)")
    district_id = models.CharField(max_length=10, null=True, blank=True, help_text="정류장이 속한 행정동 ID")
    is_active = models.BooleanField(default=True, help_text="정류장 활성화 여부")

    def __str__(self):
        return f"{self.name} ({self.busstop_id})"

class BusData(models.Model):
    # 일자별/노선별/정류장별 버스 승하차 데이터를 기록하는 모델
    busstop_id = models.CharField(max_length=20, help_text="정류장 ID")
    bus_id = models.CharField(max_length=20, help_text="노선 ID")
    timestamp = models.DateTimeField(help_text="데이터 수집 시간")
    passengers_on = models.IntegerField(help_text="승차 인원")
    passengers_off = models.IntegerField(help_text="하차 인원")

    class Meta:
        ordering = ['-timestamp', 'bus_id', 'busstop_id']

    def __str__(self):
        return f"Bus:{self.bus_id}, Stop:{self.busstop_id} @ {self.timestamp.strftime('%Y-%m-%d')}"

# Cold 모델: 최신이 아닌 정보를 보존하는 데이터셋.

class HangJeongDongHistory(models.Model):
    district_id = models.CharField(max_length=10, help_text="행정동 ID")
    name = models.CharField(max_length=100, help_text="행정동 이름")
    population = models.IntegerField(help_text="총 생활 인구수", null=True, blank=True)
    archived_at = models.DateTimeField(auto_now_add=True, help_text="데이터 보관 시점")

    class Meta:
        ordering = ['-archived_at', 'district_id']

    def __str__(self):
        return f"{self.name} ({self.district_id}) @ {self.archived_at}"

class BusStopHistory(models.Model):
    busstop_id = models.CharField(max_length=20, help_text="정류장 ID")
    name = models.CharField(max_length=100, help_text="정류장 이름")
    longitude = models.DecimalField(max_digits=10, decimal_places=7, help_text="정류장 경도 (Longitude)")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, help_text="정류장 위도 (Latitude)")
    district_id = models.CharField(max_length=10, null=True, blank=True, help_text="정류장이 속한 행정동 ID")
    is_active = models.BooleanField(default=True, help_text="정류장 활성화 여부")
    archived_at = models.DateTimeField(auto_now_add=True, help_text="데이터 보관 시점")

    class Meta:
        ordering = ['-archived_at', 'busstop_id']

    def __str__(self):
        return f"{self.name} ({self.busstop_id}) @ {self.archived_at}"

class BusDataHistory(models.Model):
    busstop_id = models.CharField(max_length=20, help_text="정류장 ID")
    bus_id = models.CharField(max_length=20, help_text="노선 ID")
    timestamp = models.DateTimeField(help_text="데이터 기준 시간")
    passengers_on = models.IntegerField(help_text="승차 인원")
    passengers_off = models.IntegerField(help_text="하차 인원")
    archived_at = models.DateTimeField(auto_now_add=True, help_text="데이터 보관 시점")

    class Meta:
        ordering = ['-archived_at', 'timestamp']

    def __str__(self):
        return f"Bus:{self.bus_id}, Stop:{self.busstop_id} @ {self.timestamp.strftime('%Y-%m-%d')}"