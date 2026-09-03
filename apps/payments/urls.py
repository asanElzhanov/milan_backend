from django.urls import path

from . import views

urlpatterns = [
    path('freedom/create/', views.FreedomCreatePaymentView.as_view(), name='freedom-create'),
    # Без завершающего слэша: FreedomPay подписывает callback именем последнего сегмента пути.
    path('freedom/result', views.FreedomResultView.as_view(), name='freedom-result'),
    path('freedom/status/', views.FreedomStatusView.as_view(), name='freedom-status'),
]
