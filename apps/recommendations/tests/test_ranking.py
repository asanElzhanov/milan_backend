from decimal import Decimal

from django.test import TestCase, override_settings

from apps.recommendations.constants import PopularityScope, PopularityWindow, RecommendationContext
from apps.recommendations.models import ProductPopularity, UserCategoryPreference
from apps.recommendations.services import RecommendationService

from .factories import make_category, make_product, make_user


class RankingTests(TestCase):
    @override_settings(
        RECOMMENDATION_MAX_PER_CATEGORY=2,
        RECOMMENDATION_MAX_RESULTS=12,
        REST_FRAMEWORK={'PAGE_SIZE': 6},
    )
    def test_diversity_is_per_page_and_deterministic(self):
        items = []
        for number in range(12):
            items.append({
                'product_id': number + 1,
                'category_id': 1 if number < 6 else (2 if number < 9 else 3),
                'score': 1 - number / 100,
            })
        first = RecommendationService.apply_diversity(items, 12)
        second = RecommendationService.apply_diversity(items, 12)
        self.assertEqual(first, second)
        self.assertLessEqual(sum(item['category_id'] == 1 for item in first[:6]), 2)
        self.assertGreater(sum(item['category_id'] == 1 for item in first[6:]), 0)

    def test_fallback_order_uses_popularity_then_product_id(self):
        category = make_category()
        low = make_product(category=category)
        high = make_product(category=category)
        for product, score in ((low, '0.1'), (high, '0.9')):
            ProductPopularity.objects.create(
                product=product,
                scope=PopularityScope.GLOBAL,
                window=PopularityWindow.WEEK,
                score=Decimal(score),
            )
        self.assertEqual(
            RecommendationService.popular_product_ids(limit=2),
            [high.id, low.id],
        )

    @override_settings(RECOMMENDATION_MAX_RESULTS=4, REST_FRAMEWORK={'PAGE_SIZE': 4})
    def test_final_score_prefers_affinity_and_generation_is_stable(self):
        user = make_user()
        preferred_category = make_category()
        other_category = make_category()
        preferred = make_product(category=preferred_category)
        other = make_product(category=other_category)
        UserCategoryPreference.objects.create(
            user=user,
            category=preferred_category,
            score=Decimal('10'),
            positive_score=Decimal('10'),
        )
        for product in (preferred, other):
            ProductPopularity.objects.create(
                product=product,
                scope=PopularityScope.GLOBAL,
                window=PopularityWindow.WEEK,
                score=Decimal('0.5'),
            )
        rows = RecommendationService.generate_for_user(user, RecommendationContext.HOME)
        self.assertEqual(rows[0].product_id, preferred.id)
        self.assertNotEqual(rows[0].score, rows[1].score)
