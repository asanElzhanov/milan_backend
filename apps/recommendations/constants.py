from django.db import models


class EventType(models.TextChoices):
    VIEW = 'view', 'Просмотр'
    SEARCH = 'search', 'Поиск'
    SEARCH_CLICK = 'search_click', 'Переход из поиска'
    FAVORITE_ADD = 'favorite_add', 'Добавление в избранное'
    FAVORITE_REMOVE = 'favorite_remove', 'Удаление из избранного'
    CART_ADD = 'cart_add', 'Добавление в корзину'
    CART_REMOVE = 'cart_remove', 'Удаление из корзины'
    ORDER_CREATED = 'order_created', 'Заказ создан'
    PURCHASE = 'purchase', 'Покупка'
    ORDER_CANCEL = 'order_cancel', 'Отмена заказа'
    RETURN = 'return', 'Возврат'
    RATING = 'rating', 'Оценка'
    RECOMMENDATION_IMPRESSION = 'recommendation_impression', 'Показ рекомендации'
    RECOMMENDATION_CLICK = 'recommendation_click', 'Клик по рекомендации'
    RECOMMENDATION_HIDE = 'recommendation_hide', 'Скрытие рекомендации'


class EventSource(models.TextChoices):
    CATALOG = 'catalog', 'Каталог'
    SEARCH = 'search', 'Поиск'
    WISHLIST = 'wishlist', 'Избранное'
    CART = 'cart', 'Корзина'
    ORDER = 'order', 'Заказ'
    REVIEW = 'review', 'Отзыв'
    RECOMMENDATION = 'recommendation', 'Рекомендация'


class RecommendationContext(models.TextChoices):
    HOME = 'home', 'Главная'
    PRODUCT = 'product', 'Товар'
    CART = 'cart', 'Корзина'
    SEARCH = 'search', 'Поиск'
    POPULAR = 'popular', 'Популярное'
    BOUGHT_TOGETHER = 'bought_together', 'Покупают вместе'


class RelationType(models.TextChoices):
    CONTENT = 'content', 'Похожие по содержанию'
    CO_PURCHASE = 'co_purchase', 'Покупают вместе'


class PopularityWindow(models.TextChoices):
    DAY = '1d', '1 день'
    WEEK = '7d', '7 дней'
    MONTH = '30d', '30 дней'
    ALL = 'all', 'Всё время'


class PopularityScope(models.TextChoices):
    GLOBAL = 'global', 'Глобальная'
    CATEGORY = 'category', 'По категории'


PUBLIC_EVENT_TYPES = {
    EventType.VIEW,
    EventType.SEARCH,
    EventType.SEARCH_CLICK,
    EventType.RECOMMENDATION_IMPRESSION,
    EventType.RECOMMENDATION_CLICK,
}

STRONG_EVENT_TYPES = {
    EventType.FAVORITE_ADD,
    EventType.FAVORITE_REMOVE,
    EventType.CART_ADD,
    EventType.CART_REMOVE,
    EventType.PURCHASE,
    EventType.RATING,
    EventType.RECOMMENDATION_HIDE,
}

PRODUCT_OPTIONAL_EVENT_TYPES = {EventType.SEARCH}

METADATA_ALLOWED_KEYS = {
    'source',
    'position',
    'page',
    'query_id',
    'campaign',
    'scoring',
}

REASON_CODES = {
    'because_category',
    'because_brand',
    'similar_to_viewed',
    'similar_to_purchased',
    'bought_together',
    'popular_in_category',
    'popular',
    'new_and_relevant',
    'fallback',
}
