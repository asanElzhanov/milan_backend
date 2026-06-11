from django.core.exceptions import ValidationError
from django.db import transaction

from .models import ProductVariant, StockMovement


class InvalidStockQuantityError(ValidationError):
    pass


class NotEnoughStockError(ValidationError):
    pass


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
