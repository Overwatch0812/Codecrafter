from django.urls import path,include
from .views import *

urlpatterns = [
    path('',Home),
    path('weather/',hit_weather)
]
