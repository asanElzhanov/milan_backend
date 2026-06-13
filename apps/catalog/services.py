from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count
from django.utils import timezone

from apps.accounts.models import User
from apps.orders.models import Order

from .models import ProductVariant, Review, StockMovement


class InvalidStockQuantityError(ValidationError):
    pass


class NotEnoughStockError(ValidationError):
    pass


class ReviewNotAllowedError(ValidationError):
    pass


class DuplicateReviewError(ValidationError):
    pass


class InvalidReviewRatingError(ValidationError):
    pass


class ReviewModerationError(ValidationError):
    pass


class ReviewRatingService:
    @classmethod
    def recalculate_product_rating(cls, product):
        stats = Review.objects.filter(
            product=product,
            status=Review.Status.PUBLISHED,
        ).aggregate(
            average_rating=Avg('rating'),
            reviews_count=Count('id'),
        )
        average_rating = stats['average_rating']
        reviews_count = stats['reviews_count']
        product.rating = cls._normalize_rating(average_rating)
        product.reviews_count = reviews_count
        product.save(update_fields=['rating', 'reviews_count', 'updated_at'])
        return product

    @staticmethod
    def _normalize_rating(value):
        if value is None:
            return Decimal('0.00')
        return Decimal(str(value)).quantize(Decimal('0.01'))


class ReviewModerationService:
    @classmethod
    def publish_review(cls, review, user, comment=''):
        return cls._moderate_review(
            review=review,
            user=user,
            status=Review.Status.PUBLISHED,
            comment=comment,
        )

    @classmethod
    def reject_review(cls, review, user, comment=''):
        return cls._moderate_review(
            review=review,
            user=user,
            status=Review.Status.REJECTED,
            comment=comment,
        )

    @classmethod
    def hide_review(cls, review, user, comment=''):
        return cls._moderate_review(
            review=review,
            user=user,
            status=Review.Status.HIDDEN,
            comment=comment,
        )

    @classmethod
    def _moderate_review(cls, *, review, user, status, comment=''):
        cls._validate_moderator(user)
        with transaction.atomic():
            locked_review = (
                Review.objects.select_for_update()
                .select_related('product')
                .get(pk=review.pk)
            )
            locked_review.status = status
            locked_review.moderated_by = user
            locked_review.moderated_at = timezone.now()
            locked_review.moderation_comment = comment or ''
            locked_review.save(update_fields=[
                'status', 'moderated_by', 'moderated_at',
                'moderation_comment', 'updated_at',
            ])
            ReviewRatingService.recalculate_product_rating(locked_review.product)
            from apps.notifications.services import EmailNotificationService

            if status == Review.Status.PUBLISHED:
                EmailNotificationService.schedule_review_published_email(locked_review)
            elif status == Review.Status.REJECTED:
                EmailNotificationService.schedule_review_rejected_email(locked_review)
            return locked_review

    @staticmethod
    def _validate_moderator(user):
        if not user or not user.is_authenticated:
            raise ReviewModerationError('Войдите в аккаунт для модерации отзыва.')
        if getattr(user, 'is_superuser', False):
            return
        if getattr(user, 'role', None) in {User.Role.MANAGER, User.Role.ADMIN}:
            return
        raise ReviewModerationError('Недостаточно прав для модерации отзыва.')


class ProductReviewService:
    allowed_order_statuses = {
        Order.Status.COMPLETED,
        Order.Status.PAID,
    }

    @classmethod
    def can_review_product(cls, user, product, order):
        cls._validate_user(user)
        cls._validate_order_owner(user, order)
        cls._validate_order_status(order)
        cls._validate_order_contains_product(order, product)
        cls._validate_not_duplicate(user, product, order)
        return True

    @classmethod
    def create_review(cls, *, user, product, order, rating, text=''):
        rating = cls._validate_rating(rating)
        with transaction.atomic():
            cls.can_review_product(user, product, order)
            try:
                return Review.objects.create(
                    product=product,
                    user=user,
                    order=order,
                    rating=rating,
                    text=text,
                    status=Review.Status.PENDING,
                    is_verified_purchase=True,
                )
            except IntegrityError as exc:
                raise DuplicateReviewError(
                    'Вы уже оставили отзыв на этот товар в рамках этого заказа.'
                ) from exc

    @staticmethod
    def _validate_user(user):
        if not user or not user.is_authenticated:
            raise ReviewNotAllowedError('Войдите в аккаунт, чтобы оставить отзыв.')

    @staticmethod
    def _validate_order_owner(user, order):
        if order.user_id is None:
            raise ReviewNotAllowedError(
                'Гостевой заказ нельзя использовать для отзыва через личный кабинет.'
            )
        if order.user_id != user.id:
            raise ReviewNotAllowedError('Нельзя оставить отзыв по чужому заказу.')

    @classmethod
    def _validate_order_status(cls, order):
        if order.status not in cls.allowed_order_statuses:
            raise ReviewNotAllowedError(
                'Отзыв можно оставить только после оплаты или завершения заказа.'
            )

    @staticmethod
    def _validate_order_contains_product(order, product):
        has_product = order.items.filter(variant__product=product).exists()
        if not has_product:
            raise ReviewNotAllowedError('В этом заказе нет выбранного товара.')

    @staticmethod
    def _validate_not_duplicate(user, product, order):
        duplicate_exists = Review.objects.filter(
            product=product,
            user=user,
            order=order,
        ).exists()
        if duplicate_exists:
            raise DuplicateReviewError(
                'Вы уже оставили отзыв на этот товар в рамках этого заказа.'
            )

    @staticmethod
    def _validate_rating(rating):
        try:
            rating = int(rating)
        except (TypeError, ValueError) as exc:
            raise InvalidReviewRatingError('Оценка должна быть числом от 1 до 5.') from exc
        if rating < 1 or rating > 5:
            raise InvalidReviewRatingError('Оценка должна быть от 1 до 5.')
        return rating


class StockService:
    @classmethod
    def check_availability(cls, variant, quantity):
        quantity = cls._validate_quantity(quantity)
        variant = cls._resolve_variant(variant)
        return variant.is_active and variant.stock_quantity >= quantity

    @classmethod
    def income(cls, variant, quantity, user=None, comment=''):
        return cls._change_stock(
            variant=variant,
            quantity=quantity,
            operation_type=StockMovement.OperationType.INCOME,
            direction=1,
            user=user,
            comment=comment,
        )

    @classmethod
    def sale(cls, variant, quantity, user=None, comment=''):
        return cls._change_stock(
            variant=variant,
            quantity=quantity,
            operation_type=StockMovement.OperationType.SALE,
            direction=-1,
            user=user,
            comment=comment,
            require_available=True,
        )

    @classmethod
    def return_stock(cls, variant, quantity, user=None, comment=''):
        return cls._change_stock(
            variant=variant,
            quantity=quantity,
            operation_type=StockMovement.OperationType.RETURN,
            direction=1,
            user=user,
            comment=comment,
        )

    @classmethod
    def cancel_order(cls, variant, quantity, user=None, comment=''):
        return cls._change_stock(
            variant=variant,
            quantity=quantity,
            operation_type=StockMovement.OperationType.ORDER_CANCEL,
            direction=1,
            user=user,
            comment=comment,
        )

    @classmethod
    def manual_adjustment(cls, variant, new_quantity, user=None, comment=''):
        new_quantity = cls._validate_non_negative_quantity(new_quantity)
        with transaction.atomic():
            locked_variant = cls._lock_variant(variant)
            current_quantity = locked_variant.stock_quantity
            movement_quantity = abs(new_quantity - current_quantity)
            if movement_quantity == 0:
                raise InvalidStockQuantityError('Новый остаток совпадает с текущим.')

            locked_variant.stock_quantity = new_quantity
            locked_variant.save(update_fields=['stock_quantity', 'updated_at'])
            return StockMovement.objects.create(
                variant=locked_variant,
                quantity=movement_quantity,
                operation_type=StockMovement.OperationType.MANUAL_ADJUSTMENT,
                user=user,
                comment=comment,
            )

    @classmethod
    def _change_stock(
        cls,
        *,
        variant,
        quantity,
        operation_type,
        direction,
        user=None,
        comment='',
        require_available=False,
    ):
        quantity = cls._validate_quantity(quantity)
        with transaction.atomic():
            locked_variant = cls._lock_variant(variant)
            if require_available and not cls._has_available_stock(locked_variant, quantity):
                raise NotEnoughStockError('Недостаточно товара на складе.')

            new_quantity = locked_variant.stock_quantity + (direction * quantity)
            if new_quantity < 0:
                raise NotEnoughStockError('Остаток не может быть отрицательным.')

            locked_variant.stock_quantity = new_quantity
            locked_variant.save(update_fields=['stock_quantity', 'updated_at'])
            return StockMovement.objects.create(
                variant=locked_variant,
                quantity=quantity,
                operation_type=operation_type,
                user=user,
                comment=comment,
            )

    @classmethod
    def _lock_variant(cls, variant):
        variant_id = cls._resolve_variant_id(variant)
        return ProductVariant.objects.select_for_update().get(pk=variant_id)

    @staticmethod
    def _resolve_variant(variant):
        if isinstance(variant, ProductVariant):
            return variant
        return ProductVariant.objects.get(pk=variant)

    @staticmethod
    def _resolve_variant_id(variant):
        if isinstance(variant, ProductVariant):
            return variant.pk
        return variant

    @staticmethod
    def _validate_quantity(quantity):
        try:
            quantity = int(quantity)
        except (TypeError, ValueError) as exc:
            raise InvalidStockQuantityError('Количество должно быть положительным числом.') from exc
        if quantity <= 0:
            raise InvalidStockQuantityError('Количество должно быть больше нуля.')
        return quantity

    @classmethod
    def _validate_non_negative_quantity(cls, quantity):
        try:
            quantity = int(quantity)
        except (TypeError, ValueError) as exc:
            raise InvalidStockQuantityError('Остаток должен быть числом.') from exc
        if quantity < 0:
            raise InvalidStockQuantityError('Остаток не может быть отрицательным.')
        return quantity

    @staticmethod
    def _has_available_stock(variant, quantity):
        return variant.is_active and variant.stock_quantity >= quantity
