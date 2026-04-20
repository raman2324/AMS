from django.urls import path
from . import views

app_name = 'approvals'

urlpatterns = [
    path('new/', views.request_new, name='request_new'),
    path('inbox/', views.inbox, name='inbox'),
    path('my/', views.my_requests, name='my_requests'),
    path('<int:pk>/', views.request_detail, name='request_detail'),
    path('<int:pk>/approve/', views.action_approve, name='action_approve'),
    path('<int:pk>/reject/', views.action_reject, name='action_reject'),
    path('<int:pk>/provision/', views.action_provision, name='action_provision'),
    path('<int:pk>/renew/', views.action_renew, name='action_renew'),
    path('<int:pk>/terminate/', views.action_terminate, name='action_terminate'),
]
