from django.db import models
from django.utils import timezone

# ==========================================
# Hot Data Models (Latest / Live Data)
# 최신 및 실시간으로 업데이트되는 데이터를 관리합니다.
# ==========================================

class HangJeongDong(models.Model):
    """
    행정동(District) 마스터 테이블.
    행정구역 코드, 이름, 그리고 인구 통계 정보를 저장합니다.
    """
    district_id = models.CharField(
        max_length=10, 
        unique=True, 
        verbose_name="행정동 ID",
        help_text="행정동 고유 코드 (예: 1111051500)"
    )
    name = models.CharField(
        max_length=100, 
        verbose_name="행정동 이름",
        help_text="행정동 명칭 (예: 종로구 청운효자동)"
    )
    population = models.IntegerField(
        null=True, 
        blank=True, 
        verbose_name="인구수",
        help_text="해당 행정동의 총 생활 인구수"
    )
    timestamp = models.DateTimeField(
        auto_now=True, 
        verbose_name="수집 일시",
        help_text="데이터가 마지막으로 업데이트된 시간"
    )

    class Meta:
        verbose_name = "행정동 (Hot)"
        verbose_name_plural = "행정동 목록 (Hot)"

    def __str__(self):
        return f"{self.name} ({self.district_id})"

class BusStop(models.Model):
    """
    버스 정류장(Bus Stop) 마스터 테이블.
    정류장의 위치(위경도), ID, 소속 행정동 등을 저장합니다.
    """
    busstop_id = models.CharField(
        max_length=20, 
        unique=True, 
        verbose_name="정류장 ID",
        help_text="버스 정류장 고유 ARS-ID 또는 표준 ID"
    )
    name = models.CharField(
        max_length=100, 
        verbose_name="정류장 이름",
        help_text="버스 정류장 명칭"
    )
    longitude = models.DecimalField(
        max_digits=10, 
        decimal_places=7, 
        verbose_name="경도",
        help_text="정류장 경도 (Longitude)"
    )
    latitude = models.DecimalField(
        max_digits=10, 
        decimal_places=7, 
        verbose_name="위도",
        help_text="정류장 위도 (Latitude)"
    )
    district_id = models.CharField(
        max_length=10, 
        null=True, 
        blank=True, 
        verbose_name="소속 행정동 ID",
        help_text="정류장이 위치한 행정동의 코드"
    )
    is_active = models.BooleanField(
        default=True, 
        verbose_name="활성 상태",
        help_text="현재 사용 중인 정류장 여부"
    )
    timestamp = models.DateTimeField(
        auto_now=True, 
        verbose_name="수집 일시",
        help_text="데이터가 마지막으로 업데이트된 시간"
    )

    class Meta:
        verbose_name = "버스 정류장 (Hot)"
        verbose_name_plural = "버스 정류장 목록 (Hot)"

    def __str__(self):
        return f"{self.name} ({self.busstop_id})"

class BusData(models.Model):
    """
    버스 승하차(Bus Usage) 데이터 테이블.
    일자별, 노선별, 정류장별 승/하차 인원 통계를 저장합니다.
    """
    busstop_id = models.CharField(
        max_length=20, 
        verbose_name="정류장 ID",
        help_text="관련 정류장 ID"
    )
    bus_id = models.CharField(
        max_length=20, 
        verbose_name="노선 ID",
        help_text="버스 노선 번호 또는 ID"
    )
    passengers_on = models.IntegerField(
        verbose_name="승차 인원",
        help_text="해당 일자의 총 승차 인원"
    )
    passengers_off = models.IntegerField(
        verbose_name="하차 인원",
        help_text="해당 일자의 총 하차 인원"
    )
    timestamp = models.DateTimeField(
        verbose_name="기준 일시",
        help_text="데이터 기준 날짜 및 시간"
    )

    class Meta:
        ordering = ['-timestamp', 'bus_id', 'busstop_id']
        verbose_name = "버스 승하차 데이터 (Hot)"
        verbose_name_plural = "버스 승하차 데이터 목록 (Hot)"

    def __str__(self):
        return f"Bus:{self.bus_id}, Stop:{self.busstop_id} @ {self.timestamp.strftime('%Y-%m-%d')}"

# ==========================================
# Cold Data Models (History / Archive)
# 과거 데이터를 보관(아카이빙)하기 위한 모델입니다.
# ==========================================

class HangJeongDongHistory(models.Model):
    """
    행정동 데이터 히스토리 (Cold Storage).
    시간 흐름에 따른 행정동 인구 변화 등을 추적하기 위해 사용됩니다.
    """
    district_id = models.CharField(max_length=10, verbose_name="행정동 ID")
    name = models.CharField(max_length=100, verbose_name="행정동 이름")
    population = models.IntegerField(null=True, blank=True, verbose_name="인구수")
    timestamp = models.DateTimeField(verbose_name="데이터 기준 일시")
    archived_at = models.DateTimeField(auto_now_add=True, verbose_name="아카이빙 시점")

    class Meta:
        ordering = ['-archived_at', 'district_id']
        verbose_name = "행정동 히스토리 (Cold)"
        verbose_name_plural = "행정동 히스토리 목록 (Cold)"

    def __str__(self):
        return f"{self.name} ({self.district_id}) @ {self.archived_at}"

class BusStopHistory(models.Model):
    """
    버스 정류장 데이터 히스토리 (Cold Storage).
    정류장 위치 변경, 폐쇄 등의 이력을 관리합니다.
    """
    busstop_id = models.CharField(max_length=20, verbose_name="정류장 ID")
    name = models.CharField(max_length=100, verbose_name="정류장 이름")
    longitude = models.DecimalField(max_digits=10, decimal_places=7, verbose_name="경도")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, verbose_name="위도")
    district_id = models.CharField(max_length=10, null=True, blank=True, verbose_name="소속 행정동 ID")
    is_active = models.BooleanField(default=True, verbose_name="활성 상태")
    timestamp = models.DateTimeField(verbose_name="데이터 기준 일시")
    archived_at = models.DateTimeField(auto_now_add=True, verbose_name="아카이빙 시점")

    class Meta:
        ordering = ['-archived_at', 'busstop_id']
        verbose_name = "버스 정류장 히스토리 (Cold)"
        verbose_name_plural = "버스 정류장 히스토리 목록 (Cold)"

    def __str__(self):
        return f"{self.name} ({self.busstop_id}) @ {self.archived_at}"

class BusDataHistory(models.Model):
    """
    버스 승하차 데이터 히스토리 (Cold Storage).
    오래된 승하차 데이터를 별도로 보관하여 Hot 테이블의 성능을 유지합니다.
    """
    busstop_id = models.CharField(max_length=20, verbose_name="정류장 ID")
    bus_id = models.CharField(max_length=20, verbose_name="노선 ID")
    passengers_on = models.IntegerField(verbose_name="승차 인원")
    passengers_off = models.IntegerField(verbose_name="하차 인원")
    timestamp = models.DateTimeField(verbose_name="데이터 기준 일시", help_text="실제 운행 일자")
    archived_at = models.DateTimeField(auto_now_add=True, verbose_name="아카이빙 시점")

    class Meta:
        ordering = ['-archived_at', 'busstop_id']
        verbose_name = "버스 승하차 히스토리 (Cold)"
        verbose_name_plural = "버스 승하차 히스토리 목록 (Cold)"

    def __str__(self):
        return f"Bus:{self.bus_id}, Stop:{self.busstop_id} @ {self.timestamp.strftime('%Y-%m-%d')}"