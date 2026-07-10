from django.conf import settings
from rest_framework import serializers

from apps.catalog.serializers import ProductListSerializer

from .constants import EventType, PopularityWindow, PUBLIC_EVENT_TYPES, RecommendationContext


class RecommendationItemSerializer(serializers.Serializer):
    tracking_id = serializers.UUIDField(allow_null=True)
    reason_code = serializers.CharField()
    is_fallback = serializers.BooleanField()
    product = ProductListSerializer()


class RecommendationEventItemSerializer(serializers.Serializer):
    client_event_id = serializers.UUIDField(required=False, allow_null=True)
    event_type = serializers.ChoiceField(choices=sorted(PUBLIC_EVENT_TYPES))
    product_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    context = serializers.ChoiceField(choices=RecommendationContext.choices)
    tracking_id = serializers.UUIDField(required=False, allow_null=True)
    search_query = serializers.CharField(max_length=255, required=False, allow_blank=True)
    metadata = serializers.DictField(required=False, default=dict)

    def validate(self, attrs):
        if attrs['event_type'] != EventType.SEARCH and not attrs.get('product_id'):
            raise serializers.ValidationError({'product_id': 'Для этого события товар обязателен.'})
        if attrs['event_type'] == EventType.SEARCH and not attrs.get('search_query'):
            raise serializers.ValidationError({'search_query': 'Для события search передайте запрос.'})
        return attrs


class RecommendationEventBatchSerializer(serializers.Serializer):
    events = RecommendationEventItemSerializer(
        many=True,
        allow_empty=False,
        max_length=settings.RECOMMENDATION_EVENT_BATCH_LIMIT,
    )


class RejectedEventSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    errors = serializers.JSONField()


class RecommendationEventBatchResponseSerializer(serializers.Serializer):
    accepted = serializers.IntegerField()
    duplicates = serializers.IntegerField()
    rejected = RejectedEventSerializer(many=True)


class HideRecommendationSerializer(serializers.Serializer):
    context = serializers.ChoiceField(choices=RecommendationContext.choices, default=RecommendationContext.HOME)
    reason = serializers.CharField(max_length=64, required=False, allow_blank=True)
    tracking_id = serializers.UUIDField(required=False, allow_null=True)


class StatusSerializer(serializers.Serializer):
    status = serializers.CharField()


class PopularQuerySerializer(serializers.Serializer):
    category = serializers.CharField(required=False, allow_blank=True)
    window = serializers.ChoiceField(
        choices=(PopularityWindow.WEEK, PopularityWindow.MONTH, PopularityWindow.ALL),
        default=PopularityWindow.WEEK,
    )
    page = serializers.IntegerField(min_value=1, required=False, default=1)


class LimitSerializer(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=24, required=False, default=12)


class RecommendationQuerySerializer(serializers.Serializer):
    context = serializers.ChoiceField(choices=RecommendationContext.choices, default=RecommendationContext.HOME)
    page = serializers.IntegerField(min_value=1, required=False, default=1)
