import time
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.recommendations.services import RecommendationCacheService


LOC_MEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


@override_settings(CACHES=LOC_MEM, RECOMMENDATION_ALGORITHM_VERSION='test-v9')
class CacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_hit_miss_ttl_and_versioned_key(self):
        key = RecommendationCacheService.personal_key(7, 'home', 1)
        self.assertIn('test-v9', key)
        self.assertIsNone(RecommendationCacheService.get(key))
        self.assertTrue(RecommendationCacheService.set(key, {'ok': True}, 0.01))
        self.assertEqual(RecommendationCacheService.get(key), {'ok': True})
        time.sleep(0.02)
        self.assertIsNone(RecommendationCacheService.get(key))

    def test_invalidation(self):
        key = RecommendationCacheService.personal_key(7, 'home', 1)
        cache.set(key, 1)
        RecommendationCacheService.invalidate_user(7)
        self.assertIsNone(cache.get(key))

    def test_cache_exception_fails_open(self):
        with patch('apps.recommendations.services.cache.get', side_effect=RuntimeError('redis down')):
            self.assertIsNone(RecommendationCacheService.get('key'))
        with patch('apps.recommendations.services.cache.set', side_effect=RuntimeError('redis down')):
            self.assertFalse(RecommendationCacheService.set('key', 1, 10))
