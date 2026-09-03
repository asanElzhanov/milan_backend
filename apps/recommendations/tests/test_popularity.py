from django.test import TestCase

from apps.recommendations.constants import EventSource, EventType, PopularityScope, PopularityWindow
from apps.recommendations.models import ProductPopularity, UserProductEvent
from apps.recommendations.services import PopularityService, bayesian_rating

from .factories import make_product, make_user


class PopularityTests(TestCase):
    def test_bayesian_rating_and_normalization(self):
        self.assertAlmostEqual(bayesian_rating(5, 5, 3, minimum_reviews=5), 4.0)
        self.assertEqual(PopularityService._normalize(5, 0, 10), 0.5)
        self.assertEqual(PopularityService._normalize(1, 1, 1), 1.0)

    def test_purchase_scores_above_view_and_rebuild_is_idempotent(self):
        user = make_user()
        viewed = make_product()
        purchased = make_product(category=viewed.category)
        UserProductEvent.objects.create(
            user=user, product=viewed, event_type=EventType.VIEW, source=EventSource.CATALOG,
        )
        UserProductEvent.objects.create(
            user=user, product=purchased, event_type=EventType.PURCHASE, source=EventSource.ORDER,
        )
        first = PopularityService.rebuild(windows=[PopularityWindow.WEEK])
        second = PopularityService.rebuild(windows=[PopularityWindow.WEEK])
        self.assertEqual(first, second)
        global_rows = ProductPopularity.objects.filter(
            scope=PopularityScope.GLOBAL,
            window=PopularityWindow.WEEK,
        )
        self.assertGreater(
            global_rows.get(product=purchased).score,
            global_rows.get(product=viewed).score,
        )
        self.assertTrue(ProductPopularity.objects.filter(
            scope=PopularityScope.CATEGORY,
            category=viewed.category,
            window=PopularityWindow.WEEK,
        ).exists())

    def test_all_time_can_use_lifetime_views_but_week_does_not(self):
        product = make_product(views_count=100)
        PopularityService.rebuild(windows=[PopularityWindow.WEEK, PopularityWindow.ALL])
        week = ProductPopularity.objects.get(
            product=product, scope=PopularityScope.GLOBAL, window=PopularityWindow.WEEK,
        )
        lifetime = ProductPopularity.objects.get(
            product=product, scope=PopularityScope.GLOBAL, window=PopularityWindow.ALL,
        )
        self.assertEqual(week.views_count, 0)
        self.assertGreater(lifetime.score, week.score)

