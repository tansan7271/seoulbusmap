import pandas as pd
import numpy as np
from django.db.models import Sum, Count, F, Avg
from django.db.models.functions import TruncDate
from .models import HangJeongDong, BusStop, BusData, BusDataHistory, HangJeongDongHistory

def get_analysis_data():
    """
    분석을 위한 데이터를 수집하고 집계합니다.
    반환값: pandas DataFrame
    컬럼: ['district_id', 'name', 'population', 'busstop_count', 
           'avg_weekday_passengers', 'avg_weekend_passengers', 'weekend_intensity_index']
    """
    
    # 1. 행정동 데이터 (인구수 - 수요)
    # 최신 Hot 데이터를 사용합니다.
    districts = HangJeongDong.objects.all().values('district_id', 'name', 'population')
    df_districts = pd.DataFrame(list(districts))
    
    if df_districts.empty:
        return pd.DataFrame()

    # 2. 버스 정류장 데이터 (공급)
    # 각 행정동별 활성화된 버스 정류장 수를 계산합니다.
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

    # 3. 버스 승하차 데이터 (이용 현황) - Hot + Cold 통합
    # 행정동 -> 날짜 -> 주중/주말 순으로 집계가 필요합니다.
    
    # 정류장 ID와 행정동 ID 매핑 정보를 가져옵니다.
    stop_to_district = dict(BusStop.objects.values_list('busstop_id', 'district_id'))
    
    # 쿼리셋 처리를 위한 헬퍼 함수
    def process_queryset(qs):
        # 정류장별, 날짜별로 그룹화하여 승하차 인원 합계를 구합니다.
        return qs.annotate(date=TruncDate('timestamp')).values(
            'busstop_id', 'date'
        ).annotate(
            daily_total=Sum(F('passengers_on') + F('passengers_off'))
        )

    # Hot 데이터와 Cold 데이터를 모두 가져옵니다.
    hot_data = list(process_queryset(BusData.objects.all()))
    cold_data = list(process_queryset(BusDataHistory.objects.all()))
    
    all_usage_data = hot_data + cold_data
    df_usage = pd.DataFrame(all_usage_data)
    
    if not df_usage.empty:
        # 정류장 ID를 행정동 ID로 매핑합니다.
        df_usage['district_id'] = df_usage['busstop_id'].map(stop_to_district)
        
        # 행정동 정보가 없는 데이터(매핑 실패 등)는 제외합니다.
        df_usage = df_usage.dropna(subset=['district_id'])
        
        # 날짜 형식을 변환하고 요일을 추출합니다.
        df_usage['date'] = pd.to_datetime(df_usage['date'])
        df_usage['day_of_week'] = df_usage['date'].dt.dayofweek # 0=월요일, 6=일요일
        
        # 주말 정의: 토요일(5), 일요일(6)
        df_usage['is_weekend'] = df_usage['day_of_week'] >= 5
        
        # 행정동 및 주말 여부로 그룹화하여 평균을 계산합니다.
        # 먼저, 각 날짜별 행정동 전체 승하차 인원을 합산합니다.
        district_daily = df_usage.groupby(['district_id', 'date', 'is_weekend'])['daily_total'].sum().reset_index()
        
        # 그 다음, 주중/주말별 일평균 이용객 수를 계산합니다.
        district_stats = district_daily.groupby(['district_id', 'is_weekend'])['daily_total'].mean().unstack(fill_value=0)
        
        # 컬럼 이름 변경
        district_stats.columns = ['avg_weekday', 'avg_weekend']
        
        # 메인 데이터프레임과 병합합니다.
        df_districts = df_districts.merge(district_stats, on='district_id', how='left')
        
    else:
        df_districts['avg_weekday'] = 0
        df_districts['avg_weekend'] = 0
        
    # 결측치(NaN)를 0으로 채웁니다.
    df_districts['avg_weekday'] = df_districts['avg_weekday'].fillna(0)
    df_districts['avg_weekend'] = df_districts['avg_weekend'].fillna(0)
    
    # 주말 집중도 지수(Weekend Intensity Index) 계산
    # 0으로 나누는 것을 방지합니다.
    df_districts['weekend_intensity_index'] = df_districts.apply(
        lambda row: row['avg_weekend'] / row['avg_weekday'] if row['avg_weekday'] > 0 else 0, axis=1
    )
    
    return df_districts

def perform_statistical_analysis(df):
    """
    회귀 분석 및 지구 분류를 수행합니다.
    데이터 전처리(이상치 제거)를 포함합니다.
    """
    results = {}
    
    # --- 데이터 전처리: 이상치 및 결측 데이터 분류 ---
    # 정류장이 아예 없거나(0개), 인구 데이터가 없는 경우 분석에서 제외하고 별도 리스트로 관리합니다.
    # 이는 행정구역 변경 등으로 인한 데이터 불일치일 가능성이 높습니다.
    
    # 분석 유효 데이터: 인구수 > 0 AND 정류장 수 > 0
    valid_df = df[(df['population'] > 0) & (df['busstop_count'] > 0)].copy()
    
    # 제외된 데이터 (데이터 부족/오류 의심)
    excluded_df = df[(df['population'] <= 0) | (df['busstop_count'] <= 0)].copy()
    
    results['excluded_districts'] = excluded_df[['name', 'population', 'busstop_count']].to_dict('records')
    
    if len(valid_df) < 2:
        return {
            'correlation': 0,
            'slope': 0,
            'intercept': 0,
            'r_value': 0,
            'p_value': 0,
            'std_err': 0
        }, valid_df

    # 1. 거시적 분석: 상관관계 및 회귀분석
    x = valid_df['population'].values
    y = valid_df['busstop_count'].values
    
    # 선형 회귀 (numpy polyfit 사용)
    # 기울기(slope), 절편(intercept)
    slope, intercept = np.polyfit(x, y, 1)
    
    # 상관계수 (Pearson Correlation Coefficient)
    correlation = np.corrcoef(x, y)[0, 1]
    
    results['macro'] = {
        'slope': slope,
        'intercept': intercept,
        'correlation': correlation
    }
    
    # 2. 미시적 분석: 잔차(Residual) 분석
    # 예측값 = 기울기 * 인구수 + 절편
    valid_df['predicted_stops'] = slope * valid_df['population'] + intercept
    valid_df['residual'] = valid_df['busstop_count'] - valid_df['predicted_stops']
    
    # 교통 소외 지역 (잔차 < 0) vs 공급 과잉 지역 (잔차 > 0)
    # 잔차가 가장 작은(음수) 순서대로 정렬 (소외 지역)
    results['marginalized_top5'] = valid_df.sort_values('residual').head(5)[
        ['name', 'population', 'busstop_count', 'predicted_stops', 'residual']
    ].to_dict('records')
    
    # 잔차가 가장 큰(양수) 순서대로 정렬 (과잉/거점 지역)
    results['oversupplied_top5'] = valid_df.sort_values('residual', ascending=False).head(5)[
        ['name', 'population', 'busstop_count', 'predicted_stops', 'residual']
    ].to_dict('records')
    
    # 3. 맥락 분석: 지구 성격 분류
    # 전체 데이터의 주말 집중도 평균은 약 0.71입니다.
    # 이를 기준으로 분포를 고려하여 임계값을 조정했습니다.
    # 업무 지구: Index < 0.65 (하위 약 25%)
    # 주거 지구: 0.65 <= Index <= 0.85
    # 문화/상업 지구: Index > 0.85 (상위 약 5~10%)
    
    def classify(idx):
        if idx < 0.65: return 'Business'
        elif idx <= 0.85: return 'Residential'
        else: return 'Cultural_Commercial'
        
    valid_df['category'] = valid_df['weekend_intensity_index'].apply(classify)
    
    results['classification_counts'] = valid_df['category'].value_counts().to_dict()
    
    # 대표 업무 지구 추출
    results['business_districts'] = valid_df[valid_df['category'] == 'Business'].sort_values('weekend_intensity_index')[
        ['name', 'avg_weekday', 'avg_weekend', 'weekend_intensity_index']
    ].head(5).to_dict('records')
    
    # 대표 문화/상업 지구 추출
    results['cultural_districts'] = valid_df[valid_df['category'] == 'Cultural_Commercial'].sort_values('weekend_intensity_index', ascending=False)[
        ['name', 'avg_weekday', 'avg_weekend', 'weekend_intensity_index']
    ].head(5).to_dict('records')
    
    return results, valid_df
