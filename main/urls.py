from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('hangjeongdong/<str:hjd_code>/', views.hangjeongdong_detail, name='hangjeongdong_detail'),
    path('hangjeongdong/<str:hjd_code>/busstop/<str:busstop_id>/', views.busstop_detail, name='busstop_detail'),
    path('analysis/', views.analysis_report, name='analysis_report'),
    path('000/', views.000_visualization, name='000_visualization'),
]