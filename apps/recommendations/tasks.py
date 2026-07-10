import logging
import time

from celery import shared_task
from django.conf import settings

from apps.accounts.models import User

from .services import (
    PopularityService,
    ProductRelationService,
    RecommendationCacheService,
    RecommendationService,
    UserPreferenceService,
)


logger = logging.getLogger(__name__)


def _run_locked(name, callback):
    lock = RecommendationCacheService.acquire_lock(name)
    if lock is None:
        logger.info('Recommendation task %s skipped: lock is held', name)
        return {'status': 'locked'}
    started = time.monotonic()
    try:
        result = callback()
        logger.info('Recommendation task %s completed duration=%.3fs result=%s', name, time.monotonic() - started, result)
        return result
    finally:
        RecommendationCacheService.release_lock(lock)


@shared_task(name='recommendations.aggregate_product_popularity')
def aggregate_product_popularity():
    return _run_locked('popularity', lambda: {'rows': PopularityService.rebuild()})


@shared_task(name='recommendations.rebuild_user_category_preferences')
def rebuild_user_category_preferences(user_ids=None):
    return _run_locked('preferences-full' if user_ids is None else f'preferences-{hash(tuple(user_ids))}', lambda: UserPreferenceService.rebuild(user_ids=user_ids))


@shared_task(name='recommendations.rebuild_content_relations')
def rebuild_content_relations(product_ids=None):
    return _run_locked('content-full' if product_ids is None else f'content-{hash(tuple(product_ids))}', lambda: ProductRelationService.rebuild_content_relations(product_ids=product_ids))


@shared_task(name='recommendations.rebuild_co_purchase_relations')
def rebuild_co_purchase_relations():
    return _run_locked('co-purchase', ProductRelationService.rebuild_co_purchase_relations)


@shared_task(name='recommendations.generate_user_recommendations')
def generate_user_recommendations(user_ids=None, context='home'):
    def generate():
        queryset = User.objects.filter(is_active=True, role=User.Role.CUSTOMER).order_by('id')
        if user_ids:
            queryset = queryset.filter(pk__in=user_ids)
        processed = generated = 0
        for user in queryset.iterator(chunk_size=settings.RECOMMENDATION_TASK_BATCH_SIZE):
            try:
                rows = RecommendationService.generate_for_user(user, context=context)
                generated += len(rows)
                processed += 1
            except Exception:
                logger.exception('Recommendation generation failed for user_id=%s', user.id)
        return {'users': processed, 'recommendations': generated}

    key = 'generation-full' if user_ids is None else f'generation-{hash(tuple(user_ids))}'
    return _run_locked(key, generate)


@shared_task(name='recommendations.refresh_user_recommendations')
def refresh_user_recommendations(user_id):
    UserPreferenceService.rebuild(user_ids=[user_id])
    rows = RecommendationService.generate_for_user(User.objects.get(pk=user_id))
    return {'user_id': user_id, 'recommendations': len(rows)}


@shared_task(name='recommendations.cleanup_recommendation_data')
def cleanup_recommendation_data():
    from .cleanup import cleanup_data

    return _run_locked('cleanup', cleanup_data)


@shared_task(name='recommendations.reconcile_recommendation_aggregates')
def reconcile_recommendation_aggregates():
    def reconcile():
        popularity_rows = PopularityService.rebuild()
        preference_rows = UserPreferenceService.rebuild()
        return {'popularity_rows': popularity_rows, **preference_rows}

    return _run_locked('reconcile', reconcile)
