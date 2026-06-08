from django.urls import path
from .views import NotificationListView, NotificationReadView

urlpatterns = [
    path('', NotificationListView.as_view(), name='notifications'),
    path('read-all/', NotificationReadView.as_view(), name='notifications-read-all'),
]
