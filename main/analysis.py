import pandas as pd
import numpy as np
from django.db.models import Sum, Count, F, Avg
from django.db.models.functions import TruncDate
from .models import HangJeongDong, BusStop, BusData, BusDataHistory, HangJeongDongHistory, BusStopHistory

def get_analysis_data(start_date=None, end_date=None):
    """
    모든 분석의 기초가 되는 데이터를 수집하고 전처리합니다.
    선택적으로 날짜 범위를 지정하여 분석할 수 있습니다.
    
    Args:
        start_date (date, optional): 분석 시작 날짜
        end_date (date, optional): 분석 종료 날짜

    [수집 단계]
    1. 행정동 데이터: 이름, 인구수 (최신 Hot 데이터 기준)
    2. 버스 정류장 데이터: 행정동별 정류장 수 (활성 상태 기준)
    3. 버스 이용 데이터: 일자별/정류장별 승하차 합계 (Hot + Cold 통합)

    [반환 값]
    pandas DataFrame:
        - district_id: 행정동 코드
        - name: 행정동 이름
        - population: 인구수 (수요)
        - busstop_count: 정류장 수 (공급)
        - avg_weekday: 주중 일평균 이용객 수
        - avg_weekend: 주말 일평균 이용객 수
        - weekend_intensity_index: 주말 집중도 (주말 평균 / 주중 평균)
    """
    
    # 1. 행정동 데이터 및 2. 버스 정류장 데이터 (수요/공급)
    # 날짜 필터(end_date)가 있으면 History(Cold) 테이블에서 당시 데이터를 조회합니다.
    
    use_history = False
    
    if end_date:
        # (1) 행정동 인구 History 조회
        qs_hjd_hist = HangJeongDongHistory.objects.filter(timestamp__date__lte=end_date).values('district_id', 'name', 'population', 'timestamp')
        df_hjd_hist = pd.DataFrame(list(qs_hjd_hist))
        
        if not df_hjd_hist.empty:
            # 여러 시점의 데이터 중 end_date에 가장 가까운 최신 데이터만 남김
            df_districts = df_hjd_hist.sort_values('timestamp', ascending=False).drop_duplicates('district_id')
            use_history = True
        else:
            # 히스토리가 없으면 현재(Hot) 데이터 사용
            df_districts = pd.DataFrame(list(HangJeongDong.objects.all().values('district_id', 'name', 'population')))

        # (2) 정류장 수 History 조회
        qs_stop_hist = BusStopHistory.objects.filter(timestamp__date__lte=end_date, is_active=True).values('district_id', 'busstop_id', 'timestamp')
        df_stop_hist = pd.DataFrame(list(qs_stop_hist))
        
        if not df_stop_hist.empty:
            # 정류장별 최신 상태 추출
            df_stop_unique = df_stop_hist.sort_values('timestamp', ascending=False).drop_duplicates('busstop_id')
            # 행정동별 집계
            stop_counts = df_stop_unique['district_id'].value_counts().reset_index()
            stop_counts.columns = ['district_id', 'busstop_count']
            
            df_districts = df_districts.merge(stop_counts, on='district_id', how='left')
            df_districts['busstop_count'] = df_districts['busstop_count'].fillna(0)
        else:
             # 히스토리 없으면 현재 데이터 Fallback
             stop_counts = BusStop.objects.filter(is_active=True).values('district_id').annotate(count=Count('busstop_id'))
             df_stops = pd.DataFrame(list(stop_counts))
             if not df_stops.empty:
                df_districts = df_districts.merge(df_stops, on='district_id', how='left')
                df_districts['busstop_count'] = df_districts['count'].fillna(0)
                df_districts.drop(columns=['count'], inplace=True)
             else:
                df_districts['busstop_count'] = 0

    else:
        # 기본: 현재(Hot) 데이터 사용
        districts = HangJeongDong.objects.all().values('district_id', 'name', 'population')
        df_districts = pd.DataFrame(list(districts))
        
        if df_districts.empty:
            return pd.DataFrame()

        stop_counts = BusStop.objects.filter(is_active=True).values('district_id').annotate(
            count=Count('busstop_id')
        )
        df_stops = pd.DataFrame(list(stop_counts))
        
        if not df_stops.empty:
            df_districts = df_districts.merge(df_stops, on='district_id', how='left')
            df_districts['busstop_count'] = df_districts['count'].fillna(0)
            df_districts.drop(columns=['count'], inplace=True)
        else:
            df_districts['busstop_count'] = 0

    # 3. 버스 승하차 데이터 (이용 현황)
    # Hot(최신) 데이터와 Cold(과거) 데이터를 통합하여 분석합니다.
    
    # 정류장 ID -> 행정동 ID 매핑 테이블 생성 (Lookup 최적화)
    stop_to_district = dict(BusStop.objects.values_list('busstop_id', 'district_id'))
    
    def process_queryset(qs):
        """쿼리셋을 날짜별/정류장별 이용객 합계로 변환"""
        return qs.annotate(date=TruncDate('timestamp')).values(
            'busstop_id', 'date'
        ).annotate(
            daily_total=Sum(F('passengers_on') + F('passengers_off'))
        )

    # Hot + Cold 통합 (날짜 필터링 적용)
    qs_hot = BusData.objects.all()
    qs_cold = BusDataHistory.objects.all()

    if start_date:
        qs_hot = qs_hot.filter(timestamp__date__gte=start_date)
        qs_cold = qs_cold.filter(timestamp__date__gte=start_date)
    
    if end_date:
        qs_hot = qs_hot.filter(timestamp__date__lte=end_date)
        qs_cold = qs_cold.filter(timestamp__date__lte=end_date)

    hot_data = list(process_queryset(qs_hot))
    cold_data = list(process_queryset(qs_cold))
    
    all_usage_data = hot_data + cold_data
    df_usage = pd.DataFrame(all_usage_data)
    
    if not df_usage.empty:
        # 매핑: 정류장 -> 행정동
        df_usage['district_id'] = df_usage['busstop_id'].map(stop_to_district)
        
        # 행정동 정보가 유실된 데이터 제외
        df_usage = df_usage.dropna(subset=['district_id'])
        
        # 날짜 처리 및 요일 추출
        df_usage['date'] = pd.to_datetime(df_usage['date'])
        df_usage['day_of_week'] = df_usage['date'].dt.dayofweek # 0:월 ~ 6:일
        
        # 주말 정의 (토요일, 일요일)
        df_usage['is_weekend'] = df_usage['day_of_week'] >= 5
        
        # 집계: 행정동별, 평일/주말별 총 이용객 수
        # (1) 날짜별 합계 (일 단위 집계)
        district_daily = df_usage.groupby(['district_id', 'date', 'is_weekend'])['daily_total'].sum().reset_index()
        
        # (2) 평일/주말 평균 계산
        district_stats = district_daily.groupby(['district_id', 'is_weekend'])['daily_total'].mean().unstack(fill_value=0)
        
        # [수정] 데이터 기간에 따라 평일 또는 주말 데이터만 존재할 수 있으므로 컬럼 강제 정렬
        # False: 평일, True: 주말
        district_stats = district_stats.reindex(columns=[False, True], fill_value=0)
        
        district_stats.columns = ['avg_weekday', 'avg_weekend']
        
        # 메인 데이터프레임과 병합
        df_districts = df_districts.merge(district_stats, on='district_id', how='left')
        
    else:
        # 이용 데이터가 없는 경우 0으로 초기화
        df_districts['avg_weekday'] = 0
        df_districts['avg_weekend'] = 0
        
    # 결측치 처리
    df_districts['avg_weekday'] = df_districts['avg_weekday'].fillna(0)
    df_districts['avg_weekend'] = df_districts['avg_weekend'].fillna(0)
    
    # 주말 집중도 지수 (Weekend Intensity Index) 계산
    # 공식: 주말 평균 / 평일 평균
    # 평일 이용객이 0인 경우(나눗셈 오류 방지), 0으로 처리
    df_districts['weekend_intensity_index'] = df_districts.apply(
        lambda row: row['avg_weekend'] / row['avg_weekday'] if row['avg_weekday'] > 0 else 0, axis=1
    )
    
    return df_districts

def perform_statistical_analysis(df):
    """
    수집된 데이터를 바탕으로 통계 분석을 수행합니다.
    
    [수행 내용]
    1. 데이터 전처리: 결측치 및 이상치(인구 0명 등) 제외
    2. 거시적 분석: 인구-정류장 수 상관관계 및 회귀분석
    3. 미시적 분석: 회귀 잔차(Residual)를 통한 교통 소외/과잉 지역 도출
    4. 맥락적 분석: 주말 집중도를 이용한 지구 성격(주거/업무/상업) 분류
    """
    results = {}
    
    # --- 1. 데이터 전처리 (이상치 분리) ---
    # 분석 유효 데이터: 인구 > 0 그리고 정류장 > 0
    valid_df = df[(df['population'] > 0) & (df['busstop_count'] > 0)].copy()
    
    # 제외된 데이터 (데이터 오류 또는 미거주 지역)
    excluded_df = df[(df['population'] <= 0) | (df['busstop_count'] <= 0)].copy()
    
    results['excluded_districts'] = excluded_df[['name', 'population', 'busstop_count']].to_dict('records')
    
    # 유효 데이터가 너무 적으면 분석 중단
    if len(valid_df) < 2:
        return {
            'macro': {'correlation': 0, 'slope': 0, 'intercept': 0},
            'excluded_districts': results['excluded_districts']
        }, valid_df

    # --- 2. 거시적 분석 (회귀분석) ---
    x = valid_df['population'].values
    y = valid_df['busstop_count'].values
    
    # 1차 선형 회귀 (y = ax + b)
    slope, intercept = np.polyfit(x, y, 1)
    correlation = np.corrcoef(x, y)[0, 1]
    
    results['macro'] = {
        'slope': slope,
        'intercept': intercept,
        'correlation': correlation
    }
    
    # --- 3. 미시적 분석 (잔차 분석) ---
    # 잔차(Residual) = 실제값 - 예측값
    # 잔차가 음수(-): 예측보다 정류장이 적음 (공급 부족/소외)
    # 잔차가 양수(+): 예측보다 정류장이 많음 (공급 충분/과잉)
    valid_df['predicted_stops'] = slope * valid_df['population'] + intercept
    valid_df['residual'] = valid_df['busstop_count'] - valid_df['predicted_stops']
    
    # 공급 부족 상위 5곳 (잔차가 작은 순)
    results['marginalized_top5'] = valid_df.sort_values('residual').head(5)[
        ['name', 'population', 'busstop_count', 'predicted_stops', 'residual']
    ].to_dict('records')
    
    # 공급 과잉/충분 상위 5곳 (잔차가 큰 순)
    results['oversupplied_top5'] = valid_df.sort_values('residual', ascending=False).head(5)[
        ['name', 'population', 'busstop_count', 'predicted_stops', 'residual']
    ].to_dict('records')
    
    # --- 4. 맥락적 분석 (지구 분류) ---
    # 주말 집중도 지수(Weekend Intensity Index)에 따른 분류 기준:
    # - Business (업무지구): 0.65 미만 (주말에 텅 빔)
    # - Residential (주거지구): 0.65 이상 ~ 0.85 이하
    # - Cultural/Commercial (상업/문화지구): 0.85 초과 (주말에 붐빔)
    
    def classify(idx):
        if idx < 0.65: return 'Business'
        elif idx <= 0.85: return 'Residential'
        else: return 'Cultural_Commercial'
        
    valid_df['category'] = valid_df['weekend_intensity_index'].apply(classify)
    
    results['classification_counts'] = valid_df['category'].value_counts().to_dict()
    
    # 대표 업무 지구 데이터
    results['business_districts'] = valid_df[valid_df['category'] == 'Business'].sort_values('weekend_intensity_index')[
        ['name', 'avg_weekday', 'avg_weekend', 'weekend_intensity_index']
    ].head(5).to_dict('records')
    
    # 대표 상업/문화 지구 데이터
    results['cultural_districts'] = valid_df[valid_df['category'] == 'Cultural_Commercial'].sort_values('weekend_intensity_index', ascending=False)[
        ['name', 'avg_weekday', 'avg_weekend', 'weekend_intensity_index']
    ].head(5).to_dict('records')
    
    return results, valid_df
