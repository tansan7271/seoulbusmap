from django.contrib import admin
from .models import HangJeongDong, BusStop, BusData, HangJeongDongHistory, BusStopHistory, BusDataHistory

# Register your models here.
admin.site.register(HangJeongDong)
admin.site.register(BusStop)
admin.site.register(BusData)
admin.site.register(HangJeongDongHistory)
admin.site.register(BusStopHistory)
admin.site.register(BusDataHistory)
