# Frontend Integration Guide

Полный трёхъязычный справочник системных статусов: [`STATUSES_FRONTEND_GUIDE.md`](STATUSES_FRONTEND_GUIDE.md).

Руководство для подключения готового фронтенда к Django REST API магазина.

## База

Backend:

```text
http://localhost:8000
```

Базовый API prefix:

```text
/api/v1
```

Документация backend:

```text
GET /docs/
GET /api/docs/
GET /api/schema/
GET /api/redoc/
```

Все запросы и ответы JSON, кроме загрузки CSV в импорт товаров.

Обязательные заголовки:

```http
Content-Type: application/json
Accept: application/json
```

Для авторизованных запросов:

```http
Authorization: Bearer <access_token>
```

Для гостевой корзины:

```http
X-Cart-Token: <cart_token>
```

## CORS

Разрешенные frontend origin задаются в `.env`:

```env
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

Если frontend работает на другом порту, добавьте его:

```env
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173
```

## Универсальный API Client

Пример для `fetch`:

```ts
const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1';

export async function apiFetch(path: string, options: RequestInit = {}) {
  const access = localStorage.getItem('access_token');
  const cartToken = localStorage.getItem('cart_token');

  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');

  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  if (access) {
    headers.set('Authorization', `Bearer ${access}`);
  }

  if (cartToken) {
    headers.set('X-Cart-Token', cartToken);
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (response.status === 204) return null;

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw {
      status: response.status,
      data,
      message: data?.detail ?? 'Request failed',
    };
  }

  return data;
}
```

Переменная фронта:

```env
VITE_API_URL=http://localhost:8000/api/v1
```

## Авторизация

### Регистрация

```http
POST /api/v1/auth/register/
```

Request:

```json
{
  "email": "user@example.com",
  "phone": "+77011234567",
  "first_name": "Amina",
  "last_name": "Sadykova",
  "password": "strongpass123",
  "password2": "strongpass123"
}
```

Response `201`:

```json
{
  "user": {
    "id": 1,
    "email": "user@example.com",
    "phone": "+77011234567",
    "first_name": "Amina",
    "last_name": "Sadykova",
    "full_name": "Amina Sadykova",
    "avatar": null,
    "role": "customer",
    "is_verified": false,
    "date_joined": "2026-07-01T10:00:00+06:00"
  },
  "tokens": {
    "refresh": "...",
    "access": "..."
  }
}
```

Сохраняйте:

```ts
localStorage.setItem('access_token', data.tokens.access);
localStorage.setItem('refresh_token', data.tokens.refresh);
```

### Логин

```http
POST /api/v1/auth/login/
```

Request:

```json
{
  "email": "user@example.com",
  "password": "strongpass123"
}
```

Response `200` такой же, как при регистрации.

### Refresh token

```http
POST /api/v1/auth/token/refresh/
```

Request:

```json
{
  "refresh": "..."
}
```

Response обычно:

```json
{
  "access": "...",
  "refresh": "..."
}
```

В backend включена ротация refresh token, поэтому при наличии нового `refresh` перезаписывайте оба токена.

### Logout

```http
POST /api/v1/auth/logout/
Authorization: Bearer <access>
```

Request:

```json
{
  "refresh": "..."
}
```

Response:

```json
{
  "detail": "Выход выполнен"
}
```

После успешного logout удалить токены на фронте.

### Профиль

```http
GET /api/v1/auth/me/
PATCH /api/v1/auth/me/
Authorization: Bearer <access>
```

PATCH request:

```json
{
  "first_name": "Amina",
  "last_name": "Sadykova",
  "phone": "+77011234567"
}
```

### Смена пароля

```http
POST /api/v1/auth/change-password/
Authorization: Bearer <access>
```

Request:

```json
{
  "old_password": "oldpass123",
  "new_password": "newpass123"
}
```

### OTP

Доступные purpose:

```text
email_verify
phone_verify
```

Запросить код:

```http
POST /api/v1/auth/otp/request/
Authorization: Bearer <access>
```

```json
{
  "purpose": "email_verify"
}
```

Проверить код:

```http
POST /api/v1/auth/otp/verify/
Authorization: Bearer <access>
```

```json
{
  "purpose": "email_verify",
  "code": "123456"
}
```

## Адреса

Все адреса требуют авторизацию.

```http
GET /api/v1/auth/addresses/
POST /api/v1/auth/addresses/
GET /api/v1/auth/addresses/{id}/
PATCH /api/v1/auth/addresses/{id}/
DELETE /api/v1/auth/addresses/{id}/
```

Create/PATCH request:

```json
{
  "title": "Дом",
  "country": "Казахстан",
  "city": "Алматы",
  "street": "Абая 10",
  "apartment": "15",
  "postal_code": "050000",
  "is_default": true
}
```

Response:

```json
{
  "id": 1,
  "title": "Дом",
  "country": "Казахстан",
  "city": "Алматы",
  "street": "Абая 10",
  "apartment": "15",
  "postal_code": "050000",
  "is_default": true,
  "created_at": "2026-07-01T10:00:00+06:00",
  "updated_at": "2026-07-01T10:00:00+06:00"
}
```

## Каталог

Публичные endpoint:

```http
GET /api/v1/catalog/categories/
GET /api/v1/catalog/categories/tree/
GET /api/v1/catalog/categories/{slug}/
GET /api/v1/catalog/brands/
GET /api/v1/catalog/brands/{slug}/
GET /api/v1/catalog/colors/
GET /api/v1/catalog/sizes/
GET /api/v1/catalog/products/
GET /api/v1/catalog/products/{slug}/
GET /api/v1/catalog/products/{slug}/similar/
GET /api/v1/catalog/products/{slug}/reviews/
GET /api/v1/catalog/banners/
```

### Справочники

Фильтр активности:

```http
GET /api/v1/catalog/categories/?active=true
GET /api/v1/catalog/brands/?active=true
GET /api/v1/catalog/colors/?active=true
GET /api/v1/catalog/sizes/?active=true
```

Размеры можно фильтровать:

```http
GET /api/v1/catalog/sizes/?size_type=shoes
```

`size_type`:

```text
shoes
clothes
accessories
```

### Список товаров

```http
GET /api/v1/catalog/products/
```

Ответ пагинируется по 24:

```json
{
  "count": 25,
  "next": "http://localhost:8000/api/v1/catalog/products/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Nike Air",
      "slug": "nike-air",
      "sku": "SKU-001",
      "category": {
        "id": 1,
        "name": "Shoes",
        "slug": "shoes"
      },
      "brand": {
        "id": 1,
        "name": "Nike",
        "slug": "nike"
      },
      "brand_name": "Nike",
      "category_name": "Shoes",
      "price": "100.00",
      "old_price": "120.00",
      "discount": 16,
      "discount_percent": 16,
      "is_new": true,
      "is_sale": true,
      "is_active": true,
      "main_image": "http://localhost:8000/media/products/images/main.jpg",
      "min_price": "100.00",
      "in_stock": true,
      "available_colors": [
        {
          "id": 1,
          "name": "Black",
          "slug": "black",
          "hex_code": "#000000",
          "is_active": true
        }
      ],
      "available_sizes": [
        {
          "id": 1,
          "value": "42",
          "size_type": "shoes",
          "sort_order": 1,
          "is_active": true
        }
      ],
      "rating": "0.00",
      "average_rating": 4.5,
      "reviews_count": 10
    }
  ]
}
```

Фильтры:

```text
category=<id|slug>
category_slug=<slug>
subcategory=<id|slug>
subcategory_slug=<slug>
brand=<id|slug>
brand_slug=<slug>
color=<id|slug>
size=<id|value>
price_from=10000
price_to=50000
price_min=10000
price_max=50000
min_price=10000
max_price=50000
material=leather
season=ss|aw|all
in_stock=true|false
is_sale=true|false
has_discount=true|false
is_new=true|false
search=zoom
ordering=price|-price|created_at|-created_at|name|-name
sort=price|-price|created_at|-created_at|name|-name
page=2
```

Пример:

```http
GET /api/v1/catalog/products/?category_slug=shoes&brand=nike&size=42&color=black&price_from=10000&price_to=50000&in_stock=true&ordering=price
```

### Детальная карточка товара

```http
GET /api/v1/catalog/products/{slug}/
```

Ключевые поля:

```json
{
  "id": 1,
  "name": "Nike Air",
  "slug": "nike-air",
  "sku": "SKU-001",
  "category": {
    "id": 1,
    "name": "Shoes",
    "slug": "shoes",
    "parent": null,
    "image": null,
    "description": "",
    "is_active": true,
    "sort_order": 0,
    "seo_title": "",
    "seo_description": "",
    "seo_keywords": ""
  },
  "brand": {
    "id": 1,
    "name": "Nike",
    "slug": "nike",
    "logo": null,
    "is_active": true
  },
  "description": "...",
  "composition": "",
  "material": "leather",
  "season": "all",
  "price": "100.00",
  "old_price": "120.00",
  "discount": 16,
  "discount_percent": 16,
  "is_sale": true,
  "images": [
    {
      "id": 1,
      "image": "http://localhost:8000/media/products/images/main.jpg",
      "alt_text": "Nike Air",
      "alt": "Nike Air",
      "is_main": true,
      "sort_order": 0,
      "created_at": "2026-07-01T10:00:00+06:00",
      "updated_at": "2026-07-01T10:00:00+06:00"
    }
  ],
  "media": [
    {
      "id": 1,
      "media_type": "image",
      "file": "http://localhost:8000/media/products/media/item.jpg",
      "url": "",
      "title": "",
      "alt_text": "",
      "sort_order": 0,
      "is_active": true,
      "created_at": "2026-07-01T10:00:00+06:00",
      "updated_at": "2026-07-01T10:00:00+06:00"
    }
  ],
  "videos": [
    {
      "video": null,
      "youtube_url": "https://youtube.com/..."
    }
  ],
  "variants": [
    {
      "id": 10,
      "color": {
        "id": 1,
        "name": "Black",
        "slug": "black",
        "hex_code": "#000000",
        "is_active": true
      },
      "size": {
        "id": 1,
        "value": "42",
        "size_type": "shoes",
        "sort_order": 1,
        "is_active": true
      },
      "sku": "VAR-001",
      "stock_quantity": 5,
      "variant_price": "100.00",
      "active": true,
      "is_active": true,
      "stock": 5,
      "sku_variant": "VAR-001",
      "extra_price": "0.00",
      "effective_price": "100.00",
      "in_stock": true,
      "is_available": true,
      "final_price": "100.00"
    }
  ],
  "available_sizes": [],
  "available_colors": [],
  "rating": "0.00",
  "average_rating": 4.5,
  "reviews_count": 10,
  "reviews": [
    {
      "id": 1,
      "user_name": "Amina Sadykova",
      "rating": 5,
      "text": "Good",
      "created_at": "2026-07-01T10:00:00+06:00"
    }
  ],
  "is_new": true,
  "is_featured": false,
  "is_active": true,
  "seo_title": "",
  "seo_description": "",
  "meta_title": "",
  "meta_description": "",
  "created_at": "2026-07-01T10:00:00+06:00"
}
```

Для кнопки "Добавить в корзину" нужен `variant.id`, не `product.id`.

### Баннеры

```http
GET /api/v1/catalog/banners/?position=hero
```

`position`:

```text
hero
mid
promo
```

Response:

```json
[
  {
    "id": 1,
    "title": "New Collection",
    "subtitle": "",
    "button_text": "Shop now",
    "image": "http://localhost:8000/media/banners/banner.jpg",
    "image_mobile": null,
    "link": "/catalog",
    "position": "hero",
    "sort_order": 0
  }
]
```

## Wishlist

Требует авторизацию.

```http
GET /api/v1/auth/wishlist/
POST /api/v1/auth/wishlist/toggle/{product_id}/
```

Toggle response:

```json
{
  "status": "added"
}
```

или:

```json
{
  "status": "removed"
}
```

## Корзина

Корзина работает для гостей и авторизованных пользователей.

Для авторизованного пользователя достаточно `Authorization`.

Для гостя первый `POST /cart/items/` создает корзину и возвращает `cart_token`. Его нужно сохранить:

```ts
localStorage.setItem('cart_token', data.cart_token);
```

Все дальнейшие запросы гостевой корзины отправлять с:

```http
X-Cart-Token: <cart_token>
```

### Получить корзину

```http
GET /api/v1/orders/cart/
```

Для гостя без `X-Cart-Token` будет `400`.

Response:

```json
{
  "cart_token": "00000000-0000-0000-0000-000000000000",
  "items": [
    {
      "id": 1,
      "variant_id": 10,
      "product_id": 1,
      "product_name": "Nike Air",
      "product_slug": "nike-air",
      "sku": "VAR-001",
      "size": "42",
      "color": "Black",
      "quantity": 2,
      "unit_price": "120.00",
      "line_total": "240.00",
      "image": "http://localhost:8000/media/products/images/main.jpg",
      "available_stock": 5,
      "in_stock": true
    }
  ],
  "items_count": 1,
  "total_quantity": 2,
  "subtotal": "240.00",
  "promo_code": null,
  "discount_amount": "0.00",
  "total_after_discount": "240.00",
  "total": "240.00"
}
```

### Добавить товар

Основной endpoint:

```http
POST /api/v1/orders/cart/items/
```

Backward-compatible alias:

```http
POST /api/v1/orders/cart/add/
```

Request:

```json
{
  "variant_id": 10,
  "quantity": 1
}
```

Response `200`: полная корзина.

### Изменить количество

```http
PATCH /api/v1/orders/cart/items/{cart_item_id}/
```

Request:

```json
{
  "quantity": 3
}
```

Response `200`: полная корзина.

### Удалить позицию

```http
DELETE /api/v1/orders/cart/items/{cart_item_id}/
```

Alias:

```http
DELETE /api/v1/orders/cart/items/{cart_item_id}/delete/
```

Response `200`: полная корзина.

### Очистить корзину

```http
DELETE /api/v1/orders/cart/clear/
```

Response `200`: пустая корзина.

### Применить промокод к корзине

```http
POST /api/v1/orders/cart/promo-code/apply/
```

Request:

```json
{
  "code": "PROMO10"
}
```

Response `200`: полная корзина плюс:

```json
{
  "message": "Промокод применён."
}
```

### Удалить промокод

```http
DELETE /api/v1/orders/cart/promo-code/
```

Response `200`: полная корзина плюс `message`.

### Объединить гостевую корзину после логина

После логина, если в `localStorage` был гостевой `cart_token`:

```http
POST /api/v1/orders/cart/merge/
Authorization: Bearer <access>
```

Request:

```json
{
  "guest_cart_token": "00000000-0000-0000-0000-000000000000"
}
```

Response `200`: корзина пользователя. После успешного merge гостевой token можно удалить.

## Checkout и заказы

### Способы доставки

```http
GET /api/v1/orders/delivery-methods/
```

Response:

```json
[
  {
    "id": 1,
    "name": "Courier",
    "code": "courier",
    "slug": "courier",
    "delivery_type": "courier",
    "description": "",
    "is_active": true,
    "base_price": "1000.00",
    "price_type": "fixed",
    "free_from_amount": null,
    "sort_order": 0
  }
]
```

`delivery_type`:

```text
courier
pickup
kazakhstan_delivery
```

`price_type`:

```text
fixed
manager_calculation
free
```

Если `price_type=manager_calculation`, backend создаст заказ с `delivery_requires_manager_calculation=true`. Оплату Stripe/Kaspi для такого заказа backend не даст начать, пока доставка не станет финальной.

### Оформить заказ

Основной endpoint:

```http
POST /api/v1/orders/checkout/
```

Alias:

```http
POST /api/v1/orders/
```

Для гостя передайте `cart_token` в body или header `X-Cart-Token`.

Request:

```json
{
  "customer_name": "Customer Name",
  "first_name": "Customer",
  "last_name": "Name",
  "email": "customer@example.com",
  "phone": "+77011234567",
  "city": "Almaty",
  "delivery_address": "Abay 10",
  "delivery_method": "courier",
  "delivery_method_code": "courier",
  "delivery_method_id": 1,
  "comment": "Leave at reception",
  "cart_token": "00000000-0000-0000-0000-000000000000",
  "promo_code": "PROMO10"
}
```

Можно передавать один из вариантов доставки:

```text
delivery_method: "courier"
delivery_method_code: "courier"
delivery_method_id: 1
```

Backend сам считает цены, скидки и остатки. Значения `delivery_price` и `discount_amount` из frontend игнорируются.

Response `201`:

```json
{
  "order_number": "ORD-ABC12345",
  "customer_name": "Customer Name",
  "phone": "+77011234567",
  "email": "customer@example.com",
  "city": "Almaty",
  "delivery_address": "Abay 10",
  "delivery_method": "courier",
  "delivery_method_code": "courier",
  "delivery_method_name": "Courier",
  "items_total": "240.00",
  "delivery_price": "1000.00",
  "delivery_requires_manager_calculation": false,
  "delivery_price_is_final": true,
  "promo_code_text": "PROMO10",
  "discount_amount": "24.00",
  "total_amount": "1216.00",
  "status": "new",
  "payment_status": "unpaid",
  "comment": "Leave at reception",
  "items": [
    {
      "id": 1,
      "product_name": "Nike Air",
      "product_slug": "nike-air",
      "sku": "VAR-001",
      "size_name": "42",
      "color_name": "Black",
      "unit_price": "120.00",
      "quantity": 2,
      "total_price": "240.00"
    }
  ],
  "status_history": [],
  "created_at": "2026-07-01T10:00:00+06:00"
}
```

После успешного checkout корзина очищается.

### История заказов

Требует авторизацию.

```http
GET /api/v1/orders/history/
GET /api/v1/orders/history/?status=new
GET /api/v1/orders/{order_number}/
```

Статусы заказа:

```text
new
waiting_payment
paid
processing
shipped
completed
cancelled
returned
```

Статусы оплаты:

```text
unpaid
waiting
paid
failed
refunded
cancelled
```

## Оплата

### Stripe

```http
POST /api/v1/payments/stripe/create-intent/
```

Для авторизованного заказа нужен `Authorization`.

Для гостевого заказа нужно передать email, совпадающий с email заказа.

Request:

```json
{
  "order_number": "ORD-ABC12345",
  "email": "customer@example.com"
}
```

Response:

```json
{
  "client_secret": "pi_..._secret_..."
}
```

Дальше `client_secret` используется в Stripe Elements на frontend.

### Kaspi

```http
POST /api/v1/payments/kaspi/create/
```

Request:

```json
{
  "order_number": "ORD-ABC12345",
  "email": "customer@example.com"
}
```

Response:

```json
{
  "redirect_url": "https://kaspi.kz/online?OrderId=ORD-ABC12345&Amount=1216&MerchantId=..."
}
```

Frontend должен сделать redirect на `redirect_url`.

Webhook endpoint фронту не нужен:

```http
POST /api/v1/payments/stripe/webhook/
POST /api/v1/payments/kaspi/webhook/
```

## Отзывы

Полный контракт, multipart-примеры и сценарий личного кабинета описаны в
[`REVIEWS_FRONTEND_GUIDE.md`](REVIEWS_FRONTEND_GUIDE.md).

Публично:

```http
GET /api/v1/catalog/products/{slug}/reviews/
```

Создание требует авторизацию и завершенный/валидный заказ по backend-логике:

```http
POST /api/v1/catalog/reviews/
Authorization: Bearer <access>
```

Request:

```json
{
  "product_id": 1,
  "order_number": "ORD-ABC12345",
  "rating": 5,
  "text": "Good"
}
```

Можно использовать `product_slug` вместо `product_id`, а также `order_id` вместо `order_number`.

Response `201`:

```json
{
  "id": 1,
  "product": {
    "id": 1,
    "slug": "nike-air",
    "name_ru": "Nike Air",
    "name_kz": "",
    "name_en": "Nike Air"
  },
  "order": {
    "id": 1,
    "order_number": "ORD-ABC12345"
  },
  "user_name": "Amina Sadykova",
  "rating": 5,
  "text": "Good",
  "status": "pending",
  "status_labels": {
    "ru": "На модерации",
    "kz": "Модерацияда",
    "en": "Pending moderation"
  },
  "media": [],
  "is_verified_purchase": true,
  "moderation_comment": "",
  "moderated_at": null,
  "created_at": "2026-07-01T10:00:00+06:00",
  "updated_at": "2026-07-01T10:00:00+06:00"
}
```

Фото и видео передаются как `multipart/form-data` повторяющимся полем `media`.
Все отзывы текущего пользователя, включая ожидающие модерации и отклонённые:

```http
GET /api/v1/catalog/reviews/mine/
Authorization: Bearer <access>
```

## Промокод без корзины

Требует авторизацию.

```http
POST /api/v1/catalog/promo/check/
Authorization: Bearer <access>
```

Request:

```json
{
  "code": "PROMO10",
  "order_amount": "240.00"
}
```

Response:

```json
{
  "code": "PROMO10",
  "discount_type": "percent",
  "discount_value": "10.00",
  "discount_amount": "24.00",
  "final_amount": "216.00"
}
```

Для реальной корзины лучше использовать `/orders/cart/promo-code/apply/`, чтобы backend сохранил промокод в корзине.

## CMS страницы

```http
GET /api/v1/cms/pages/
GET /api/v1/cms/pages/{slug}/
```

List response:

```json
[
  {
    "id": 1,
    "slug": "delivery",
    "title": "Delivery"
  }
]
```

Detail response:

```json
{
  "id": 1,
  "slug": "delivery",
  "title": "Delivery",
  "content": "<p>...</p>",
  "seo_title": "",
  "seo_description": ""
}
```

## Уведомления

Требуют авторизацию.

```http
GET /api/v1/notifications/
GET /api/v1/notifications/?is_read=false
GET /api/v1/notifications/?event_type=payment_error
POST /api/v1/notifications/{id}/mark-read/
POST /api/v1/notifications/mark-all-read/
POST /api/v1/notifications/read-all/
```

Response:

```json
[
  {
    "id": 1,
    "title": "Payment failed",
    "message": "...",
    "event_type": "payment_error",
    "is_read": false,
    "created_at": "2026-07-01T10:00:00+06:00"
  }
]
```

## Manager/Admin endpoints

Эти endpoint нужны для админки/оператора, не для обычной витрины. Требуют роль `manager` или `admin`.

Остатки:

```http
GET /api/v1/catalog/stock/
POST /api/v1/catalog/stock/adjust/
GET /api/v1/catalog/stock/movements/
```

Корректировка остатка:

```json
{
  "variant_id": 10,
  "new_quantity": 7,
  "comment": "Manual recount"
}
```

Импорт товаров CSV:

```http
GET /api/v1/catalog/imports/products/
POST /api/v1/catalog/imports/products/
GET /api/v1/catalog/imports/products/{id}/
GET /api/v1/catalog/imports/products/{id}/errors/
GET /api/v1/catalog/imports/products/{id}/error-report/
```

Upload request должен быть `multipart/form-data`:

```text
file=<products.csv>
```

## Ошибки

Типовые форматы:

```json
{
  "detail": "Ошибка"
}
```

или ошибки полей:

```json
{
  "email": ["user with this email already exists."],
  "password2": ["Пароли не совпадают"]
}
```

На frontend стоит обрабатывать:

```text
400 validation/business error
401 access token expired or missing
403 no permission
404 not found
429 OTP rate limit
500 backend error
```

Для `401` выполнить refresh:

1. Отправить `POST /api/v1/auth/token/refresh/` с refresh token.
2. Сохранить новый access/refresh.
3. Повторить исходный запрос один раз.
4. Если refresh не прошел, разлогинить пользователя.

## Рекомендуемый порядок подключения фронта

1. Настроить `VITE_API_URL` и CORS.
2. Подключить `apiFetch` с JWT, refresh и `X-Cart-Token`.
3. Главная: `banners`, `categories/tree`, `products?is_new=true`, `products?is_sale=true`.
4. Каталог: `categories/tree`, `brands`, `colors`, `sizes`, `products` с фильтрами.
5. Карточка товара: `products/{slug}`, выбор `variant.id`, добавление в корзину.
6. Корзина: `cart`, `cart/items`, `cart/promo-code/apply`, `cart/clear`.
7. Auth: register/login/logout/me, после login делать `cart/merge`.
8. Checkout: `delivery-methods`, `checkout`, затем Stripe/Kaspi при необходимости.
9. Кабинет: профиль, адреса, история заказов, wishlist, уведомления.

## Минимальный сценарий покупки

```text
GET  /api/v1/catalog/products/{slug}/
POST /api/v1/orders/cart/items/             { variant_id, quantity }
GET  /api/v1/orders/cart/                   with X-Cart-Token for guest
GET  /api/v1/orders/delivery-methods/
POST /api/v1/orders/checkout/               { customer_name, email, phone, city, delivery_address, delivery_method, cart_token }
POST /api/v1/payments/stripe/create-intent/ { order_number, email }
```

## Важные нюансы

- В корзину добавляется `variant_id`, а не `product_id`.
- Цены, скидки, доставку и остатки считает backend.
- Гостевой `cart_token` обязательно хранить до checkout или login.
- После login вызывайте `/orders/cart/merge/`, если была гостевая корзина.
- `GET /orders/cart/` для гостя без token вернет `400`.
- `checkout` для гостя без `cart_token` вернет `400`.
- Если доставка требует расчета менеджером, платежные endpoint вернут `400` до финализации доставки.
- Список товаров пагинируется: брать данные из `results`.
- Медиа URL могут быть абсолютными или относительными в зависимости от serializer/storage; frontend должен уметь нормализовать относительный путь через backend origin.
