from django.test import TestCase

from apps.recommendations.constants import RecommendationContext
from apps.recommendations.models import HiddenRecommendation
from apps.recommendations.services import ProductEligibilityService
from apps.orders.models import CartItem

from .factories import make_cart, make_product, make_user


class EligibilityTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_only_active_products_with_active_stocked_variant_are_eligible(self):
        eligible = make_product()
        inactive = make_product(is_active=False)
        no_variants = make_product(with_variant=False)
        inactive_variant = make_product(variant_active=False)
        no_stock = make_product(stock=0)
        ids = set(ProductEligibilityService.queryset().values_list('id', flat=True))
        self.assertIn(eligible.id, ids)
        self.assertNotIn(inactive.id, ids)
        self.assertNotIn(no_variants.id, ids)
        self.assertNotIn(inactive_variant.id, ids)
        self.assertNotIn(no_stock.id, ids)

    def test_hidden_source_and_cart_products_are_excluded(self):
        hidden = make_product()
        source = make_product()
        cart_product = make_product()
        available = make_product()
        HiddenRecommendation.objects.create(
            user=self.user,
            product=hidden,
            context=RecommendationContext.HOME,
        )
        cart = make_cart(self.user)
        CartItem.objects.create(cart=cart, variant=cart_product.variants.first(), quantity=1)
        ids = set(ProductEligibilityService.queryset(
            user=self.user,
            context=RecommendationContext.HOME,
            exclude_ids=[source.id, cart_product.id],
        ).values_list('id', flat=True))
        self.assertNotIn(hidden.id, ids)
        self.assertNotIn(source.id, ids)
        self.assertNotIn(cart_product.id, ids)
        self.assertIn(available.id, ids)

    def test_hydrate_drops_stale_ids(self):
        good = make_product()
        stale = make_product(stock=0)
        hydrated = ProductEligibilityService.hydrate([stale.id, good.id])
        self.assertEqual([product.id for product in hydrated], [good.id])

