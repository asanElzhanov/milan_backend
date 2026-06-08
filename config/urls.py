from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerUIView, SpectacularRedocView

API_V1 = 'api/v1/'

urlpatterns = [
    path('django-admin/', admin.site.urls),

    # Schema
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerUIView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Apps
    path(API_V1 + 'auth/', include('apps.accounts.urls')),
    path(API_V1 + 'catalog/', include('apps.catalog.urls')),
    path(API_V1 + 'orders/', include('apps.orders.urls')),
    path(API_V1 + 'payments/', include('apps.payments.urls')),
    path(API_V1 + 'notifications/', include('apps.notifications.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
