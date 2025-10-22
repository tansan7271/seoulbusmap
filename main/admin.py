from django.contrib import admin
from .models import HangJeongDong, BusStop, BusData

# Register your models here.
admin.site.register(HangJeongDong)
admin.site.register(BusStop)
admin.site.register(BusData)
