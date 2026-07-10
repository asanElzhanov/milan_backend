from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.recommendations.constants import EventSource, EventType
from apps.recommendations.models import UserProductEvent
from apps.recommendations.services import (
    RecommendationEventService,
    decay_factor,
    effective_event_weight,
    event_base_weight,
    quantity_factor,
)

from .factories import make_product, make_user


class EventWeightTests(TestCase):
    def test_event_weight_decay_quantity_and_rating(self):
        self.assertGreater(event_base_weight(EventType.PURCHASE), event_base_weight(EventType.VIEW))
        self.assertAlmostEqual(decay_factor(10, 10), 0.5)
        self.assertEqual(quantity_factor(1), 1.0)
        self.assertEqual(quantity_factor(100), 3.0)
        self.assertLess(event_base_weight(EventType.RATING, 1), 0)
        self.assertGreater(event_base_weight(EventType.RATING, 5), 0)

    def test_effective_weight_honours_scoring_flag(self):
        event = UserProductEvent(
            event_type=EventType.CART_ADD,
            value=Decimal('2'),
            occurred_at=timezone.now() - timedelta(days=7),
            metadata={'scoring': False},
        )
        self.assertEqual(effective_event_weight(event), 0)
        event.metadata = {}
        self.assertGreater(effective_event_weight(event), 0)


@override_settings(RECOMMENDATION_VIEW_DEDUP_MINUTES=30, RECOMMENDATION_MAX_VIEWS_PER_DAY=3)
class EventServiceTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.product = make_product()

    def test_duplicate_client_event_id_is_idempotent(self):
        import uuid

        client_id = uuid.uuid4()
        first, duplicate = RecommendationEventService.record_business_event(
            event_type=EventType.CART_ADD,
            source=EventSource.CART,
            user=self.user,
            product=self.product,
            value=1,
            client_event_id=client_id,
        )
        second, duplicate_again = RecommendationEventService.record_business_event(
            event_type=EventType.CART_ADD,
            source=EventSource.CART,
            user=self.user,
            product=self.product,
            value=1,
            client_event_id=client_id,
        )
        self.assertFalse(duplicate)
        self.assertTrue(duplicate_again)
        self.assertIsNone(second)
        self.assertEqual(UserProductEvent.objects.filter(client_event_id=client_id).count(), 1)

    def test_repeated_view_and_daily_cap(self):
        first, duplicate = RecommendationEventService.record_business_event(
            event_type=EventType.VIEW,
            source=EventSource.CATALOG,
            user=self.user,
            product=self.product,
        )
        second, duplicate_again = RecommendationEventService.record_business_event(
            event_type=EventType.VIEW,
            source=EventSource.CATALOG,
            user=self.user,
            product=self.product,
        )
        self.assertIsNotNone(first)
        self.assertFalse(duplicate)
        self.assertIsNone(second)
        self.assertTrue(duplicate_again)
        UserProductEvent.objects.filter(pk=first.pk).update(
            occurred_at=timezone.now() - timedelta(hours=3)
        )
        for minutes in (120, 60):
            event, _ = RecommendationEventService.record_business_event(
                event_type=EventType.VIEW,
                source=EventSource.CATALOG,
                user=self.user,
                product=self.product,
                occurred_at=timezone.now() - timedelta(minutes=minutes),
            )
            self.assertIsNotNone(event)
        capped, is_duplicate = RecommendationEventService.record_business_event(
            event_type=EventType.VIEW,
            source=EventSource.CATALOG,
            user=self.user,
            product=self.product,
        )
        self.assertIsNone(capped)
        self.assertTrue(is_duplicate)

    def test_metadata_allowlist(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            RecommendationEventService.record_business_event(
                event_type=EventType.VIEW,
                source=EventSource.CATALOG,
                user=self.user,
                product=self.product,
                metadata={'page': 2, 'secret': 'must-not-be-stored'},
            )
