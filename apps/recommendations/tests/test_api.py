import uuid
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.orders.models import CartItem
from apps.recommendations.constants import PopularityScope, PopularityWindow, RelationType
from apps.recommendations.models import ProductPopularity, ProductRelation, UserProductEvent

from .factories import make_cart, make_product, make_user


LOC_MEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


@override_settings(CACHES=LOC_MEM)
class EventApiTests(TestCase):
    url = '/api/v1/recommendations/events/'

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.product = make_product()

    def payload(self, **changes):
        item = {
            'client_event_id': str(uuid.uuid4()),
            'event_type': 'view',
            'product_id': self.product.id,
            'context': 'product',
            'metadata': {'page': 1},
        }
        item.update(changes)
        return {'events': [item]}

    def test_authenticated_actor_and_user_id_cannot_be_injected(self):
        user = make_user()
        attacker = make_user()
        self.client.force_authenticate(user)
        payload = self.payload()
        payload['events'][0]['user_id'] = attacker.id
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, 200)
        event = UserProductEvent.objects.get()
        self.assertEqual(event.user_id, user.id)
        self.assertEqual(event.metadata, {'page': 1})

    def test_anonymous_actor_receives_cookie_and_only_hash_is_stored(self):
        response = self.client.post(self.url, self.payload(), format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('reco_actor', response.cookies)
        event = UserProductEvent.objects.get()
        self.assertIsNone(event.user_id)
        self.assertEqual(len(event.anonymous_id_hash), 64)
        self.assertNotEqual(event.anonymous_id_hash, response.cookies['reco_actor'].value)

    def test_batch_duplicate_invalid_product_and_invalid_tracking(self):
        user = make_user()
        self.client.force_authenticate(user)
        client_id = str(uuid.uuid4())
        payload = {'events': [
            self.payload(client_event_id=client_id)['events'][0],
            self.payload(client_event_id=client_id)['events'][0],
            self.payload(product_id=999999)['events'][0],
            self.payload(event_type='recommendation_click', tracking_id=str(uuid.uuid4()))['events'][0],
        ]}
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['accepted'], 1)
        self.assertEqual(response.data['duplicates'], 1)
        self.assertEqual(len(response.data['rejected']), 2)

    def test_forbidden_event_type_is_rejected_by_serializer(self):
        response = self.client.post(self.url, self.payload(event_type='purchase'), format='json')
        self.assertEqual(response.status_code, 400)

    def test_rate_limit(self):
        with patch.object(ScopedRateThrottle, 'get_rate', return_value='1/min'):
            first = self.client.post(self.url, self.payload(), format='json')
            second = self.client.post(self.url, self.payload(), format='json')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)


@override_settings(CACHES=LOC_MEM, REST_FRAMEWORK={
    'PAGE_SIZE': 24,
    'DEFAULT_THROTTLE_RATES': {'recommendation_events': '100/min'},
})
class RecommendationApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def _popular(self, product, score):
        return ProductPopularity.objects.create(
            product=product,
            scope=PopularityScope.GLOBAL,
            window=PopularityWindow.WEEK,
            score=Decimal(str(score)),
        )

    def test_anonymous_fallback_shape_has_product_serializer_and_no_score(self):
        product = make_product()
        self._popular(product, 1)
        response = self.client.get('/api/v1/recommendations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        item = response.data['results'][0]
        self.assertIn('product', item)
        self.assertIn('slug', item['product'])
        self.assertNotIn('score', item)
        self.assertTrue(item['is_fallback'])

    def test_authenticated_user_with_generation_has_tracking_id(self):
        user = make_user()
        product = make_product()
        self.client.force_authenticate(user)
        from apps.recommendations.services import RecommendationService

        RecommendationService.save_generation(user, 'home', [{
            'product_id': product.id,
            'score': 0.5,
            'reason_code': 'because_category',
            'reason_payload': {},
        }])
        response = self.client.get('/api/v1/recommendations/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.data['results'][0]['tracking_id'])

    def test_empty_catalog_and_stale_cache_are_safe(self):
        response = self.client.get('/api/v1/recommendations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'], [])

        user = make_user()
        stale = make_product(stock=0)
        from apps.recommendations.services import RecommendationCacheService

        key = RecommendationCacheService.personal_key(user.id, 'home', 1)
        cache.set(key, {'count': 1, 'items': [{
            'product_id': stale.id, 'tracking_id': None, 'reason_code': 'fallback', 'is_fallback': True,
        }]})
        self.client.force_authenticate(user)
        stale_response = self.client.get('/api/v1/recommendations/')
        self.assertEqual(stale_response.status_code, 200)
        self.assertEqual(stale_response.data['results'], [])

    @override_settings(PAGE_SIZE=24)
    def test_pagination_stable_order_and_query_budget(self):
        products = [make_product() for _ in range(26)]
        for number, product in enumerate(products):
            self._popular(product, 100 - number)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/api/v1/recommendations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 24)
        self.assertIsNotNone(response.data['next'])
        self.assertLessEqual(len(queries), 15)
        second = self.client.get('/api/v1/recommendations/?page=2')
        first_ids = {item['product']['id'] for item in response.data['results']}
        second_ids = {item['product']['id'] for item in second.data['results']}
        self.assertFalse(first_ids & second_ids)

    def test_hide_and_unhide(self):
        user = make_user()
        product = make_product()
        self.client.force_authenticate(user)
        url = f'/api/v1/recommendations/products/{product.id}/hide/'
        self.assertEqual(self.client.post(url, {'context': 'home'}, format='json').status_code, 200)
        self.assertEqual(self.client.delete(f'{url}?context=home').status_code, 200)

    def test_similar_cart_and_popular_query_budgets(self):
        user = make_user()
        source = make_product()
        targets = [make_product(category=source.category) for _ in range(12)]
        for index, target in enumerate(targets):
            ProductRelation.objects.create(
                source_product=source,
                target_product=target,
                relation_type=RelationType.CONTENT,
                score=Decimal(str(1 - index / 100)),
            )
            self._popular(target, 1 - index / 100)

        cache.clear()
        with CaptureQueriesContext(connection) as similar_queries:
            similar = self.client.get(f'/api/v1/catalog/products/{source.slug}/similar/')
        self.assertEqual(similar.status_code, 200)
        self.assertLessEqual(len(similar_queries), 16)

        cache.clear()
        with CaptureQueriesContext(connection) as popular_queries:
            popular = self.client.get('/api/v1/recommendations/popular/')
        self.assertEqual(popular.status_code, 200)
        self.assertLessEqual(len(popular_queries), 16)

        cart = make_cart(user)
        CartItem.objects.create(cart=cart, variant=source.variants.get(), quantity=1)
        self.client.force_authenticate(user)
        cache.clear()
        with CaptureQueriesContext(connection) as cart_queries:
            cart_response = self.client.get('/api/v1/recommendations/cart/')
        self.assertEqual(cart_response.status_code, 200)
        self.assertLessEqual(len(cart_queries), 20)
