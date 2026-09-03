from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.accounts.models import User, Wishlist
from apps.catalog.models import Review
from apps.orders.models import CartItem, Order, OrderItem

from ...constants import EventSource, EventType, RecommendationContext
from ...models import UserProductEvent
from ...services import (
    PopularityService,
    ProductRelationService,
    RecommendationEventService,
    RecommendationService,
    UserPreferenceService,
)


class Command(BaseCommand):
    help = 'Идемпотентно заполняет данные рекомендательной системы из существующих бизнес-таблиц.'

    def add_arguments(self, parser):
        parser.add_argument('--events', action='store_true')
        parser.add_argument('--popularity', action='store_true')
        parser.add_argument('--preferences', action='store_true')
        parser.add_argument('--content-relations', action='store_true')
        parser.add_argument('--co-purchase', action='store_true')
        parser.add_argument('--recommendations', action='store_true')
        parser.add_argument('--all', action='store_true')
        parser.add_argument('--batch-size', type=int, default=500)
        parser.add_argument('--user-id', type=int)
        parser.add_argument('--product-id', type=int)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        if options['batch_size'] <= 0:
            raise CommandError('--batch-size должен быть положительным.')
        selected = any(options[name] for name in (
            'events', 'popularity', 'preferences', 'content_relations',
            'co_purchase', 'recommendations', 'all',
        ))
        if not selected:
            options['all'] = True

        flags = {
            'events': options['all'] or options['events'],
            'popularity': options['all'] or options['popularity'],
            'preferences': options['all'] or options['preferences'],
            'content_relations': options['all'] or options['content_relations'],
            'co_purchase': options['all'] or options['co_purchase'],
            'recommendations': options['all'] or options['recommendations'],
        }
        self.dry_run = options['dry_run']
        self.batch_size = options['batch_size']
        self.user_id = options.get('user_id')
        self.product_id = options.get('product_id')
        summary = {}

        if flags['events']:
            summary['events'] = self._backfill_events()
        if flags['popularity']:
            summary['popularity'] = self._run_or_describe(
                'popularity',
                lambda: PopularityService.rebuild(batch_size=self.batch_size),
            )
        if flags['preferences']:
            user_ids = [self.user_id] if self.user_id else None
            summary['preferences'] = self._run_or_describe(
                'preferences',
                lambda: UserPreferenceService.rebuild(user_ids=user_ids, batch_size=self.batch_size),
            )
        if flags['content_relations']:
            product_ids = [self.product_id] if self.product_id else None
            summary['content_relations'] = self._run_or_describe(
                'content-relations',
                lambda: ProductRelationService.rebuild_content_relations(
                    product_ids=product_ids,
                    batch_size=self.batch_size,
                ),
            )
        if flags['co_purchase']:
            summary['co_purchase'] = self._run_or_describe(
                'co-purchase',
                lambda: ProductRelationService.rebuild_co_purchase_relations(batch_size=self.batch_size),
            )
        if flags['recommendations']:
            summary['recommendations'] = self._backfill_recommendations()

        prefix = 'DRY RUN — ' if self.dry_run else ''
        self.stdout.write(self.style.SUCCESS(f'{prefix}backfill завершён: {summary}'))

    def _run_or_describe(self, label, callback):
        if self.dry_run:
            self.stdout.write(f'DRY RUN: расчёт {label} будет выполнен.')
            return 'dry-run'
        return callback()

    def _record(self, *, deduplication_key, **kwargs):
        if UserProductEvent.objects.filter(deduplication_key=deduplication_key).exists():
            return 'duplicate'
        if self.dry_run:
            return 'created'
        _, duplicate = RecommendationEventService.record_business_event(
            deduplication_key=deduplication_key,
            schedule=False,
            **kwargs,
        )
        return 'duplicate' if duplicate else 'created'

    def _actor(self, user, kind, object_id):
        if user:
            return {'user': user, 'anonymous_id_hash': ''}
        return {
            'user': None,
            'anonymous_id_hash': RecommendationEventService.build_backfill_hash(kind, object_id),
        }

    def _backfill_events(self):
        stats = {'created': 0, 'duplicates': 0, 'errors': 0}
        items = OrderItem.objects.select_related('order__user', 'variant__product').order_by('id')
        if self.user_id:
            items = items.filter(order__user_id=self.user_id)
        if self.product_id:
            items = items.filter(variant__product_id=self.product_id)
        for index, item in enumerate(items.iterator(chunk_size=self.batch_size), start=1):
            try:
                actor = self._actor(item.order.user, 'order', item.order_id)
                self._count(stats, self._record(
                    deduplication_key=f'order_created:{item.id}',
                    event_type=EventType.ORDER_CREATED,
                    source=EventSource.ORDER,
                    product=item.variant.product,
                    variant=item.variant,
                    order_item=item,
                    context=RecommendationContext.HOME,
                    value=item.quantity,
                    occurred_at=item.order.created_at,
                    **actor,
                ))
                successful = (
                    item.order.payment_status == Order.PaymentStatus.PAID
                    or item.order.status == Order.Status.COMPLETED
                ) and item.order.status not in {Order.Status.CANCELLED, Order.Status.RETURNED} and (
                    item.order.payment_status != Order.PaymentStatus.REFUNDED
                )
                if successful:
                    self._count(stats, self._record(
                        deduplication_key=f'purchase:{item.id}',
                        event_type=EventType.PURCHASE,
                        source=EventSource.ORDER,
                        product=item.variant.product,
                        variant=item.variant,
                        order_item=item,
                        context=RecommendationContext.HOME,
                        value=item.quantity,
                        occurred_at=item.order.updated_at,
                        **actor,
                    ))
                if item.order.status == Order.Status.CANCELLED:
                    self._count(stats, self._record(
                        deduplication_key=f'backfill:order_cancel:{item.id}',
                        event_type=EventType.ORDER_CANCEL,
                        source=EventSource.ORDER,
                        product=item.variant.product,
                        variant=item.variant,
                        order_item=item,
                        context=RecommendationContext.HOME,
                        value=item.quantity,
                        occurred_at=item.order.updated_at,
                        **actor,
                    ))
                elif item.order.status == Order.Status.RETURNED:
                    self._count(stats, self._record(
                        deduplication_key=f'backfill:return:{item.id}',
                        event_type=EventType.RETURN,
                        source=EventSource.ORDER,
                        product=item.variant.product,
                        variant=item.variant,
                        order_item=item,
                        context=RecommendationContext.HOME,
                        value=item.quantity,
                        occurred_at=item.order.updated_at,
                        **actor,
                    ))
            except Exception as exc:
                stats['errors'] += 1
                self.stderr.write(f'OrderItem #{item.id}: {exc}')
            if index % self.batch_size == 0:
                self.stdout.write(f'Orders processed: {index}')

        reviews = Review.objects.filter(status=Review.Status.PUBLISHED).select_related('user', 'product').order_by('id')
        if self.user_id:
            reviews = reviews.filter(user_id=self.user_id)
        if self.product_id:
            reviews = reviews.filter(product_id=self.product_id)
        for review in reviews.iterator(chunk_size=self.batch_size):
            try:
                self._count(stats, self._record(
                    deduplication_key=f'rating:{review.id}',
                    event_type=EventType.RATING,
                    source=EventSource.REVIEW,
                    user=review.user,
                    product=review.product,
                    context=RecommendationContext.PRODUCT,
                    value=review.rating,
                    occurred_at=review.created_at,
                ))
            except Exception as exc:
                stats['errors'] += 1
                self.stderr.write(f'Review #{review.id}: {exc}')

        wishlist = Wishlist.objects.select_related('user', 'product').order_by('id')
        if self.user_id:
            wishlist = wishlist.filter(user_id=self.user_id)
        if self.product_id:
            wishlist = wishlist.filter(product_id=self.product_id)
        for item in wishlist.iterator(chunk_size=self.batch_size):
            try:
                self._count(stats, self._record(
                    deduplication_key=f'favorite_add:{item.id}',
                    event_type=EventType.FAVORITE_ADD,
                    source=EventSource.WISHLIST,
                    user=item.user,
                    product=item.product,
                    context=RecommendationContext.HOME,
                    occurred_at=item.added_at,
                ))
            except Exception as exc:
                stats['errors'] += 1
                self.stderr.write(f'Wishlist #{item.id}: {exc}')

        cart_items = CartItem.objects.select_related('cart__user', 'variant__product').order_by('id')
        if self.user_id:
            cart_items = cart_items.filter(cart__user_id=self.user_id)
        if self.product_id:
            cart_items = cart_items.filter(variant__product_id=self.product_id)
        for item in cart_items.iterator(chunk_size=self.batch_size):
            try:
                actor = self._actor(item.cart.user, 'cart', item.cart_id)
                self._count(stats, self._record(
                    deduplication_key=f'backfill:cart_add:{item.id}',
                    event_type=EventType.CART_ADD,
                    source=EventSource.CART,
                    product=item.variant.product,
                    variant=item.variant,
                    context=RecommendationContext.CART,
                    value=item.quantity,
                    occurred_at=item.created_at,
                    **actor,
                ))
            except Exception as exc:
                stats['errors'] += 1
                self.stderr.write(f'CartItem #{item.id}: {exc}')
        return stats

    def _backfill_recommendations(self):
        queryset = User.objects.filter(is_active=True, role=User.Role.CUSTOMER).order_by('id')
        if self.user_id:
            queryset = queryset.filter(pk=self.user_id)
        if self.dry_run:
            return {'users': queryset.count(), 'recommendations': 'dry-run'}
        users = generated = 0
        for user in queryset.iterator(chunk_size=self.batch_size):
            rows = RecommendationService.generate_for_user(user)
            generated += len(rows)
            users += 1
            if users % self.batch_size == 0:
                self.stdout.write(f'Recommendations generated for users: {users}')
        return {'users': users, 'recommendations': generated}

    @staticmethod
    def _count(stats, result):
        if result == 'duplicate':
            stats['duplicates'] += 1
        else:
            stats['created'] += 1
