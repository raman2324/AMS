from django.urls import path
from . import views

app_name = 'audit'

urlpatterns = [
    path('', views.audit_log, name='audit_log'),
    path('my-audit/', views.my_audit_log, name='my_audit_log'),
    path('offboard/', views.offboard, name='offboard'),
]
