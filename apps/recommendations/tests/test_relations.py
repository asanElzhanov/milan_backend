from django.test import TestCase, override_settings

from apps.recommendations.constants import RelationType
from apps.recommendations.models import ProductRelation
from apps.recommendations.services import ProductRelationService, price_proximity

from .factories import add_order_item, make_brand, make_category, make_order, make_product


class RelationTests(TestCase):
    def test_content_components_and_price_proximity(self):
        category = make_category()
        brand = make_brand()
        left = make_product(
            category=category,
            brand=brand,
            material='cotton',
            composition='cotton wool',
            description='warm blue shirt',
            season='aw',
        )
        right = make_product(
            category=category,
            brand=brand,
            material='cotton',
            composition='cotton',
            description='warm shirt',
            season='aw',
        )
        score, components = ProductRelationService.content_components(left, right)
        self.assertGreater(score, 0.7)
        self.assertEqual(components['category'], 1.0)
        self.assertEqual(price_proximity(100, 100), 1.0)
        self.assertEqual(price_proximity(100, 200), 0.5)

    def test_content_rebuild_is_idempotent(self):
        category = make_category()
        left = make_product(category=category, description='same words')
        right = make_product(category=category, description='same words')
        first = ProductRelationService.rebuild_content_relations([left.id, right.id])
        second = ProductRelationService.rebuild_content_relations([left.id, right.id])
        self.assertEqual(first, second)
        self.assertEqual(
            ProductRelation.objects.filter(relation_type=RelationType.CONTENT).count(),
            first['relations'],
        )

    @override_settings(RECOMMENDATION_CO_PURCHASE_MIN_SUPPORT=1)
    def test_co_purchase_relation_rebuild(self):
        left = make_product()
        right = make_product()
        order = make_order(status='completed', payment_status='paid')
        add_order_item(order, left)
        add_order_item(order, right)
        ProductRelationService.rebuild_co_purchase_relations()
        relation = ProductRelation.objects.get(
            source_product=left,
            target_product=right,
            relation_type=RelationType.CO_PURCHASE,
        )
        self.assertEqual(relation.support_count, 1)
        self.assertEqual(float(relation.confidence), 1.0)
