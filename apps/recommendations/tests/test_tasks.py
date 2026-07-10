from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.recommendations.constants import EventSource, EventType
from apps.recommendations.models import UserProductEvent
from apps.recommendations.tasks import (
    aggregate_product_popularity,
    cleanup_recommendation_data,
    generate_user_recommendations,
    rebuild_co_purchase_relations,
    reconcile_recommendation_aggregates,
)

from .factories import add_order_item, make_order, make_product, make_user


LOC_MEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


@override_settings(CACHES=LOC_MEM, RECOMMENDATION_EVENT_RETENTION_DAYS=30)
class TaskTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_empty_and_repeated_popularity_task(self):
        first = aggregate_product_popularity.run()
        second = aggregate_product_popularity.run()
        self.assertEqual(first, second)
        self.assertEqual(first['rows'], 0)

    def test_generation_batch_continues_after_partial_failure(self):
        first = make_user()
        second = make_user()
        make_product()
        with patch(
            'apps.recommendations.tasks.RecommendationService.generate_for_user',
            side_effect=[RuntimeError('one user failed'), []],
        ) as generate:
            result = generate_user_recommendations.run(user_ids=[first.id, second.id])
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(result, {'users': 1, 'recommendations': 0})

    def test_relation_rebuild_empty_dataset(self):
        self.assertEqual(rebuild_co_purchase_relations.run(), 0)

    def test_cleanup_deletes_expired_events_in_batches(self):
        user = make_user()
        product = make_product()
        event = UserProductEvent.objects.create(
            user=user, product=product, event_type=EventType.VIEW, source=EventSource.CATALOG,
        )
        UserProductEvent.objects.filter(pk=event.pk).update(
            occurred_at=timezone.now() - timedelta(days=31)
        )
        result = cleanup_recommendation_data.run()
        self.assertEqual(result['events'], 1)
        self.assertFalse(UserProductEvent.objects.exists())

    def test_reconciliation_calls_both_aggregate_services(self):
        with patch('apps.recommendations.tasks.PopularityService.rebuild', return_value=7), patch(
            'apps.recommendations.tasks.UserPreferenceService.rebuild',
            return_value={'users': 2, 'preferences': 5},
        ):
            result = reconcile_recommendation_aggregates.run()
        self.assertEqual(result, {'popularity_rows': 7, 'users': 2, 'preferences': 5})

    def test_event_backfill_is_repeatable_and_dry_run_does_not_write(self):
        user = make_user()
        product = make_product()
        order = make_order(user=user, status='completed', payment_status='paid')
        add_order_item(order, product)
        call_command('backfill_recommendations', events=True, stdout=StringIO())
        first_count = UserProductEvent.objects.count()
        call_command('backfill_recommendations', events=True, stdout=StringIO())
        self.assertEqual(UserProductEvent.objects.count(), first_count)

        UserProductEvent.objects.all().delete()
        call_command(
            'backfill_recommendations', events=True, dry_run=True, stdout=StringIO(),
        )
        self.assertEqual(UserProductEvent.objects.count(), 0)
