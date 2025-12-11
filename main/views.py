from django.shortcuts import render
from .models import HangJeongDong, BusStop, BusData, HangJeongDongHistory, BusStopHistory, BusDataHistory
from django.utils import timezone
from datetime import timedelta
from django.db.models import Avg, Sum, Count, F
from django.db.models.functions import TruncDay
import json
from collections import defaultdict

def index(request):
    hjd_list = HangJeongDong.objects.all().order_by('name')

    # 데이터 최종 업데이트 시간 조회 (Hot 테이블 기준)
    last_hjd_update = HangJeongDong.objects.order_by('-timestamp').first()
    last_busstop_update = BusStop.objects.order_by('-timestamp').first()
    last_busdata_update = BusData.objects.order_by('-timestamp').first()

    context = {
        'hjd_list': hjd_list,
        'last_hjd_update_time': last_hjd_update.timestamp.strftime("%Y-%m-%d %H:%M") if last_hjd_update else None,
        'last_busstop_update_time': last_busstop_update.timestamp.strftime("%Y-%m-%d %H:%M") if last_busstop_update else None,
        'last_busdata_update_time': last_busdata_update.timestamp.strftime("%Y-%m-%d %H:%M") if last_busdata_update else None,
    }
    return render(request, 'main/index.html', context)


def hangjeongdong_detail(request, hjd_code):
    hjd_list = HangJeongDong.objects.all().order_by('name')
    selected_hjd = HangJeongDong.objects.get(district_id=hjd_code)
    bus_stops_qs = BusStop.objects.filter(district_id=hjd_code).order_by('name')

    # Hot 데이터셋에서 가장 최신 날짜를 찾음
    latest_date = BusData.objects.order_by('-timestamp').values_list('timestamp__date', flat=True).first()

    passenger_counts = {}
    if latest_date:
        # 최신 날짜에 해당하는 모든 정류장의 승하차 인원 합계를 한 번의 쿼리로 계산
        counts = BusData.objects.filter(
            timestamp__date=latest_date,
            busstop_id__in=bus_stops_qs.values_list('busstop_id', flat=True)
        ).values('busstop_id').annotate(
            total_passengers=Sum(F('passengers_on') + F('passengers_off'))
        )
        # 템플릿에서 쉽게 찾아 쓸 수 있도록 딕셔너리로 변환
        passenger_counts = {item['busstop_id']: item['total_passengers'] for item in counts}

    # 각 버스 정류장 객체에 최신 승하차 인원 정보 추가
    bus_stops_with_counts = []
    for stop in bus_stops_qs:
        stop.latest_passenger_count = passenger_counts.get(stop.busstop_id)
        bus_stops_with_counts.append(stop)

    context = {
        'hjd_list': hjd_list,
        'selected_hjd_code': hjd_code,
        'selected_hjd': selected_hjd,
        'bus_stops': bus_stops_with_counts,
        'bus_stop_count': bus_stops_qs.count(),
        'latest_data_date': latest_date,
    }

    return render(request, 'main/hangjeongdong_detail.html', context)


def busstop_detail(request, hjd_code, busstop_id):
    bus_stop = BusStop.objects.get(busstop_id=busstop_id)
    hangjeongdong = HangJeongDong.objects.get(district_id=hjd_code)

    # --- 1. 날짜 필터링 준비 ---
    today = timezone.now().date()
    default_start_date = today - timedelta(days=6)
    
    start_date_str = request.GET.get('start_date', default_start_date.strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', today.strftime('%Y-%m-%d'))

    # --- 2. 데이터 조회 (Hot/Cold 데이터 통합) ---
    # Django ORM은 union 이후에 집계를 지원하지 않으므로, 
    # (1) 차트/전체통계용 데이터와 (2) 상세 테이블용 데이터를 별도로 준비.

    # (1) 차트 및 전체 통계용 데이터 준비
    hot_daily_summary = BusData.objects.filter(
        busstop_id=busstop_id,
        timestamp__date__gte=start_date_str,
        timestamp__date__lte=end_date_str
    ).annotate(day=TruncDay('timestamp')).values('day').annotate(daily_on=Sum('passengers_on'), daily_off=Sum('passengers_off'))

    cold_daily_summary = BusDataHistory.objects.filter(
        busstop_id=busstop_id,
        timestamp__date__gte=start_date_str,
        timestamp__date__lte=end_date_str
    ).annotate(day=TruncDay('timestamp')).values('day').annotate(daily_on=Sum('passengers_on'), daily_off=Sum('passengers_off'))

    aggregated_daily_summary = defaultdict(lambda: {'daily_on': 0, 'daily_off': 0})
    for item in hot_daily_summary:
        aggregated_daily_summary[item['day']]['daily_on'] += item['daily_on']
        aggregated_daily_summary[item['day']]['daily_off'] += item['daily_off']
    for item in cold_daily_summary:
        aggregated_daily_summary[item['day']]['daily_on'] += item['daily_on']
        aggregated_daily_summary[item['day']]['daily_off'] += item['daily_off']

    sorted_chart_days = sorted(aggregated_daily_summary.keys())
    chart_labels = [day.strftime('%Y-%m-%d') for day in sorted_chart_days]
    chart_data_on = [aggregated_daily_summary[day]['daily_on'] for day in sorted_chart_days]
    chart_data_off = [aggregated_daily_summary[day]['daily_off'] for day in sorted_chart_days]

    # 일별 집계 데이터에서 전체 통계 다시 계산
    total_stats = {
        'total_passengers_on': sum(d['daily_on'] for d in aggregated_daily_summary.values()),
        'total_passengers_off': sum(d['daily_off'] for d in aggregated_daily_summary.values())
    }

    # (2) 상세 테이블용 전체 데이터 준비
    common_fields = ['timestamp', 'bus_id', 'passengers_on', 'passengers_off']
    hot_records_qs = BusData.objects.filter(
        busstop_id=busstop_id, timestamp__date__gte=start_date_str, timestamp__date__lte=end_date_str
    ).values(*common_fields).order_by()

    cold_records_qs = BusDataHistory.objects.filter(
        busstop_id=busstop_id, timestamp__date__gte=start_date_str, timestamp__date__lte=end_date_str
    ).values(*common_fields).order_by()

    combined_records_qs = hot_records_qs.union(cold_records_qs)

    # --- 3. 템플릿 컨텍스트 준비 ---
    quick_dates = {
        'today_str': today.strftime('%Y-%m-%d'),
        'seven_days_ago_str': (today - timedelta(days=6)).strftime('%Y-%m-%d'),
        'thirty_days_ago_str': (today - timedelta(days=29)).strftime('%Y-%m-%d'),
        'three_months_ago_str': (today - timedelta(days=89)).strftime('%Y-%m-%d'),
    }

    context = {
        # 정류장 기본 정보
        'bus_stop': bus_stop,
        'hangjeongdong': hangjeongdong,
        # 날짜 필터 정보
        'start_date': start_date_str,
        'end_date': end_date_str,
        'quick_dates': quick_dates,
        # 통계 및 상세 데이터
        'stats': total_stats,
        'bus_records': combined_records_qs.order_by('-timestamp'),
        # 차트 데이터
        'chart_labels': json.dumps(chart_labels),
        'chart_data_on': json.dumps(chart_data_on),
        'chart_data_off': json.dumps(chart_data_off),
    }
    
    return render(request, 'main/busstop_detail.html', context)



from .analysis import get_analysis_data, perform_statistical_analysis

def analysis_report(request):
    """
    분석 보고서를 생성하고 표시합니다.
    """
    # 1. 집계 데이터 가져오기
    df = get_analysis_data()
    
    if df.empty:
        context = {'error': '분석할 데이터가 없습니다.'}
        return render(request, 'main/analysis_report.html', context)
        
    # 2. 분석 수행
    results, valid_df = perform_statistical_analysis(df)
    
    # 3. 컨텍스트 준비
    # 템플릿 필터 오류 방지를 위해 뷰에서 숫자를 문자열로 포맷팅합니다.
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
        
    # 제외된 지역 포맷팅
    for item in results.get('excluded_districts', []):
        item['population'] = f"{item['population']:.0f}"
        item['busstop_count'] = f"{item['busstop_count']:.0f}"

    context = {
        'macro': results.get('macro'),
        'marginalized_top5': results.get('marginalized_top5'),
        'oversupplied_top5': results.get('oversupplied_top5'),
        'classification_counts': results.get('classification_counts'),
        'business_districts': results.get('business_districts'),
        'cultural_districts': results.get('cultural_districts'),
        'excluded_districts': results.get('excluded_districts'), # 추가된 항목
        'total_districts': len(valid_df),
        'excluded_count': len(results.get('excluded_districts', [])),
    }
    
    return render(request, 'main/analysis_report.html', context)


from django.conf import settings
import os
import xml.etree.ElementTree as ET

def 000_visualization(request):
    """
    000의 시각화 페이지.
    1. 거시적 분석 (상관관계 산점도)
    2. 미시적 분석 (지도 시각화)
    """
    # 1. 데이터 분석 수행
    df = get_analysis_data()
    if df.empty:
        return render(request, 'main/000.html', {'error': '분석할 데이터가 없습니다.'})

    results, valid_df = perform_statistical_analysis(df)

    if valid_df.empty:
        print("valid_df is empty after statistical analysis.")
        return render(request, 'main/000.html', {'error': '분석할 데이터가 없습니다.'})

    # 2. SVG 파일 읽고 데이터 주입
    svg_path = os.path.join(settings.BASE_DIR, 'main', 'static', 'main', 'svg', '11_서울특별시.svg')
    svg_content = f"<p>SVG 파일을 찾을 수 없습니다. '{svg_path}' 경로를 확인해주세요.</p>"
    try:
        # SVG 파일에 네임스페이스가 있을 수 있으므로, 처리 준비
        ET.register_namespace('', "http://www.w3.org/2000/svg")
        tree = ET.parse(svg_path)
        root = tree.getroot()
        
        # 데이터프레임을 district_id 기준으로 정렬
        sorted_df = valid_df.sort_values('district_id').reset_index(drop=True)
        district_ids = sorted_df['district_id'].tolist()

        # SVG 내의 모든 path 태그 찾기
        # 네임스페이스를 고려하여 findall 사용
        paths = root.findall('.//{http://www.w3.org/2000/svg}path')
        
        print(f"Number of paths found in SVG: {len(paths)}")
        print(f"Number of districts in data: {len(district_ids)}")

        # path 태그와 데이터를 순서대로 매핑하여 data-district-id 추가
        # path가 더 많거나, 데이터가 더 많거나, 숫자가 다를 경우를 대비
        for i, path in enumerate(paths):
            if i < len(district_ids):
                district_id = district_ids[i]
                path.set('data-district-id', str(district_id))
            else:
                # 데이터보다 많은 path가 있는 경우, ID를 부여하지 않음
                pass
        
        # 수정된 XML을 문자열로 변환
        svg_content = ET.tostring(root, encoding='unicode')

    except FileNotFoundError:
        # svg_content는 이미 에러 메시지로 초기화되어 있음
        pass
    except ET.ParseError:
        svg_content = "<p>SVG 파일 파싱에 실패했습니다. 파일이 유효한 XML 형식이 아닙니다.</p>"


    # 3. 템플릿으로 전달할 데이터 준비
    # 거시분석용 데이터 (산점도)
    scatter_data = valid_df[['name', 'population', 'busstop_count']].to_dict('records')
    
    # 미시분석용 데이터 (지도 색칠)
    residual_map = valid_df.set_index('district_id')['residual'].to_dict()

    context = {
        'svg_content': svg_content,
        'scatter_data': json.dumps(scatter_data),
        'macro_results': json.dumps(results.get('macro', {})),
        'residual_map': json.dumps(residual_map),
        'hjd_list': HangJeongDong.objects.all().order_by('name') # 네비게이션용
    }
    
    return render(request, 'main/000.html', context)