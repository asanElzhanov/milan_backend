import math

from django.conf import settings
from django.db.models import Count, Max, Sum
from django.http import QueryDict
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
)
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.catalog.models import Category, Product
from apps.orders.services import CartError
from apps.orders.views import get_current_cart

from .constants import PopularityWindow, RecommendationContext
from .serializers import (
    HideRecommendationSerializer,
    LimitSerializer,
    PopularQuerySerializer,
    RecommendationEventBatchResponseSerializer,
    RecommendationEventBatchSerializer,
    RecommendationItemSerializer,
    RecommendationQuerySerializer,
    StatusSerializer,
)
from .services import (
    HiddenRecommendationService,
    RecommendationCacheService,
    RecommendationEventService,
    RecommendationService,
)


def _page_url(request, page_number):
    if page_number is None:
        return None
    params = QueryDict('', mutable=True)
    params.update(request.query_params)
    params['page'] = page_number
    return request.build_absolute_uri(f'{request.path}?{params.urlencode()}')


def _paginated_recommendation_response(request, items, *, user=None, context='', cache_key=None):
    page_size = settings.REST_FRAMEWORK['PAGE_SIZE']
    try:
        page_number = int(request.query_params.get('page', 1))
    except (TypeError, ValueError):
        raise NotFound('Некорректный номер страницы.')
    if page_number < 1:
        raise NotFound('Некорректный номер страницы.')

    cached = RecommendationCacheService.get(cache_key) if cache_key else None
    if cached is not None:
        page_items = cached['items']
        count = cached['count']
    else:
        count = len(items)
        start = (page_number - 1) * page_size
        page_items = items[start:start + page_size]
        if start >= count and count:
            raise NotFound('Страница не найдена.')
        if cache_key:
            RecommendationCacheService.set(
                cache_key,
                {'count': count, 'items': page_items},
                settings.RECOMMENDATION_CACHE_TTLS['personal'],
            )

    hydrated = RecommendationService.hydrate_items(
        page_items,
        user=user,
        context=context,
        limit=page_size,
    )
    data = RecommendationItemSerializer(hydrated, many=True, context={'request': request}).data
    pages = math.ceil(count / page_size) if count else 1
    return Response({
        'count': count,
        'next': _page_url(request, page_number + 1) if page_number < pages else None,
        'previous': _page_url(request, page_number - 1) if page_number > 1 else None,
        'results': data,
    })


class RecommendationListView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Recommendations'],
        summary='Персональные рекомендации или fallback',
        parameters=[
            OpenApiParameter('context', OpenApiTypes.STR, OpenApiParameter.QUERY, default='home'),
            OpenApiParameter('page', OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: RecommendationItemSerializer(many=True), 400: OpenApiResponse(description='Некорректные параметры')},
    )
    def get(self, request):
        query = RecommendationQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        context = query.validated_data['context']
        page = query.validated_data['page']
        if request.user.is_authenticated:
            items = RecommendationService.latest_user_items(request.user, context=context)
            if not items:
                items = RecommendationService.anonymous_items(context=context)
            key = RecommendationCacheService.personal_key(request.user.id, context, page)
            return _paginated_recommendation_response(
                request,
                items,
                user=request.user,
                context=context,
                cache_key=key,
            )
        items = RecommendationService.anonymous_items(context=context)
        return _paginated_recommendation_response(request, items, context=context)


class BoughtTogetherView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Recommendations'],
        summary='Товары, которые покупают вместе',
        parameters=[OpenApiParameter('limit', OpenApiTypes.INT, OpenApiParameter.QUERY, default=12)],
        responses={200: RecommendationItemSerializer(many=True), 404: OpenApiResponse(description='Товар не найден')},
    )
    def get(self, request, slug):
        query = LimitSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        product = get_object_or_404(Product.objects.filter(is_active=True), slug=slug)
        items = RecommendationService.bought_together_items(product, limit=query.validated_data['limit'])
        hydrated = RecommendationService.hydrate_items(items, context=RecommendationContext.BOUGHT_TOGETHER)
        return Response(RecommendationItemSerializer(hydrated, many=True, context={'request': request}).data)


class PopularRecommendationView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Recommendations'],
        summary='Популярные товары',
        parameters=[
            OpenApiParameter('category', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('window', OpenApiTypes.STR, OpenApiParameter.QUERY, enum=['7d', '30d', 'all']),
            OpenApiParameter('page', OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: RecommendationItemSerializer(many=True), 400: OpenApiResponse(description='Некорректные параметры')},
    )
    def get(self, request):
        query = PopularQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        category_value = query.validated_data.get('category')
        category = None
        if category_value:
            lookup = {'pk': category_value} if str(category_value).isdigit() else {'slug': category_value}
            category = get_object_or_404(Category, **lookup)
        window = query.validated_data['window']
        page = query.validated_data['page']
        key = RecommendationCacheService.popular_key(category.id if category else None, window, page)
        cached = RecommendationCacheService.get(key)
        if cached is None:
            ids = RecommendationService.popular_product_ids(
                category=category,
                window=window,
                limit=settings.RECOMMENDATION_MAX_RESULTS,
            )
            items = [
                {'product_id': product_id, 'tracking_id': None, 'reason_code': 'popular', 'is_fallback': True}
                for product_id in ids
            ]
        else:
            items = cached.get('all_items', [])
        response = _paginated_recommendation_response(
            request,
            items,
            context=RecommendationContext.POPULAR,
        )
        if cached is None:
            RecommendationCacheService.set(
                key,
                {'all_items': items},
                settings.RECOMMENDATION_CACHE_TTLS['popular'],
            )
        return response


class CartRecommendationView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Recommendations'],
        summary='Рекомендации для корзины',
        parameters=[
            OpenApiParameter('limit', OpenApiTypes.INT, OpenApiParameter.QUERY, default=12),
            OpenApiParameter('X-Cart-Token', OpenApiTypes.UUID, OpenApiParameter.HEADER, required=False),
        ],
        responses={200: RecommendationItemSerializer(many=True), 400: OpenApiResponse(description='Корзина не найдена')},
    )
    def get(self, request):
        query = LimitSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            cart = get_current_cart(request)
        except CartError as exc:
            detail = exc.messages[0] if getattr(exc, 'messages', None) else str(exc)
            return Response({'detail': detail}, status=status.HTTP_400_BAD_REQUEST)
        version_data = cart.items.aggregate(last=Max('updated_at'), count=Count('id'), quantity=Sum('quantity'))
        version = f'{version_data["last"]}:{version_data["count"]}:{version_data["quantity"]}'
        key = RecommendationCacheService.cart_key(cart.id, version)
        items = RecommendationCacheService.get(key)
        user = request.user if request.user.is_authenticated else None
        if items is None:
            items = RecommendationService.cart_items(cart, user=user, limit=query.validated_data['limit'])
            RecommendationCacheService.set(key, items, settings.RECOMMENDATION_CACHE_TTLS['cart'])
        hydrated = RecommendationService.hydrate_items(
            items,
            user=user,
            context=RecommendationContext.CART,
            limit=query.validated_data['limit'],
        )
        return Response(RecommendationItemSerializer(hydrated, many=True, context={'request': request}).data)


class RecommendationEventView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'recommendation_events'

    @extend_schema(
        tags=['Recommendations / Events'],
        summary='Регистрация frontend-событий',
        request=RecommendationEventBatchSerializer,
        responses={
            200: RecommendationEventBatchResponseSerializer,
            400: OpenApiResponse(description='Ошибка валидации batch'),
            429: OpenApiResponse(description='Превышен лимит запросов'),
        },
        examples=[OpenApiExample(
            'Batch событий',
            value={
                'events': [
                    {
                        'client_event_id': '5b4ce30c-8fb8-47db-a510-a3a2f1c15ae9',
                        'event_type': 'view',
                        'product_id': 42,
                        'context': 'product',
                        'metadata': {'source': 'catalog'},
                    }
                ]
            },
            request_only=True,
        )],
    )
    def post(self, request):
        serializer = RecommendationEventBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = RecommendationEventService.record_batch(request, serializer.validated_data['events'])
        return Response(result)


class HideRecommendationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['Recommendations'],
        summary='Скрыть рекомендацию',
        request=HideRecommendationSerializer,
        responses={
            200: StatusSerializer,
            400: OpenApiResponse(description='Некорректный tracking ID'),
            401: OpenApiResponse(description='Требуется авторизация'),
            404: OpenApiResponse(description='Товар не найден'),
        },
    )
    def post(self, request, product_id):
        serializer = HideRecommendationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = get_object_or_404(Product.objects.filter(is_active=True), pk=product_id)
        HiddenRecommendationService.hide(
            user=request.user,
            product=product,
            context=serializer.validated_data['context'],
            reason=serializer.validated_data.get('reason', ''),
            tracking_id=serializer.validated_data.get('tracking_id'),
        )
        return Response({'status': 'hidden'})

    @extend_schema(
        tags=['Recommendations'],
        summary='Отменить скрытие рекомендации',
        parameters=[OpenApiParameter('context', OpenApiTypes.STR, OpenApiParameter.QUERY, default='home')],
        responses={200: StatusSerializer, 401: OpenApiResponse(description='Требуется авторизация')},
    )
    def delete(self, request, product_id):
        context = request.query_params.get('context', RecommendationContext.HOME)
        valid_contexts = {choice for choice, _ in RecommendationContext.choices}
        if context not in valid_contexts:
            return Response({'context': ['Некорректный контекст.']}, status=status.HTTP_400_BAD_REQUEST)
        product = get_object_or_404(Product, pk=product_id)
        HiddenRecommendationService.unhide(user=request.user, product=product, context=context)
        return Response({'status': 'visible'})
