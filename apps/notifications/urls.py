from django.urls import path

from .views import NotificationListView, NotificationMarkAllReadView, NotificationMarkReadView

urlpatterns = [
    path('', NotificationListView.as_view(), name='notifications'),
    path('mark-all-read/', NotificationMarkAllReadView.as_view(), name='notifications-mark-all-read'),
    path('read-all/', NotificationMarkAllReadView.as_view(), name='notifications-read-all'),
    path('<int:pk>/mark-read/', NotificationMarkReadView.as_view(), name='notifications-mark-read'),
]
