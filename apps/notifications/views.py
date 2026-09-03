from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_field, inline_serializer,
)
from rest_framework import generics, permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from apps.common.statuses import get_status_labels


class NotificationSerializer(serializers.ModelSerializer):
    read_status = serializers.SerializerMethodField()
    read_status_labels = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = (
            'id', 'title', 'message', 'event_type', 'is_read',
            'read_status', 'read_status_labels', 'created_at',
        )
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.STR)
    def get_read_status(self, obj):
        return 'read' if obj.is_read else 'unread'

    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_read_status_labels(self, obj):
        return get_status_labels('notification', self.get_read_status(obj))


class NotificationListView(generics.ListAPIView):
    """GET /notifications/"""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ('is_read', 'event_type')
    ordering = ['-created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Notification.objects.none()
        return Notification.objects.filter(recipient=self.request.user)

    @extend_schema(
        tags=['Notifications'],
        summary='Список уведомлений',
        parameters=[
            OpenApiParameter('is_read', OpenApiTypes.BOOL, OpenApiParameter.QUERY),
            OpenApiParameter('event_type', OpenApiTypes.STR, OpenApiParameter.QUERY),
        ],
        responses={200: NotificationSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class NotificationMarkReadView(APIView):
    """POST /notifications/<id>/mark-read/ — пометить уведомление прочитанным"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['Notifications'],
        summary='Пометить уведомление прочитанным',
        request=None,
        responses={200: NotificationSerializer},
    )
    def post(self, request, pk):
        notification = get_object_or_404(
            Notification.objects.filter(recipient=request.user),
            pk=pk,
        )
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read', 'updated_at'])
        return Response(NotificationSerializer(notification).data)


class NotificationMarkAllReadView(APIView):
    """POST /notifications/mark-all-read/ — пометить все прочитанными"""
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
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({'detail': 'Все уведомления прочитаны'})


NotificationReadView = NotificationMarkAllReadView
