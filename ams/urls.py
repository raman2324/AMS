from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('accounts/', include('accounts.urls')),
    path('requests/', include('approvals.urls')),
    path('subscriptions/', include('subscriptions.urls')),
    path('expenses/', include('expenses.urls')),
    path('admin-ams/', include('audit.urls')),
    path('', RedirectView.as_view(url='/requests/inbox/', permanent=False)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
