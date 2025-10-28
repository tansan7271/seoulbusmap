from django.urls import path
from . import views

urlpatterns = [
  path('', views.index, name='index'),
  path('busstop/<str:busstop_id>/', views.busstop_detail, name='busstop_detail'),
]