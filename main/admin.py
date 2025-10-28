from django.contrib import admin
from .models import HangJeongDong, BusStop, BusData, HangJeongDongHistory, BusStopHistory, BusDataHistory

@admin.register(HangJeongDong)
class HangJeongDongAdmin(admin.ModelAdmin):
    list_display = ('district_id', 'name', 'population', 'timestamp')
    readonly_fields = ('timestamp',)

@admin.register(BusStop)
class BusStopAdmin(admin.ModelAdmin):
    list_display = ('busstop_id', 'name', 'district_id', 'is_active', 'timestamp')
    readonly_fields = ('timestamp',)

@admin.register(BusData)
class BusDataAdmin(admin.ModelAdmin):
    list_display = ('bus_id', 'busstop_id', 'passengers_on', 'passengers_off', 'timestamp')

@admin.register(HangJeongDongHistory)
class HangJeongDongHistoryAdmin(admin.ModelAdmin):
    list_display = ('district_id', 'name', 'population', 'timestamp', 'archived_at')
    readonly_fields = ('archived_at',)
    search_fields = ('name', 'district_id')
    list_filter = ('archived_at',)

@admin.register(BusStopHistory)
class BusStopHistoryAdmin(admin.ModelAdmin):
    list_display = ('busstop_id', 'name', 'district_id', 'is_active', 'timestamp', 'archived_at')
    readonly_fields = ('archived_at',)
    search_fields = ('name', 'busstop_id', 'district_id')
    list_filter = ('is_active', 'archived_at')

@admin.register(BusDataHistory)
class BusDataHistoryAdmin(admin.ModelAdmin):
    list_display = ('bus_id', 'busstop_id', 'timestamp', 'passengers_on', 'passengers_off', 'archived_at')
    readonly_fields = ('archived_at',)
    search_fields = ('bus_id', 'busstop_id')
    list_filter = ('timestamp', 'archived_at')
    date_hierarchy = 'timestamp'
