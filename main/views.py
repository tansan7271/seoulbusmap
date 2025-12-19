from django.shortcuts import render
from .models import HangJeongDong, BusStop, BusData, HangJeongDongHistory, BusStopHistory, BusDataHistory
from django.utils import timezone
from datetime import timedelta, datetime
from django.db.models import Avg, Sum, Count, F
from django.db.models.functions import TruncDay
from django.http import JsonResponse
import pandas as pd
import json
import os
from django.conf import settings
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
    최적화를 위해 미리 계산된(baked) JSON 데이터를 우선적으로 사용합니다.
    """
    baked_file_path = os.path.join(settings.BASE_DIR, 'main', 'static', 'main', 'data', 'analysis_result.json')
    
    # 1. Baked Data 확인
    if os.path.exists(baked_file_path):
        try:
            with open(baked_file_path, 'r', encoding='utf-8') as f:
                context = json.load(f)
                # context['generated_at']은 JSON에 이미 포함되어 있음
                return render(request, 'main/analysis_report.html', context)
        except Exception as e:
            print(f"Error loading baked data: {e}")
            # 로드 실패 시 Fallback 로직으로 진행
            pass

    # 2. Fallback: 실시간 계산 (기존 로직)
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

def 000(request):
    """
    김000 팀원을 위한 2.5D 시각화 전용 페이지
    """
    return render(request, 'main/000.html')


def 000_visualization(request):
    """
    김000 팀원을 위한 시각화 페이지 뷰.
    
    기존에는 이 뷰에서 실시간 분석을 수행했으나, 
    성능 최적화 및 구조 개선을 위해 클라이언트 사이드(JS)에서 
    미리 계산된 JSON 데이터(static/main/data/analysis_result.json)를 
    비동기로 가져와 렌더링하도록 변경되었습니다.
    
    따라서 이 뷰는 기본 템플릿만 렌더링하며, 
    네비게이션 바 구성을 위한 행정동 목록(hjd_list)만 컨텍스트로 전달합니다.
    """
    context = {
        'hjd_list': HangJeongDong.objects.all().order_by('name')
    }
    return render(request, 'main/000.html', context)

def api_analysis_data(request):
    """
    [API] 분석 데이터를 동적으로 계산하여 JSON으로 반환합니다 (날짜 검색용).
    """
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    start_date = None
    end_date = None

    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)

    # 데이터 분석 실행
    df = get_analysis_data(start_date, end_date)

    if df.empty:
         return JsonResponse({'error': 'No data found'}, status=404)

    results, valid_df = perform_statistical_analysis(df)
    
    # JSON 직렬화 준비: DataFrame -> Dict
    all_districts = valid_df.to_dict('records')
    
    # NaN 처리 (JSON 표준은 NaN 미지원)
    for d in all_districts:
        for k, v in d.items():
            if pd.isna(v):
                d[k] = None

    response_data = {
        'macro': results.get('macro'),
        'all_districts': all_districts,
        'generated_at': timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    return JsonResponse(response_data)