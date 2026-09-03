from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .statuses import get_status_registry


class StatusLabelsSerializer(serializers.Serializer):
    ru = serializers.CharField()
    kz = serializers.CharField()
    en = serializers.CharField()


class StatusOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    labels = StatusLabelsSerializer()


class SystemStatusRegistrySerializer(serializers.Serializer):
    order = StatusOptionSerializer(many=True)
    order_payment = StatusOptionSerializer(many=True)
    payment = StatusOptionSerializer(many=True)
    import_job = StatusOptionSerializer(many=True)
    review = StatusOptionSerializer(many=True)
    notification = StatusOptionSerializer(many=True)


class SystemStatusRegistryView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['System'],
        summary='Все системные статусы на трёх языках',
        responses={200: SystemStatusRegistrySerializer},
    )
    def get(self, request):
        return Response(get_status_registry())
