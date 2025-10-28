from django.shortcuts import render
from .models import HangJeongDong, BusStop, BusData, HangJeongDongHistory, BusStopHistory
from django.utils import timezone
from datetime import timedelta
from django.db.models import Avg, Sum, Count
from django.db.models.functions import TruncHour, TruncDay
import json

def index(request):
    hjd_list = HangJeongDong.objects.all().order_by('name')
    selected_hjd_code = request.GET.get('hjd_code')
    
    # Get last update times
    last_hjd_update = HangJeongDongHistory.objects.order_by('-archived_at').first()
    last_busstop_update = BusStopHistory.objects.order_by('-archived_at').first()
    last_busdata_update = BusData.objects.order_by('-timestamp').first()

    context = {
        'hjd_list': hjd_list,
        'selected_hjd_code': selected_hjd_code,
        'last_hjd_update_time': last_hjd_update.archived_at if last_hjd_update else None,
        'last_busstop_update_time': last_busstop_update.archived_at if last_busstop_update else None,
        'last_busdata_update_time': last_busdata_update.timestamp if last_busdata_update else None,
    }
    
    if selected_hjd_code:
        selected_hjd = HangJeongDong.objects.get(district_id=selected_hjd_code)
        bus_stops = BusStop.objects.filter(district_id=selected_hjd_code)
        bus_stop_count = bus_stops.count()
        
        context['selected_hjd'] = selected_hjd
        context['bus_stops'] = bus_stops
        context['bus_stop_count'] = bus_stop_count

    return render(request, 'main/index.html', context)

def busstop_detail(request, busstop_id):
    bus_stop = BusStop.objects.get(busstop_id=busstop_id)

    # --- Date Filtering ---
    default_end_date = timezone.now().date()
    default_start_date = default_end_date - timedelta(days=6)
    
    start_date_str = request.GET.get('start_date', default_start_date.strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', default_end_date.strftime('%Y-%m-%d'))

    # --- Data Query ---
    bus_data_history = BusDataHistory.objects.filter(
        busstop_id=busstop_id,
        timestamp__date__gte=start_date_str,
        timestamp__date__lte=end_date_str
    ).order_by('timestamp')

    # --- Summary Statistics ---
    stats = bus_data_history.aggregate(
        total_passengers_on=Sum('passengers_on'),
        total_passengers_off=Sum('passengers_off')
    )
    
    # Calculate busiest hour
    busiest_hour_data = bus_data_history.annotate(
        hour=TruncHour('timestamp')
    ).values('hour').annotate(
        total_on=Sum('passengers_on')
    ).order_by('-total_on').first()

    # --- Chart Data Preparation ---
    daily_summary = bus_data_history.annotate(
        day=TruncDay('timestamp')
    ).values('day').annotate(
        daily_on=Sum('passengers_on'),
        daily_off=Sum('passengers_off')
    ).order_by('day')

    chart_labels = [item['day'].strftime('%Y-%m-%d') for item in daily_summary]
    chart_data_on = [item['daily_on'] for item in daily_summary]
    chart_data_off = [item['daily_off'] for item in daily_summary]

    # --- Context ---
    context = {
        'bus_stop': bus_stop,
        'bus_data': bus_data_history,
        'stats': stats,
        'busiest_hour': busiest_hour_data,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'chart_labels': json.dumps(chart_labels),
        'chart_data_on': json.dumps(chart_data_on),
        'chart_data_off': json.dumps(chart_data_off),
    }
    return render(request, 'main/busstop_detail.html', context)