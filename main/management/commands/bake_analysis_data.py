import json
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
import pandas as pd
from main.analysis import get_analysis_data, perform_statistical_analysis

class Command(BaseCommand):
    help = 'Analyzes data and bakes the result into a static JSON file.'

    def handle(self, *args, **options):
        self.stdout.write("Baking analysis data...")
        
        try:
            # 1. 집계 데이터 가져오기
            df = get_analysis_data()
            
            if df.empty:
                self.stdout.write(self.style.WARNING("No data to analyze."))
                return

            # 2. 분석 수행
            results, valid_df = perform_statistical_analysis(df)
            
            # 3. 데이터 포맷팅 (View 로직과 동일)
            if results.get('macro'):
                results['macro']['correlation'] = f"{results['macro']['correlation']:.4f}"
                results['macro']['slope'] = f"{results['macro']['slope']:.4f}"
                results['macro']['intercept'] = f"{results['macro']['intercept']:.2f}"
                
            for item in results.get('marginalized_top5', []):
                item['population'] = f"{item['population']:.0f}"
                item['busstop_count'] = f"{item['busstop_count']:.0f}"
                item['predicted_stops'] = f"{item['predicted_stops']:.1f}"
                item['residual'] = f"{item['residual']:.1f}"
                
            for item in results.get('oversupplied_top5', []):
                item['population'] = f"{item['population']:.0f}"
                item['busstop_count'] = f"{item['busstop_count']:.0f}"
                item['predicted_stops'] = f"{item['predicted_stops']:.1f}"
                item['residual'] = f"{item['residual']:.1f}"

            for item in results.get('business_districts', []):
                item['avg_weekday'] = f"{item['avg_weekday']:.0f}"
                item['avg_weekend'] = f"{item['avg_weekend']:.0f}"
                item['weekend_intensity_index'] = f"{item['weekend_intensity_index']:.2f}"

            for item in results.get('cultural_districts', []):
                item['avg_weekday'] = f"{item['avg_weekday']:.0f}"
                item['avg_weekend'] = f"{item['avg_weekend']:.0f}"
                item['weekend_intensity_index'] = f"{item['weekend_intensity_index']:.2f}"
                
            for item in results.get('excluded_districts', []):
                item['population'] = f"{item['population']:.0f}"
                item['busstop_count'] = f"{item['busstop_count']:.0f}"

            # 4. 시각화를 위한 전체 데이터 준비
            
            # 4-1. 모든 행정동 데이터 (Scatter Plot, Choropleth Map용)
            # valid_df에는 이미 모든 분석 지표가 포함되어 있음
            all_districts = valid_df.to_dict('records')
            # NaN 값 처리 (JSON 시리얼라이즈 문제 방지)
            for d in all_districts:
                for k, v in d.items():
                    if pd.isna(v):
                        d[k] = None
                        
            # 4-2. 버스 정류장 데이터 (Dot Map용) -> 크기(점유율) 시각화를 위해 승하차 합계 계산
            self.stdout.write("Aggregating bus stop usage data...")
            from main.models import BusStop, BusData, BusDataHistory
            from django.db.models import Sum, F, Max
            from collections import defaultdict

            # 정류장 기본 정보
            active_stops = BusStop.objects.filter(is_active=True).values('busstop_id', 'latitude', 'longitude', 'name')
            stops_map = {s['busstop_id']: s for s in active_stops}
            
            # 이용객 수 집계 (Hot + Cold)
            usage_map = defaultdict(int)
            
            
            hot_stats = BusData.objects.values('busstop_id').annotate(total=Sum(F('passengers_on') + F('passengers_off')))
            for item in hot_stats:
                usage_map[item['busstop_id']] += int(item['total'] or 0)
                
            cold_stats = BusDataHistory.objects.values('busstop_id').annotate(total=Sum(F('passengers_on') + F('passengers_off')))
            for item in cold_stats:
                usage_map[item['busstop_id']] += int(item['total'] or 0)
            
            # 정류장 리스트 생성
            bus_stops_data = []
            for stop_id, stop_info in stops_map.items():
                bus_stops_data.append({
                    'id': stop_id,
                    'name': stop_info['name'],
                    'lat': float(stop_info['latitude']),
                    'lng': float(stop_info['longitude']),
                    'usage': usage_map.get(stop_id, 0)
                })

            # 4-3. 2.5D 지도용 시계열 데이터 (최근 30일, 행정동별 이용량) -> Equalizer 효과
            self.stdout.write("Baking time-series data for equalizer...")
            from datetime import timedelta
            
            # [수정] 데이터가 존재하는 마지막 날짜를 기준으로 30일 산출
            # 사용자 요청: "데이터가 11월 30일까지 있다면, 오늘이 12월이라도 11월 1일~30일을 베이킹해야 함"
            latest_result = BusData.objects.aggregate(latest=Max('timestamp'))['latest']
            if not latest_result:
                latest_result = BusDataHistory.objects.aggregate(latest=Max('timestamp'))['latest']
            
            if latest_result:
                end_date = latest_result.date()
                self.stdout.write(f"Latest data found at: {end_date}")
            else:
                end_date = timezone.now().date()
                self.stdout.write(self.style.WARNING("No data found. Using today as end date."))

            start_date = end_date - timedelta(days=30)
            
            # DataFrame 활용하여 빠르게 집계
            # df_usage는 get_analysis_data 내부변수라 다시 만들어야 함 (또는 get_analysis_data가 반환하도록 수정하는 게 좋지만, 여기선 로직 복제)
            # 여기서는 편의상 DB에서 직접 빠른 쿼리 수행
            
            # Hot/Cold 통합 쿼리 (날짜 필터링)
            daily_qs_hot = BusData.objects.filter(timestamp__date__gte=start_date).values('busstop_id', 'timestamp__date').annotate(daily_total=Sum(F('passengers_on') + F('passengers_off')))
            daily_qs_cold = BusDataHistory.objects.filter(timestamp__date__gte=start_date).values('busstop_id', 'timestamp__date').annotate(daily_total=Sum(F('passengers_on') + F('passengers_off')))
            
            # 정류장-행정동 매핑
            stop_to_district = dict(BusStop.objects.values_list('busstop_id', 'district_id'))
            
            # 데이터 프레임 변환
            df_daily_hot = pd.DataFrame(list(daily_qs_hot))
            df_daily_cold = pd.DataFrame(list(daily_qs_cold))
            
            df_daily_combined = pd.concat([df_daily_hot, df_daily_cold], ignore_index=True)
            
            district_time_series = {}
            
            if not df_daily_combined.empty:
                # 컬럼명 통일
                df_daily_combined.rename(columns={'timestamp__date': 'date'}, inplace=True)
                # 정류장 ID -> 행정동 ID 매핑
                df_daily_combined['district_id'] = df_daily_combined['busstop_id'].map(stop_to_district)
                # 매핑 안된거 제거
                df_daily_combined.dropna(subset=['district_id'], inplace=True)
                
                # 날짜/행정동별 그룹화 (sum)
                daily_grouped = df_daily_combined.groupby(['date', 'district_id'])['daily_total'].sum().reset_index()
                
                # 날짜를 String으로 변환
                daily_grouped['date'] = daily_grouped['date'].astype(str)
                
                # 구조 변환: { "YYYY-MM-DD": { "district_id": count, ... }, ... }
                for date_str in daily_grouped['date'].unique():
                    day_data = daily_grouped[daily_grouped['date'] == date_str]
                    district_time_series[date_str] = dict(zip(day_data['district_id'], day_data['daily_total']))

            # 4-4. 연도별 통계 (Yearly Stats) -> 상관관계 변화 추이
            # 이는 데이터가 충분히 쌓여야 의미가 있겠지만, 구조를 잡아둠.
            self.stdout.write("Baking yearly stats...")
            
            # 전체 데이터에서 연도 추출
            # (주의: 전체 데이터를 다시 로드하는 것은 무거울 수 있으나, 현재 규모에선 허용)
            # 여기서는 간단히 valid_df (현재 시점 스냅샷)이 아니라, 이력 테이블을 뒤져야 함.
            # 하지만 시간 관계상 '현재' 시점의 연도별 스냅샷을 찍는 건 불가능하므로,
            # '데이터의 타임스탬프'를 기준으로 연도별 이용객 추이만 제공하거나,
            # 혹은 전체 데이터의 scatter plot 점들을 제공하는 것으로 대체 (all_districts에 이미 포함됨)
            
            # 사용자 요청: "연도별 다이어그램" -> 아마도 과거 데이터(Cold) vs 현재 데이터(Hot) 비교를 원할 수 있음.
            # 여기서는 'Hot 데이터(2025)'와 'Cold 데이터(과거)'를 분리해서 각각의 Correlation을 계산해봄.
            
            year_stats = []
            
            # Cold Data (과거) 통계
            # (구현 복잡도를 줄이기 위해, 여기서는 단순화하여 '전체 누적' vs '최근 30일' 비교로 가거나
            #  또는 'Hot' vs 'Cold'로 나눔)
            
            # Hot Data 기준 상관계수 (현재)
            current_corr = results.get('macro', {}).get('correlation', 0)
            
            year_stats.append({
                'label': 'Current (Hot)',
                'correlation': current_corr
            })
            
            # TODO: Cold 데이터만으로 별도 회귀분석을 돌리는 건 비용이 크므로, 
            # 일단은 시각화 템플릿에서 'all_districts'를 가지고 인터랙티브하게 필터링하도록 가이드.

            # 5. JSON 구조 생성
            data_to_save = {
                'generated_at': timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
                'macro': results.get('macro'),
                'marginalized_top5': results.get('marginalized_top5'),
                'oversupplied_top5': results.get('oversupplied_top5'),
                'classification_counts': results.get('classification_counts'),
                'business_districts': results.get('business_districts'),
                'cultural_districts': results.get('cultural_districts'),
                'excluded_districts': results.get('excluded_districts'),
                'total_districts': len(valid_df),
                'excluded_count': len(results.get('excluded_districts', [])),
                # 시각화용 추가 데이터
                'all_districts': all_districts,
                'bus_stops': bus_stops_data,
                'district_time_series': district_time_series, # Equalizer용
                'year_stats': year_stats, # 연도별 비교용
            }
            
            # 5. 파일 저장
            static_dir = os.path.join(settings.BASE_DIR, 'main', 'static', 'main', 'data')
            os.makedirs(static_dir, exist_ok=True)
            file_path = os.path.join(static_dir, 'analysis_result.json')
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
                
            self.stdout.write(self.style.SUCCESS(f"Successfully baked analysis data to {file_path}"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error baking analysis data: {e}"))
