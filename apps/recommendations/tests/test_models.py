import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.recommendations.constants import EventSource, EventType, RecommendationContext, RelationType
from apps.recommendations.models import ProductRelation, UserProductEvent, UserRecommendation
from apps.recommendations.services import RecommendationService

from .factories import make_product, make_user


class RecommendationModelTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.left = make_product()
        self.right = make_product(category=self.left.category)

    def test_relation_unique_and_not_self_constraints(self):
        ProductRelation.objects.create(
            source_product=self.left,
            target_product=self.right,
            relation_type=RelationType.CONTENT,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductRelation.objects.create(
                source_product=self.left,
                target_product=self.right,
                relation_type=RelationType.CONTENT,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductRelation.objects.create(
                source_product=self.left,
                target_product=self.left,
                relation_type=RelationType.CONTENT,
            )

    def test_actor_constraint_and_multiple_nullable_unique_values(self):
        for _ in range(2):
            UserProductEvent.objects.create(
                user=self.user,
                product=self.left,
                event_type=EventType.VIEW,
                source=EventSource.CATALOG,
                client_event_id=None,
                deduplication_key=None,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserProductEvent.objects.create(
                product=self.left,
                event_type=EventType.VIEW,
                source=EventSource.CATALOG,
            )

    def test_generation_rows_are_appended_not_mutated(self):
        item = {
            'product_id': self.left.id,
            'score': 0.7,
            'reason_code': 'popular',
            'reason_payload': {},
        }
        first = RecommendationService.save_generation(self.user, RecommendationContext.HOME, [item])
        second = RecommendationService.save_generation(self.user, RecommendationContext.HOME, [item])
        self.assertNotEqual(first[0].generation_id, second[0].generation_id)
        self.assertEqual(UserRecommendation.objects.count(), 2)

    def test_recommendation_unique_rank_and_product(self):
        generation = uuid.uuid4()
        common = {
            'user': self.user,
            'context': RecommendationContext.HOME,
            'generation_id': generation,
            'score': Decimal('0.5'),
            'reason_code': 'popular',
            'algorithm_version': 'v1',
            'expires_at': timezone.now() + timedelta(days=1),
        }
        UserRecommendation.objects.create(product=self.left, rank=1, **common)
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserRecommendation.objects.create(product=self.right, rank=1, **common)

