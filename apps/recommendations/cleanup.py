from datetime import timedelta

from django.conf import settings
from django.db.models import Max
from django.utils import timezone

from .models import HiddenRecommendation, ProductRelation, UserProductEvent, UserRecommendation


def _delete_in_batches(queryset, batch_size):
    deleted = 0
    while True:
        ids = list(queryset.values_list('id', flat=True)[:batch_size])
        if not ids:
            break
        count, _ = queryset.model.objects.filter(pk__in=ids).delete()
        deleted += count
    return deleted


def cleanup_data():
    now = timezone.now()
    batch_size = settings.RECOMMENDATION_TASK_BATCH_SIZE
    stats = {}
    event_cutoff = now - timedelta(days=settings.RECOMMENDATION_EVENT_RETENTION_DAYS)
    stats['events'] = _delete_in_batches(
        UserProductEvent.objects.filter(occurred_at__lt=event_cutoff),
        batch_size,
    )
    search_cutoff = now - timedelta(days=settings.RECOMMENDATION_SEARCH_RETENTION_DAYS)
    stats['search_queries_cleared'] = UserProductEvent.objects.filter(
        search_query__isnull=False,
        occurred_at__lt=search_cutoff,
    ).update(search_query=None)
    stats['expired_recommendations'] = _delete_in_batches(
        UserRecommendation.objects.filter(expires_at__lt=now),
        batch_size,
    )
    stats['expired_hidden'] = _delete_in_batches(
        HiddenRecommendation.objects.filter(expires_at__lt=now),
        batch_size,
    )
    stale_relation_cutoff = now - timedelta(days=settings.RECOMMENDATION_GENERATION_RETENTION_DAYS * 3)
    stats['stale_relations'] = _delete_in_batches(
        ProductRelation.objects.filter(calculated_at__lt=stale_relation_cutoff),
        batch_size,
    )

    old_generation_ids = []
    pairs = UserRecommendation.objects.values_list('user_id', 'context').distinct().iterator(chunk_size=batch_size)
    for user_id, context in pairs:
        generations = list(UserRecommendation.objects.filter(
            user_id=user_id,
            context=context,
        ).values('generation_id').annotate(
            latest_generated_at=Max('generated_at'),
        ).order_by('-latest_generated_at').values_list('generation_id', flat=True))
        old_generation_ids.extend(generations[settings.RECOMMENDATION_MAX_GENERATIONS:])
    stats['old_generations'] = _delete_in_batches(
        UserRecommendation.objects.filter(generation_id__in=old_generation_ids),
        batch_size,
    ) if old_generation_ids else 0
    return stats
