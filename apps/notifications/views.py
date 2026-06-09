from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'type', 'title', 'message', 'is_read', 'created_at')


class NotificationListView(generics.ListAPIView):
    """GET /notifications/"""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Notification.objects.none()
        return Notification.objects.filter(user=self.request.user)

    @extend_schema(
        tags=['Notifications'],
        summary='Список уведомлений',
        responses={200: NotificationSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class NotificationReadView(APIView):
    """POST /notifications/read-all/ — пометить все прочитанными"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['Notifications'],
        summary='Пометить все уведомления прочитанными',
        request=None,
        responses={
            200: inline_serializer(
                name='NotificationsReadAllResponse',
                fields={'detail': serializers.CharField()},
            ),
        },
    )
    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'detail': 'Все уведомления прочитаны'})
