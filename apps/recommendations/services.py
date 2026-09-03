import hashlib
import logging
import math
import re
import statistics
import time
import uuid
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Avg, Case, Count, Exists, Max, Min, OuterRef, Prefetch, Q, Sum, When
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.filters import with_product_list_annotations
from apps.catalog.models import Category, Product, ProductImage, ProductVariant, Review
from apps.orders.models import Cart, Order, OrderItem

from .constants import (
    EventSource,
    EventType,
    METADATA_ALLOWED_KEYS,
    PRODUCT_OPTIONAL_EVENT_TYPES,
    PUBLIC_EVENT_TYPES,
    PopularityScope,
    PopularityWindow,
    RecommendationContext,
    RelationType,
    STRONG_EVENT_TYPES,
)
from .middleware import hash_anonymous_id
from .models import (
    HiddenRecommendation,
    ProductPopularity,
    ProductRelation,
    UserCategoryPreference,
    UserProductEvent,
    UserRecommendation,
)


logger = logging.getLogger(__name__)
TOKEN_RE = re.compile(r"[\wа-яёәіңғүұқөһ]+", re.IGNORECASE)


def clamp(value, minimum=0.0, maximum=1.0):
    return max(minimum, min(maximum, float(value)))


def quantity_factor(value):
    try:
        quantity = abs(float(value or 1))
    except (TypeError, ValueError):
        quantity = 1.0
    if quantity <= 1:
        return 1.0
    return min(1.0 + math.log2(quantity), 3.0)


def decay_factor(age_days, half_life_days):
    half_life = max(float(half_life_days or 1), 0.0001)
    return 2 ** (-max(float(age_days), 0.0) / half_life)


def event_base_weight(event_type, value=None):
    if event_type == EventType.RATING:
        try:
            return float(settings.RECOMMENDATION_RATING_WEIGHTS.get(int(value), 0.0))
        except (TypeError, ValueError):
            return 0.0
    return float(settings.RECOMMENDATION_EVENT_WEIGHTS.get(event_type, 0.0))


def effective_event_weight(event, now=None):
    if event.metadata.get('scoring') is False:
        return 0.0
    now = now or timezone.now()
    age_days = max((now - event.occurred_at).total_seconds() / 86400, 0.0)
    half_life = settings.RECOMMENDATION_EVENT_HALF_LIFE_DAYS.get(event.event_type, 30)
    base = event_base_weight(event.event_type, event.value)
    factor = quantity_factor(event.value) if event.event_type in {EventType.CART_ADD, EventType.CART_REMOVE} else 1.0
    return base * decay_factor(age_days, half_life) * factor


def price_proximity(left, right):
    if left is None or right is None:
        return None
    left = float(left)
    right = float(right)
    maximum = max(abs(left), abs(right))
    if maximum == 0:
        return 1.0
    return clamp(1.0 - abs(left - right) / maximum)


def token_overlap(left, right):
    left_tokens = set(TOKEN_RE.findall((left or '').lower()))
    right_tokens = set(TOKEN_RE.findall((right or '').lower()))
    if not left_tokens or not right_tokens:
        return None
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def set_overlap(left, right):
    left = set(left or ())
    right = set(right or ())
    if not left or not right:
        return None
    return len(left & right) / len(left | right)


def bayesian_rating(rating, reviews_count, catalog_average, minimum_reviews=5):
    rating = float(rating or 0)
    reviews_count = int(reviews_count or 0)
    catalog_average = float(catalog_average or 0)
    denominator = reviews_count + minimum_reviews
    if denominator <= 0:
        return 0.0
    return ((reviews_count / denominator) * rating) + ((minimum_reviews / denominator) * catalog_average)


class RecommendationEventService:
    PUBLIC_SOURCES = {
        EventType.VIEW: EventSource.CATALOG,
        EventType.SEARCH: EventSource.SEARCH,
        EventType.SEARCH_CLICK: EventSource.SEARCH,
        EventType.RECOMMENDATION_IMPRESSION: EventSource.RECOMMENDATION,
        EventType.RECOMMENDATION_CLICK: EventSource.RECOMMENDATION,
    }

    @classmethod
    def get_actor(cls, request):
        user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
        anonymous_hash = '' if user else getattr(request, 'recommendation_anonymous_id_hash', '')
        if not user and not anonymous_hash:
            raw_id = str(uuid.uuid4())
            anonymous_hash = cls.build_anonymous_hash(raw_id)
        return user, anonymous_hash

    @staticmethod
    def build_anonymous_hash(raw_id):
        return hash_anonymous_id(str(raw_id))

    @staticmethod
    def build_backfill_hash(kind, object_id):
        value = f'{settings.SECRET_KEY}:backfill:{kind}:{object_id}'.encode('utf-8')
        return hashlib.sha256(value).hexdigest()

    @classmethod
    def _sanitize_metadata(cls, metadata):
        metadata = metadata or {}
        if not isinstance(metadata, dict):
            raise ValidationError({'metadata': 'metadata должна быть объектом.'})
        cleaned = {}
        for key, value in metadata.items():
            if key not in METADATA_ALLOWED_KEYS:
                raise ValidationError({'metadata': f'Поле {key} не разрешено.'})
            if isinstance(value, (dict, list, tuple, set)):
                raise ValidationError({'metadata': 'Вложенные структуры не разрешены.'})
            if isinstance(value, str):
                if '<' in value or '>' in value:
                    raise ValidationError({'metadata': 'HTML не разрешён.'})
                value = value[:128]
            elif value is not None and not isinstance(value, (bool, int, float)):
                raise ValidationError({'metadata': 'Недопустимое значение metadata.'})
            cleaned[key] = value
        return cleaned

    @classmethod
    def _resolve_product(cls, product, public=False):
        if product in (None, ''):
            return None
        if isinstance(product, Product):
            resolved = product
        else:
            queryset = Product.objects.all()
            if public:
                queryset = queryset.filter(is_active=True)
            try:
                resolved = queryset.get(pk=product)
            except (Product.DoesNotExist, TypeError, ValueError) as exc:
                raise ValidationError({'product_id': 'Товар не найден.'}) from exc
        if public and not resolved.is_active:
            raise ValidationError({'product_id': 'Товар недоступен.'})
        return resolved

    @classmethod
    def _resolve_variant(cls, variant, product):
        if variant in (None, ''):
            return None
        if isinstance(variant, ProductVariant):
            resolved = variant
        else:
            try:
                resolved = ProductVariant.objects.select_related('product').get(pk=variant)
            except (ProductVariant.DoesNotExist, TypeError, ValueError) as exc:
                raise ValidationError({'variant_id': 'Вариант товара не найден.'}) from exc
        if product and resolved.product_id != product.id:
            raise ValidationError({'variant_id': 'Вариант не принадлежит товару.'})
        return resolved

    @classmethod
    def _is_duplicate_view(cls, *, user, anonymous_id_hash, product, occurred_at):
        actor_filter = Q(user=user) if user else Q(user__isnull=True, anonymous_id_hash=anonymous_id_hash)
        queryset = UserProductEvent.objects.filter(
            actor_filter,
            event_type=EventType.VIEW,
            product=product,
        )
        cutoff = occurred_at - timedelta(minutes=settings.RECOMMENDATION_VIEW_DEDUP_MINUTES)
        if queryset.filter(occurred_at__gte=cutoff).exists():
            return True
        day_start = occurred_at.replace(hour=0, minute=0, second=0, microsecond=0)
        return queryset.filter(occurred_at__gte=day_start).count() >= settings.RECOMMENDATION_MAX_VIEWS_PER_DAY

    @classmethod
    def record_event(
        cls,
        *,
        event_type,
        source,
        user=None,
        anonymous_id_hash='',
        product=None,
        variant=None,
        order_item=None,
        recommendation=None,
        context='',
        value=None,
        client_event_id=None,
        deduplication_key=None,
        search_query=None,
        metadata=None,
        occurred_at=None,
        schedule=True,
        public=False,
    ):
        if not settings.RECOMMENDATIONS_ENABLED:
            return None, False
        valid_events = {choice for choice, _ in EventType.choices}
        if event_type not in valid_events:
            raise ValidationError({'event_type': 'Неизвестный тип события.'})
        valid_sources = {choice for choice, _ in EventSource.choices}
        if source not in valid_sources:
            raise ValidationError({'source': 'Неизвестный источник события.'})
        valid_contexts = {choice for choice, _ in RecommendationContext.choices}
        if context and context not in valid_contexts:
            raise ValidationError({'context': 'Неизвестный контекст.'})
        if not user and not anonymous_id_hash:
            raise ValidationError('Событие должно иметь actor.')

        product = cls._resolve_product(product, public=public)
        if event_type not in PRODUCT_OPTIONAL_EVENT_TYPES and product is None:
            raise ValidationError({'product_id': 'Для этого события товар обязателен.'})
        variant = cls._resolve_variant(variant, product)
        metadata = cls._sanitize_metadata(metadata)
        occurred_at = occurred_at or timezone.now()
        if public:
            occurred_at = timezone.now()
        if event_type == EventType.VIEW and cls._is_duplicate_view(
            user=user,
            anonymous_id_hash=anonymous_id_hash,
            product=product,
            occurred_at=occurred_at,
        ):
            return None, True

        if search_query:
            if not settings.RECOMMENDATION_SEARCH_QUERY_ENABLED:
                search_query = None
            else:
                search_query = str(search_query).strip()[:255] or None

        try:
            with transaction.atomic():
                event = UserProductEvent.objects.create(
                    user=user,
                    anonymous_id_hash='' if user else anonymous_id_hash,
                    product=product,
                    variant=variant,
                    order_item=order_item,
                    recommendation=recommendation,
                    event_type=event_type,
                    source=source,
                    context=context,
                    value=value,
                    client_event_id=client_event_id,
                    deduplication_key=deduplication_key,
                    search_query=search_query,
                    metadata=metadata,
                    occurred_at=occurred_at,
                )
        except IntegrityError:
            if client_event_id or deduplication_key:
                return None, True
            raise

        if schedule and event_type in STRONG_EVENT_TYPES:
            cls.schedule_recalculation(event)
        return event, False

    @classmethod
    def record_public_event(cls, request, payload):
        event_type = payload['event_type']
        if event_type not in PUBLIC_EVENT_TYPES:
            raise ValidationError({'event_type': 'Этот тип события нельзя отправлять с клиента.'})
        user, anonymous_hash = cls.get_actor(request)
        recommendation = None
        tracking_id = payload.get('tracking_id')
        if tracking_id:
            try:
                recommendation = UserRecommendation.objects.select_related('user').get(tracking_id=tracking_id)
            except UserRecommendation.DoesNotExist as exc:
                raise ValidationError({'tracking_id': 'Рекомендация не найдена.'}) from exc
            if not user or recommendation.user_id != user.id:
                raise ValidationError({'tracking_id': 'Рекомендация не принадлежит пользователю.'})

        source = cls.PUBLIC_SOURCES[event_type]
        return cls.record_event(
            event_type=event_type,
            source=source,
            user=user,
            anonymous_id_hash=anonymous_hash,
            product=payload.get('product_id'),
            recommendation=recommendation,
            context=payload.get('context', ''),
            client_event_id=payload.get('client_event_id'),
            search_query=payload.get('search_query'),
            metadata=payload.get('metadata'),
            public=True,
        )

    @classmethod
    def record_business_event(cls, **kwargs):
        kwargs['public'] = False
        return cls.record_event(**kwargs)

    @classmethod
    def record_batch(cls, request, payloads):
        accepted = 0
        duplicates = 0
        rejected = []
        for index, payload in enumerate(payloads):
            try:
                event, duplicate = cls.record_public_event(request, payload)
            except ValidationError as exc:
                detail = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
                rejected.append({'index': index, 'errors': detail})
            else:
                if duplicate:
                    duplicates += 1
                elif event is not None:
                    accepted += 1
        return {'accepted': accepted, 'duplicates': duplicates, 'rejected': rejected}

    @classmethod
    def schedule_recalculation(cls, event):
        if not event.user_id:
            return

        def enqueue():
            try:
                from .tasks import refresh_user_recommendations

                refresh_user_recommendations.delay(event.user_id)
            except Exception:
                logger.exception('Failed to schedule recommendation refresh for user_id=%s', event.user_id)

        transaction.on_commit(enqueue)


class ProductEligibilityService:
    @classmethod
    def queryset(cls, *, user=None, context='', exclude_ids=None):
        available_variant = ProductVariant.objects.filter(
            product=OuterRef('pk'),
            is_active=True,
            stock_quantity__gt=0,
        )
        queryset = Product.objects.filter(is_active=True).annotate(
            _reco_in_stock=Exists(available_variant)
        ).filter(_reco_in_stock=True)
        if exclude_ids:
            queryset = queryset.exclude(pk__in=set(exclude_ids))
        if user and user.is_authenticated:
            now = timezone.now()
            hidden = HiddenRecommendation.objects.filter(
                user=user,
                product=OuterRef('pk'),
            ).filter(
                Q(context='all') | Q(context=context)
            ).filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now)
            )
            queryset = queryset.annotate(_reco_hidden=Exists(hidden)).filter(_reco_hidden=False)
        return queryset

    @classmethod
    def hydrate(cls, product_ids, *, user=None, context='', exclude_ids=None):
        ordered_ids = [int(product_id) for product_id in product_ids]
        if not ordered_ids:
            return []
        ordering = Case(*[When(pk=pk, then=position) for position, pk in enumerate(ordered_ids)])
        queryset = cls.queryset(user=user, context=context, exclude_ids=exclude_ids).filter(pk__in=ordered_ids)
        queryset = with_product_list_annotations(queryset.select_related('category', 'brand'))
        queryset = queryset.prefetch_related(
            Prefetch('images', queryset=ProductImage.objects.order_by('sort_order', 'id')),
            Prefetch(
                'variants',
                queryset=ProductVariant.objects.filter(is_active=True).select_related('color', 'size'),
            ),
        ).order_by(ordering)
        return list(queryset)


class RecommendationCacheService:
    @staticmethod
    def _version():
        return settings.RECOMMENDATION_ALGORITHM_VERSION

    @classmethod
    def personal_key(cls, user_id, context, page):
        return f'reco:{cls._version()}:user:{user_id}:{context}:{page}'

    @classmethod
    def popular_key(cls, category, window, page=1):
        return f'reco:{cls._version()}:popular:{category or "all"}:{window}:{page}'

    @classmethod
    def similar_key(cls, product_id):
        return f'reco:{cls._version()}:similar:{product_id}'

    @classmethod
    def bought_together_key(cls, product_id):
        return f'reco:{cls._version()}:bought_together:{product_id}'

    @classmethod
    def cart_key(cls, cart_id, version):
        safe_version = hashlib.sha256(str(version).encode('utf-8')).hexdigest()[:16]
        return f'reco:{cls._version()}:cart:{cart_id}:{safe_version}'

    @staticmethod
    def get(key):
        try:
            value = cache.get(key)
            logger.debug('Recommendation cache %s for key=%s', 'hit' if value is not None else 'miss', key)
            return value
        except Exception:
            logger.warning('Recommendation cache read failed for key=%s', key, exc_info=True)
            return None

    @staticmethod
    def set(key, value, timeout):
        try:
            cache.set(key, value, timeout=timeout)
            return True
        except Exception:
            logger.warning('Recommendation cache write failed for key=%s', key, exc_info=True)
            return False

    @staticmethod
    def delete(key):
        try:
            cache.delete(key)
        except Exception:
            logger.warning('Recommendation cache delete failed for key=%s', key, exc_info=True)

    @classmethod
    def invalidate_user(cls, user_id):
        for context, _ in RecommendationContext.choices:
            for page in range(1, 6):
                cls.delete(cls.personal_key(user_id, context, page))

    @staticmethod
    def acquire_lock(name, timeout=3600):
        key = f'reco:lock:{name}'
        try:
            return key if cache.add(key, str(uuid.uuid4()), timeout=timeout) else None
        except Exception:
            logger.warning('Recommendation cache lock unavailable: %s', name, exc_info=True)
            return key

    @staticmethod
    def release_lock(key):
        if key:
            RecommendationCacheService.delete(key)


class PopularityService:
    WINDOWS = {
        PopularityWindow.DAY: timedelta(days=1),
        PopularityWindow.WEEK: timedelta(days=7),
        PopularityWindow.MONTH: timedelta(days=30),
        PopularityWindow.ALL: None,
    }

    @staticmethod
    def _normalize(value, minimum, maximum):
        if maximum <= minimum:
            return 1.0 if value > 0 else 0.0
        return clamp((value - minimum) / (maximum - minimum))

    @classmethod
    def rebuild(cls, windows=None, batch_size=None):
        windows = windows or list(cls.WINDOWS)
        batch_size = batch_size or settings.RECOMMENDATION_TASK_BATCH_SIZE
        total_rows = 0
        for window in windows:
            total_rows += cls._rebuild_window(window, batch_size=batch_size)
        return total_rows

    @classmethod
    def _event_stats(cls, cutoff):
        queryset = UserProductEvent.objects.filter(product__isnull=False).filter(
            Q(metadata__scoring__isnull=True) | ~Q(metadata__scoring=False)
        )
        if cutoff:
            queryset = queryset.filter(occurred_at__gte=cutoff)
        rows = queryset.values('product_id').annotate(
            views_count=Count('id', filter=Q(event_type=EventType.VIEW)),
            search_clicks_count=Count('id', filter=Q(event_type=EventType.SEARCH_CLICK)),
            favorite_adds_count=Count('id', filter=Q(event_type=EventType.FAVORITE_ADD)),
            cart_adds_count=Count('id', filter=Q(event_type=EventType.CART_ADD)),
            purchases_count=Count('id', filter=Q(event_type=EventType.PURCHASE)),
            cancellations_count=Count('id', filter=Q(event_type=EventType.ORDER_CANCEL)),
            returns_count=Count('id', filter=Q(event_type=EventType.RETURN)),
        )
        return {row['product_id']: row for row in rows.iterator(chunk_size=2000)}

    @classmethod
    def _review_stats(cls):
        published = Review.objects.filter(status=Review.Status.PUBLISHED)
        catalog_average = published.aggregate(value=Avg('rating'))['value'] or 0
        rows = published.values('product_id').annotate(rating=Avg('rating'), reviews=Count('id'))
        return catalog_average, {row['product_id']: row for row in rows.iterator(chunk_size=2000)}

    @classmethod
    def _raw_score(cls, product, stats, review_stats, catalog_average, window):
        data = stats.get(product.id, {})
        rating_data = review_stats.get(product.id, {})
        rating = bayesian_rating(
            rating_data.get('rating', 0),
            rating_data.get('reviews', 0),
            catalog_average,
        ) / 5 if catalog_average else 0.0
        raw = (
            data.get('views_count', 0) * 0.2
            + data.get('search_clicks_count', 0) * 0.5
            + data.get('favorite_adds_count', 0) * 2.0
            + data.get('cart_adds_count', 0) * 3.0
            + data.get('purchases_count', 0) * 5.0
            - data.get('cancellations_count', 0) * 4.0
            - data.get('returns_count', 0) * 6.0
            + rating
        )
        interactions = sum(int(data.get(key, 0)) for key in (
            'views_count', 'search_clicks_count', 'favorite_adds_count', 'cart_adds_count',
            'purchases_count', 'cancellations_count', 'returns_count',
        ))
        if window == PopularityWindow.ALL and interactions == 0:
            raw += min(product.views_count, 10000) * 0.01
        return raw, rating, data

    @classmethod
    def _rebuild_window(cls, window, batch_size):
        started = time.monotonic()
        now = timezone.now()
        delta = cls.WINDOWS[window]
        cutoff = now - delta if delta else None
        event_stats = cls._event_stats(cutoff)
        catalog_average, review_stats = cls._review_stats()

        global_min = float('inf')
        global_max = float('-inf')
        category_ranges = defaultdict(lambda: [float('inf'), float('-inf')])
        products = Product.objects.filter(is_active=True).only('id', 'category_id', 'views_count')
        for product in products.iterator(chunk_size=batch_size):
            raw, _, _ = cls._raw_score(product, event_stats, review_stats, catalog_average, window)
            global_min = min(global_min, raw)
            global_max = max(global_max, raw)
            if product.category_id:
                category_ranges[product.category_id][0] = min(category_ranges[product.category_id][0], raw)
                category_ranges[product.category_id][1] = max(category_ranges[product.category_id][1], raw)

        if global_min == float('inf'):
            global_min = global_max = 0.0

        ProductPopularity.objects.filter(window=window).delete()
        pending = []
        created = 0
        for product in products.iterator(chunk_size=batch_size):
            raw, rating, data = cls._raw_score(product, event_stats, review_stats, catalog_average, window)
            common = {
                'product_id': product.id,
                'window': window,
                'views_count': data.get('views_count', 0),
                'search_clicks_count': data.get('search_clicks_count', 0),
                'favorite_adds_count': data.get('favorite_adds_count', 0),
                'cart_adds_count': data.get('cart_adds_count', 0),
                'purchases_count': data.get('purchases_count', 0),
                'cancellations_count': data.get('cancellations_count', 0),
                'returns_count': data.get('returns_count', 0),
                'rating_score': Decimal(str(round(rating, 8))),
                'window_started_at': cutoff,
                'window_ended_at': now,
                'calculated_at': now,
            }
            pending.append(ProductPopularity(
                scope=PopularityScope.GLOBAL,
                category=None,
                score=Decimal(str(round(cls._normalize(raw, global_min, global_max), 8))),
                **common,
            ))
            if product.category_id:
                cat_min, cat_max = category_ranges[product.category_id]
                pending.append(ProductPopularity(
                    scope=PopularityScope.CATEGORY,
                    category_id=product.category_id,
                    score=Decimal(str(round(cls._normalize(raw, cat_min, cat_max), 8))),
                    **common,
                ))
            if len(pending) >= batch_size:
                ProductPopularity.objects.bulk_create(pending, batch_size=batch_size)
                created += len(pending)
                pending = []
        if pending:
            ProductPopularity.objects.bulk_create(pending, batch_size=batch_size)
            created += len(pending)
        logger.info('Popularity window=%s rebuilt rows=%s duration=%.3fs', window, created, time.monotonic() - started)
        return created


class ProductRelationService:
    COMPONENT_WEIGHTS = {
        'category': 0.25,
        'brand': 0.15,
        'material_composition': 0.15,
        'season': 0.10,
        'price': 0.15,
        'color': 0.05,
        'size': 0.05,
        'text': 0.10,
    }

    @classmethod
    def _category_similarity(cls, left, right):
        if not left or not right:
            return None
        if left.id == right.id:
            return 1.0
        if left.tree_id != right.tree_id:
            return 0.0
        left_contains_right = left.lft <= right.lft and left.rght >= right.rght
        right_contains_left = right.lft <= left.lft and right.rght >= left.rght
        if left_contains_right or right_contains_left:
            return 0.7
        return 0.4

    @staticmethod
    def _variant_sets(product):
        variants = list(product.variants.all())
        colors = {variant.color_id for variant in variants if variant.color_id and variant.in_stock}
        sizes = {variant.size_id for variant in variants if variant.size_id and variant.in_stock}
        return colors, sizes

    @classmethod
    def content_components(cls, source, target):
        source_colors, source_sizes = cls._variant_sets(source)
        target_colors, target_sizes = cls._variant_sets(target)
        components = {
            'category': cls._category_similarity(source.category, target.category),
            'brand': None if not source.brand_id or not target.brand_id else float(source.brand_id == target.brand_id),
            'material_composition': token_overlap(
                f'{source.material_ru} {source.composition_ru}',
                f'{target.material_ru} {target.composition_ru}',
            ),
            'season': None if not source.season or not target.season else float(source.season == target.season),
            'price': price_proximity(source.price, target.price),
            'color': set_overlap(source_colors, target_colors),
            'size': set_overlap(source_sizes, target_sizes),
            'text': token_overlap(
                f'{source.name_ru} {source.description_ru}',
                f'{target.name_ru} {target.description_ru}',
            ),
        }
        used_weight = sum(cls.COMPONENT_WEIGHTS[key] for key, value in components.items() if value is not None)
        if not used_weight:
            return 0.0, {}
        score = sum(
            cls.COMPONENT_WEIGHTS[key] * value
            for key, value in components.items()
            if value is not None
        ) / used_weight
        return clamp(score), {key: round(value, 6) for key, value in components.items() if value is not None}

    @classmethod
    def _base_queryset(cls):
        variants = ProductVariant.objects.filter(is_active=True, stock_quantity__gt=0).select_related('color', 'size')
        return ProductEligibilityService.queryset().select_related('category', 'brand').prefetch_related(
            Prefetch('variants', queryset=variants)
        )

    @classmethod
    def content_candidates(cls, source, limit=None):
        limit = limit or settings.RECOMMENDATION_MAX_CANDIDATES
        candidate_filter = Q()
        if source.category_id:
            candidate_filter |= Q(category__tree_id=source.category.tree_id)
        if source.brand_id:
            candidate_filter |= Q(brand_id=source.brand_id)
        if source.price is not None:
            candidate_filter |= Q(price__gte=source.price * Decimal('0.50'), price__lte=source.price * Decimal('1.50'))
        if not candidate_filter:
            return []
        candidates = cls._base_queryset().filter(candidate_filter).exclude(pk=source.pk).distinct().order_by(
            '-is_featured', '-rating', '-created_at', 'id'
        )[:limit]
        scored = []
        for candidate in candidates:
            score, components = cls.content_components(source, candidate)
            if score > 0:
                scored.append((candidate.id, score, components))
        return sorted(scored, key=lambda item: (-item[1], item[0]))

    @classmethod
    def rebuild_content_relations(cls, product_ids=None, batch_size=None):
        started = time.monotonic()
        batch_size = batch_size or settings.RECOMMENDATION_TASK_BATCH_SIZE
        queryset = cls._base_queryset().order_by('id')
        if product_ids:
            queryset = queryset.filter(pk__in=product_ids)
        processed = created = 0
        now = timezone.now()
        top_limit = settings.RECOMMENDATION_RELATIONS_PER_PRODUCT
        for source in queryset.iterator(chunk_size=max(1, min(batch_size, 100))):
            try:
                scored = cls.content_candidates(source)[:top_limit]
                with transaction.atomic():
                    ProductRelation.objects.filter(
                        source_product=source,
                        relation_type=RelationType.CONTENT,
                    ).delete()
                    rows = [
                        ProductRelation(
                            source_product=source,
                            target_product_id=target_id,
                            relation_type=RelationType.CONTENT,
                            score=Decimal(str(round(score, 8))),
                            support_count=0,
                            confidence=Decimal(str(round(score, 8))),
                            components=components,
                            calculated_at=now,
                        )
                        for target_id, score, components in scored
                    ]
                    ProductRelation.objects.bulk_create(rows, batch_size=batch_size)
                created += len(rows)
                processed += 1
                RecommendationCacheService.delete(RecommendationCacheService.similar_key(source.id))
            except Exception:
                logger.exception('Content relation rebuild failed for product_id=%s', source.id)
        logger.info('Content relations rebuilt products=%s rows=%s duration=%.3fs', processed, created, time.monotonic() - started)
        return {'products': processed, 'relations': created}

    @classmethod
    def rebuild_co_purchase_relations(cls, batch_size=None):
        started = time.monotonic()
        batch_size = batch_size or settings.RECOMMENDATION_TASK_BATCH_SIZE
        successful = (
            Q(order__payment_status=Order.PaymentStatus.PAID)
            | Q(order__status=Order.Status.COMPLETED)
        ) & ~Q(order__status__in=[Order.Status.CANCELLED, Order.Status.RETURNED]) & ~Q(
            order__payment_status=Order.PaymentStatus.REFUNDED
        )
        item_rows = OrderItem.objects.filter(successful).values_list(
            'order_id', 'variant__product_id'
        ).order_by('order_id').iterator(chunk_size=batch_size)
        pair_counts = Counter()
        source_orders = Counter()
        current_order = None
        products = set()

        def consume(product_ids):
            ordered = sorted(product_ids)
            for source_id in ordered:
                source_orders[source_id] += 1
                for target_id in ordered:
                    if source_id != target_id:
                        pair_counts[(source_id, target_id)] += 1

        for order_id, product_id in item_rows:
            if current_order is not None and order_id != current_order:
                consume(products)
                products = set()
            current_order = order_id
            products.add(product_id)
        if products:
            consume(products)

        minimum_support = settings.RECOMMENDATION_CO_PURCHASE_MIN_SUPPORT
        per_source = defaultdict(list)
        for (source_id, target_id), support in pair_counts.items():
            if support < minimum_support:
                continue
            confidence = support / max(source_orders[source_id], 1)
            support_factor = min(math.log1p(support) / math.log1p(10), 1.0)
            score = clamp(confidence * support_factor)
            per_source[source_id].append((target_id, support, confidence, score))

        now = timezone.now()
        window_start = Order.objects.filter(
            Q(payment_status=Order.PaymentStatus.PAID) | Q(status=Order.Status.COMPLETED),
        ).exclude(status__in=[Order.Status.CANCELLED, Order.Status.RETURNED]).aggregate(
            value=Min('created_at')
        )['value']
        rows = []
        top_limit = settings.RECOMMENDATION_RELATIONS_PER_PRODUCT
        for source_id, values in per_source.items():
            for target_id, support, confidence, score in sorted(values, key=lambda item: (-item[3], -item[1], item[0]))[:top_limit]:
                rows.append(ProductRelation(
                    source_product_id=source_id,
                    target_product_id=target_id,
                    relation_type=RelationType.CO_PURCHASE,
                    score=Decimal(str(round(score, 8))),
                    support_count=support,
                    confidence=Decimal(str(round(confidence, 8))),
                    components={'support': support, 'source_orders': source_orders[source_id]},
                    window_started_at=window_start,
                    window_ended_at=now,
                    calculated_at=now,
                ))
        with transaction.atomic():
            ProductRelation.objects.filter(relation_type=RelationType.CO_PURCHASE).delete()
            ProductRelation.objects.bulk_create(rows, batch_size=batch_size)
        logger.info('Co-purchase relations rebuilt rows=%s duration=%.3fs', len(rows), time.monotonic() - started)
        return len(rows)


class UserPreferenceService:
    @classmethod
    def rebuild(cls, user_ids=None, batch_size=None):
        started = time.monotonic()
        batch_size = batch_size or settings.RECOMMENDATION_TASK_BATCH_SIZE
        if user_ids is None:
            user_ids = UserProductEvent.objects.filter(user__isnull=False).values_list('user_id', flat=True).distinct()
        processed = rows_created = 0
        for user_id in user_ids:
            try:
                rows_created += cls.rebuild_user(user_id, batch_size=batch_size)
                processed += 1
            except Exception:
                logger.exception('Preference rebuild failed for user_id=%s', user_id)
        logger.info('Preferences rebuilt users=%s rows=%s duration=%.3fs', processed, rows_created, time.monotonic() - started)
        return {'users': processed, 'preferences': rows_created}

    @classmethod
    def rebuild_user(cls, user_id, batch_size=None):
        batch_size = batch_size or settings.RECOMMENDATION_TASK_BATCH_SIZE
        aggregates = defaultdict(lambda: {'positive': 0.0, 'negative': 0.0, 'events': 0, 'last': None})
        events = UserProductEvent.objects.filter(
            user_id=user_id,
            product__category__isnull=False,
        ).select_related('product__category__parent').order_by('occurred_at')
        now = timezone.now()
        for event in events.iterator(chunk_size=batch_size):
            weight = effective_event_weight(event, now=now)
            if weight == 0:
                continue
            category = event.product.category
            cls._add_preference(aggregates[category.id], weight, event.occurred_at)
            if category.parent_id:
                cls._add_preference(aggregates[category.parent_id], weight * 0.30, event.occurred_at)

        with transaction.atomic():
            UserCategoryPreference.objects.filter(user_id=user_id).delete()
            rows = [
                UserCategoryPreference(
                    user_id=user_id,
                    category_id=category_id,
                    positive_score=Decimal(str(round(values['positive'], 8))),
                    negative_score=Decimal(str(round(values['negative'], 8))),
                    score=Decimal(str(round(values['positive'] - values['negative'], 8))),
                    events_count=values['events'],
                    last_event_at=values['last'],
                )
                for category_id, values in aggregates.items()
            ]
            UserCategoryPreference.objects.bulk_create(rows, batch_size=batch_size)
        return len(rows)

    @staticmethod
    def _add_preference(bucket, weight, occurred_at):
        if weight > 0:
            bucket['positive'] += weight
        else:
            bucket['negative'] += abs(weight)
        bucket['events'] += 1
        if bucket['last'] is None or occurred_at > bucket['last']:
            bucket['last'] = occurred_at


class RecommendationService:
    HOME_WEIGHTS = {
        'user_affinity': 0.35,
        'content': 0.25,
        'popularity': 0.20,
        'relation': 0.10,
        'freshness': 0.05,
        'business': 0.05,
    }

    @staticmethod
    def _candidate_bucket(candidates, product_id):
        return candidates.setdefault(product_id, {
            'user_affinity': 0.0,
            'content': 0.0,
            'popularity': 0.0,
            'relation': 0.0,
            'reason_code': None,
        })

    @staticmethod
    def _freshness(product, now=None):
        now = now or timezone.now()
        age_days = max((now - product.created_at).total_seconds() / 86400, 0)
        return decay_factor(age_days, 90)

    @classmethod
    def _seed_products(cls, user):
        events = UserProductEvent.objects.filter(
            user=user,
            product__isnull=False,
        ).exclude(event_type__in=[
            EventType.FAVORITE_REMOVE,
            EventType.CART_REMOVE,
            EventType.ORDER_CANCEL,
            EventType.RETURN,
            EventType.RECOMMENDATION_HIDE,
        ]).select_related('product').order_by('-occurred_at')[: settings.RECOMMENDATION_SEED_PRODUCTS * 5]
        seen = set()
        seeds = []
        now = timezone.now()
        for event in events:
            if event.product_id in seen or effective_event_weight(event, now=now) <= 0:
                continue
            seen.add(event.product_id)
            seeds.append(event.product)
            if len(seeds) >= settings.RECOMMENDATION_SEED_PRODUCTS:
                break
        return seeds

    @classmethod
    def generate_for_user(cls, user, context=RecommendationContext.HOME):
        if not settings.RECOMMENDATIONS_ENABLED:
            return []
        candidates = {}
        max_candidates = settings.RECOMMENDATION_MAX_CANDIDATES
        preferences = list(UserCategoryPreference.objects.filter(user=user, score__gt=0).order_by('-score')[:10])
        max_preference = float(preferences[0].score) if preferences else 1.0
        preference_map = {item.category_id: clamp(float(item.score) / max(max_preference, 0.0001)) for item in preferences}
        top_category_ids = list(preference_map)

        if top_category_ids:
            category_products = ProductEligibilityService.queryset(user=user, context=context).filter(
                category_id__in=top_category_ids
            ).values_list('id', 'category_id').order_by('-rating', '-created_at')[:max_candidates]
            for product_id, category_id in category_products:
                bucket = cls._candidate_bucket(candidates, product_id)
                bucket['user_affinity'] = max(bucket['user_affinity'], preference_map.get(category_id, 0.0))
                bucket['reason_code'] = 'because_category'

        seeds = cls._seed_products(user)
        seed_ids = [product.id for product in seeds]
        if seed_ids:
            relations = ProductRelation.objects.filter(source_product_id__in=seed_ids).order_by('-score')[:max_candidates * 2]
            for relation in relations:
                if relation.target_product_id in seed_ids:
                    continue
                bucket = cls._candidate_bucket(candidates, relation.target_product_id)
                score = float(relation.score)
                if relation.relation_type == RelationType.CONTENT:
                    bucket['content'] = max(bucket['content'], score)
                    bucket['reason_code'] = bucket['reason_code'] or 'similar_to_viewed'
                else:
                    bucket['relation'] = max(bucket['relation'], score)
                    bucket['reason_code'] = 'bought_together'

        popularity = ProductPopularity.objects.filter(
            scope=PopularityScope.GLOBAL,
            window=PopularityWindow.WEEK,
        ).order_by('-score')[:max_candidates]
        for row in popularity:
            bucket = cls._candidate_bucket(candidates, row.product_id)
            bucket['popularity'] = max(bucket['popularity'], float(row.score))
            bucket['reason_code'] = bucket['reason_code'] or 'popular'

        exploration = ProductEligibilityService.queryset(user=user, context=context).filter(
            Q(is_featured=True) | Q(is_new=True)
        ).values_list('id', flat=True).order_by('-is_featured', '-created_at')[:max(20, max_candidates // 5)]
        for product_id in exploration:
            bucket = cls._candidate_bucket(candidates, product_id)
            bucket['reason_code'] = bucket['reason_code'] or 'new_and_relevant'

        if len(candidates) > max_candidates:
            candidates = dict(list(candidates.items())[:max_candidates])

        candidate_products = list(ProductEligibilityService.queryset(user=user, context=context).filter(
            pk__in=candidates
        ).select_related('category', 'brand'))
        seed_brand_counts = Counter(product.brand_id for product in seeds if product.brand_id)
        max_brand_count = max(seed_brand_counts.values(), default=1)
        seed_prices = [float(product.price) for product in seeds if product.price is not None]
        median_price = statistics.median(seed_prices) if seed_prices else None
        recently_purchased = set(UserProductEvent.objects.filter(
            user=user,
            event_type=EventType.PURCHASE,
            occurred_at__gte=timezone.now() - timedelta(days=settings.RECOMMENDATION_RECENT_PURCHASE_DAYS),
        ).values_list('product_id', flat=True))

        scored = []
        for product in candidate_products:
            data = candidates[product.id]
            category_affinity = preference_map.get(product.category_id, 0.0)
            brand_affinity = seed_brand_counts.get(product.brand_id, 0) / max_brand_count if product.brand_id else 0.0
            price_affinity = price_proximity(product.price, median_price) if median_price is not None else 0.0
            data['user_affinity'] = max(
                data['user_affinity'],
                0.60 * category_affinity + 0.25 * brand_affinity + 0.15 * (price_affinity or 0.0),
            )
            components = {
                'user_affinity': clamp(data['user_affinity']),
                'content': clamp(data['content']),
                'popularity': clamp(data['popularity']),
                'relation': clamp(data['relation']),
                'freshness': cls._freshness(product),
                'business': 1.0 if product.is_featured else 0.0,
            }
            score = sum(cls.HOME_WEIGHTS[key] * components[key] for key in cls.HOME_WEIGHTS)
            if product.id in recently_purchased:
                score *= 0.5
            scored.append({
                'product_id': product.id,
                'category_id': product.category_id,
                'score': score,
                'reason_code': data['reason_code'] or 'fallback',
                'reason_payload': {key: round(value, 6) for key, value in components.items()},
                'is_fallback': False,
            })

        scored.sort(key=lambda item: (-item['score'], item['product_id']))
        selected = cls.apply_diversity(scored, settings.RECOMMENDATION_MAX_RESULTS)
        selected_ids = {item['product_id'] for item in selected}
        if len(selected) < settings.RECOMMENDATION_MAX_RESULTS:
            fallback_ids = cls.popular_product_ids(
                window=PopularityWindow.WEEK,
                limit=settings.RECOMMENDATION_MAX_RESULTS * 2,
                user=user,
                context=context,
                exclude_ids=selected_ids,
            )
            fallback_categories = dict(Product.objects.filter(
                id__in=fallback_ids,
            ).values_list('id', 'category_id'))
            fallback_rows = [
                {
                    'product_id': product_id,
                    'category_id': fallback_categories.get(product_id),
                    'score': 0.0,
                    'reason_code': 'fallback',
                    'reason_payload': {},
                    'is_fallback': True,
                }
                for product_id in fallback_ids
            ]
            selected = cls.apply_diversity(selected + fallback_rows, settings.RECOMMENDATION_MAX_RESULTS)

        return cls.save_generation(user, context, selected)

    @staticmethod
    def apply_diversity(items, limit):
        selected = []
        seen = set()
        max_per_category = settings.RECOMMENDATION_MAX_PER_CATEGORY
        page_size = settings.REST_FRAMEWORK['PAGE_SIZE']
        remaining = list(items)
        while remaining and len(selected) < limit:
            category_counts = Counter()
            page = []
            deferred = []
            for index, item in enumerate(remaining):
                if item['product_id'] in seen:
                    continue
                category_id = item.get('category_id')
                category_key = category_id if category_id is not None else f'none:{item["product_id"]}'
                if category_counts[category_key] >= max_per_category:
                    deferred.append(item)
                    continue
                page.append(item)
                seen.add(item['product_id'])
                category_counts[category_key] += 1
                if len(page) >= page_size or len(selected) + len(page) >= limit:
                    deferred.extend(remaining[index + 1:])
                    break
            if not page:
                break
            selected.extend(page)
            if len(page) < page_size and len(selected) < limit:
                break
            remaining = deferred
        return selected

    @classmethod
    def save_generation(cls, user, context, items):
        if not items:
            return []
        generation_id = uuid.uuid4()
        generated_at = timezone.now()
        expires_at = generated_at + timedelta(hours=settings.RECOMMENDATION_GENERATION_EXPIRY_HOURS)
        rows = [
            UserRecommendation(
                generation_id=generation_id,
                user=user,
                product_id=item['product_id'],
                context=context,
                rank=rank,
                score=Decimal(str(round(item['score'], 8))),
                reason_code=item['reason_code'],
                reason_payload=item.get('reason_payload', {}),
                algorithm_version=settings.RECOMMENDATION_ALGORITHM_VERSION,
                is_fallback=item.get('is_fallback', False),
                generated_at=generated_at,
                expires_at=expires_at,
            )
            for rank, item in enumerate(items, start=1)
        ]
        with transaction.atomic():
            UserRecommendation.objects.bulk_create(rows, batch_size=settings.RECOMMENDATION_TASK_BATCH_SIZE)
        RecommendationCacheService.invalidate_user(user.id)
        return list(UserRecommendation.objects.filter(generation_id=generation_id).order_by('rank'))

    @classmethod
    def latest_user_items(cls, user, context=RecommendationContext.HOME):
        latest = UserRecommendation.objects.filter(
            user=user,
            context=context,
            expires_at__gt=timezone.now(),
        ).order_by('-generated_at').first()
        if latest is None and settings.RECOMMENDATIONS_ENABLED:
            generated = cls.generate_for_user(user, context=context)
            latest = generated[0] if generated else None
        if latest is None:
            return []
        return [
            {
                'product_id': row.product_id,
                'tracking_id': str(row.tracking_id),
                'reason_code': row.reason_code,
                'is_fallback': row.is_fallback,
            }
            for row in UserRecommendation.objects.filter(
                user=user,
                context=context,
                generation_id=latest.generation_id,
            ).order_by('rank')
        ]

    @classmethod
    def popular_product_ids(
        cls,
        *,
        category=None,
        window=PopularityWindow.WEEK,
        limit=100,
        user=None,
        context=RecommendationContext.POPULAR,
        exclude_ids=None,
    ):
        exclude_ids = set(exclude_ids or ())
        category_id = getattr(category, 'id', category)
        scope = PopularityScope.CATEGORY if category_id else PopularityScope.GLOBAL
        rows = ProductPopularity.objects.filter(scope=scope, window=window)
        if category_id:
            rows = rows.filter(category_id=category_id)
        ids = list(rows.order_by('-score', 'product_id').exclude(product_id__in=exclude_ids).values_list(
            'product_id', flat=True
        )[:limit * 2])
        eligible = list(ProductEligibilityService.queryset(
            user=user,
            context=context,
            exclude_ids=exclude_ids,
        ).filter(pk__in=ids).values_list('id', flat=True))
        eligible_set = set(eligible)
        ordered = [product_id for product_id in ids if product_id in eligible_set]
        if len(ordered) < limit:
            fallback = ProductEligibilityService.queryset(
                user=user,
                context=context,
                exclude_ids=exclude_ids | set(ordered),
            )
            if category_id:
                fallback = fallback.filter(category_id=category_id)
            fallback_ids = fallback.order_by('-rating', '-views_count', '-created_at', 'id').values_list(
                'id', flat=True
            )[: limit - len(ordered)]
            ordered.extend(fallback_ids)
        return ordered[:limit]

    @classmethod
    def anonymous_items(cls, context=RecommendationContext.HOME, limit=100):
        return [
            {
                'product_id': product_id,
                'tracking_id': None,
                'reason_code': 'popular',
                'is_fallback': True,
            }
            for product_id in cls.popular_product_ids(window=PopularityWindow.WEEK, limit=limit, context=context)
        ]

    @classmethod
    def similar_product_ids(cls, product, limit=8):
        key = RecommendationCacheService.similar_key(product.id)
        cached = RecommendationCacheService.get(key)
        if cached is not None:
            ids = cached
        else:
            combined = defaultdict(float)
            for relation in ProductRelation.objects.filter(source_product=product).order_by('-score')[:200]:
                weight = 0.55 if relation.relation_type == RelationType.CONTENT else 0.20
                combined[relation.target_product_id] += weight * float(relation.score)
            popularity = dict(ProductPopularity.objects.filter(
                product_id__in=combined,
                scope=PopularityScope.GLOBAL,
                window=PopularityWindow.WEEK,
            ).values_list('product_id', 'score'))
            for product_id in list(combined):
                combined[product_id] += 0.20 * float(popularity.get(product_id, 0))
            if not combined:
                for target_id, score, _ in ProductRelationService.content_candidates(product, limit=100):
                    combined[target_id] = 0.55 * score
            ids = [product_id for product_id, _ in sorted(combined.items(), key=lambda item: (-item[1], item[0]))]
            if len(ids) < limit:
                fallback = cls.popular_product_ids(
                    category=product.category_id,
                    window=PopularityWindow.WEEK,
                    limit=limit * 2,
                    context=RecommendationContext.PRODUCT,
                    exclude_ids=set(ids) | {product.id},
                )
                ids.extend(fallback)
            ids = list(dict.fromkeys(ids))[: max(limit, 100)]
            RecommendationCacheService.set(key, ids, settings.RECOMMENDATION_CACHE_TTLS['similar'])
        hydrated = ProductEligibilityService.hydrate(
            ids,
            context=RecommendationContext.PRODUCT,
            exclude_ids={product.id},
        )
        return [item.id for item in hydrated[:limit]]

    @classmethod
    def bought_together_items(cls, product, limit=24):
        key = RecommendationCacheService.bought_together_key(product.id)
        ids = RecommendationCacheService.get(key)
        if ids is None:
            ids = list(ProductRelation.objects.filter(
                source_product=product,
                relation_type=RelationType.CO_PURCHASE,
            ).order_by('-score', '-support_count', 'target_product_id').values_list('target_product_id', flat=True)[:100])
            RecommendationCacheService.set(key, ids, settings.RECOMMENDATION_CACHE_TTLS['bought_together'])
        products = ProductEligibilityService.hydrate(
            ids,
            context=RecommendationContext.BOUGHT_TOGETHER,
            exclude_ids={product.id},
        )[:limit]
        return [
            {'product_id': item.id, 'tracking_id': None, 'reason_code': 'bought_together', 'is_fallback': False}
            for item in products
        ]

    @classmethod
    def cart_items(cls, cart, *, user=None, limit=12):
        cart_product_ids = set(cart.items.values_list('variant__product_id', flat=True))
        aggregate = defaultdict(float)
        relations = ProductRelation.objects.filter(source_product_id__in=cart_product_ids).order_by('-score')[:500]
        for relation in relations:
            if relation.target_product_id in cart_product_ids:
                continue
            weight = 0.65 if relation.relation_type == RelationType.CO_PURCHASE else 0.25
            aggregate[relation.target_product_id] = max(
                aggregate[relation.target_product_id],
                weight * float(relation.score),
            )
        ordered = [product_id for product_id, _ in sorted(aggregate.items(), key=lambda item: (-item[1], item[0]))]
        products = ProductEligibilityService.hydrate(
            ordered,
            user=user,
            context=RecommendationContext.CART,
            exclude_ids=cart_product_ids,
        )
        items = [
            {'product_id': product.id, 'tracking_id': None, 'reason_code': 'bought_together', 'is_fallback': False}
            for product in products[:limit]
        ]
        if len(items) < limit:
            excluded = cart_product_ids | {item['product_id'] for item in items}
            fallback_ids = cls.popular_product_ids(
                window=PopularityWindow.WEEK,
                limit=limit - len(items),
                user=user,
                context=RecommendationContext.CART,
                exclude_ids=excluded,
            )
            items.extend({
                'product_id': product_id,
                'tracking_id': None,
                'reason_code': 'fallback',
                'is_fallback': True,
            } for product_id in fallback_ids)
        return items[:limit]

    @classmethod
    def hydrate_items(cls, items, *, user=None, context='', limit=None):
        item_map = {int(item['product_id']): item for item in items}
        products = ProductEligibilityService.hydrate(
            list(item_map),
            user=user,
            context=context,
        )
        result = []
        for product in products:
            metadata = item_map[product.id]
            result.append({
                'tracking_id': metadata.get('tracking_id'),
                'reason_code': metadata.get('reason_code', 'fallback'),
                'is_fallback': metadata.get('is_fallback', False),
                'product': product,
            })
            if limit and len(result) >= limit:
                break
        return result


class HiddenRecommendationService:
    @classmethod
    def hide(cls, *, user, product, context, reason='', tracking_id=None):
        recommendation = None
        if tracking_id:
            try:
                recommendation = UserRecommendation.objects.get(tracking_id=tracking_id, user=user)
            except UserRecommendation.DoesNotExist as exc:
                raise ValidationError({'tracking_id': 'Рекомендация не найдена.'}) from exc
            if recommendation.product_id != product.id:
                raise ValidationError({'tracking_id': 'Рекомендация относится к другому товару.'})
        hidden, _ = HiddenRecommendation.objects.update_or_create(
            user=user,
            product=product,
            context=context,
            defaults={'reason': reason, 'source_recommendation': recommendation},
        )
        RecommendationEventService.record_business_event(
            event_type=EventType.RECOMMENDATION_HIDE,
            source=EventSource.RECOMMENDATION,
            user=user,
            product=product,
            recommendation=recommendation,
            context=context,
            deduplication_key=f'recommendation_hide:{hidden.id}',
        )
        RecommendationCacheService.invalidate_user(user.id)
        return hidden

    @classmethod
    def unhide(cls, *, user, product, context):
        deleted, _ = HiddenRecommendation.objects.filter(
            user=user,
            product=product,
            context=context,
        ).delete()
        RecommendationCacheService.invalidate_user(user.id)
        return bool(deleted)
