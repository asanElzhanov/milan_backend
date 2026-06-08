# Fashion Shop — Django REST API

Бэкенд интернет-магазина женской обуви и аксессуаров.  
Django 5 + DRF + PostgreSQL + Redis + Celery.

## Структура проекта

```
shop_backend/
├── config/
│   ├── settings.py          # Все настройки
│   ├── urls.py              # Главный роутер
│   └── celery.py            # Celery конфиг
│
├── apps/
│   ├── accounts/            # Пользователи, адреса, избранное, OTP
│   ├── catalog/             # Категории, товары, отзывы, баннеры, промокоды
│   ├── orders/              # Корзина + заказы
│   ├── payments/            # Stripe, Kaspi Pay
│   └── notifications/       # Email-уведомления (Celery tasks)
│
├── requirements.txt
└── .env.example
```

## API Endpoints

### Auth — `/api/v1/auth/`
| Метод | URL | Описание |
|-------|-----|----------|
| POST | `register/` | Регистрация |
| POST | `login/` | Вход → JWT tokens |
| POST | `logout/` | Выход (blacklist) |
| POST | `token/refresh/` | Обновить access token |
| GET/PATCH | `me/` | Профиль |
| POST | `change-password/` | Смена пароля |
| GET/POST | `addresses/` | Адреса доставки |
| GET/PATCH/DELETE | `addresses/<pk>/` | Один адрес |
| GET | `wishlist/` | Избранное |
| POST | `wishlist/toggle/<id>/` | Добавить/убрать |
| POST | `otp/request/` | Запросить OTP |
| POST | `otp/verify/` | Подтвердить OTP |

### Catalog — `/api/v1/catalog/`
| Метод | URL | Описание |
|-------|-----|----------|
| GET | `categories/` | Дерево категорий |
| GET | `brands/` | Все бренды |
| GET | `products/` | Список с фильтрами |
| GET | `products/<slug>/` | Карточка товара |
| GET | `products/<slug>/similar/` | Похожие товары |
| GET/POST | `products/<slug>/reviews/` | Отзывы |
| GET | `banners/?position=hero` | Баннеры |
| POST | `promo/check/` | Проверить промокод |

**Параметры фильтрации** `GET /products/`:
- `category`, `brand`, `color`, `size`
- `price_min`, `price_max`
- `material`, `season`
- `in_stock=true`, `has_discount=true`, `is_new=true`
- `search=текст`
- `ordering=price | -price | created_at | -rating | orders_count`

### Orders — `/api/v1/orders/`
| Метод | URL | Описание |
|-------|-----|----------|
| GET | `cart/` | Текущая корзина |
| POST | `cart/add/` | Добавить товар |
| PATCH | `cart/items/<pk>/` | Изменить количество |
| DELETE | `cart/items/<pk>/delete/` | Удалить позицию |
| DELETE | `cart/clear/` | Очистить корзину |
| POST | `` (root) | Оформить заказ |
| GET | `history/` | История заказов |
| GET | `<number>/` | Статус заказа |

### Payments — `/api/v1/payments/`
| Метод | URL | Описание |
|-------|-----|----------|
| POST | `stripe/create-intent/` | Создать PaymentIntent |
| POST | `stripe/webhook/` | Webhook от Stripe |
| POST | `kaspi/create/` | Ссылка Kaspi Pay |
| POST | `kaspi/webhook/` | Callback от Kaspi |

### Документация
- Swagger UI: `/api/docs/`
- Redoc: `/api/redoc/`

---

## Установка

```bash
# 1. Зависимости
pip install -r requirements.txt

# 2. Переменные окружения
cp .env.example .env
# Отредактируй .env

# 3. База данных
python manage.py migrate

# 4. Суперпользователь
python manage.py createsuperuser

# 5. Dev сервер
python manage.py runserver

# 6. Celery (в отдельном терминале)
celery -A config worker -l info

# 7. Celery Beat (периодические задачи)
celery -A config beat -l info
```

## Docker Compose

Compose поднимает весь backend stack: Django/Gunicorn, PostgreSQL, Redis, Celery worker,
Celery Beat и MinIO для пользовательских файлов.

```bash
docker compose up -d
```

Если порт `8000` занят:

```bash
APP_PORT=8001 docker compose up -d
```

MinIO:
- API: `http://localhost:9000`
- Console: `http://localhost:9001`
- bucket: `shop-media`
- логин/пароль по умолчанию: `minioadmin` / `minioadmin`

Если порт `9000` занят, можно поднять MinIO на других портах:

```bash
APP_PORT=8001 MINIO_API_PORT=9002 MINIO_CONSOLE_PORT=9003 MINIO_PUBLIC_DOMAIN=localhost:9002/shop-media docker compose up -d
```

Static files остаются локальными и отдаются через Whitenoise, а media uploads
(`ImageField`/`FileField`) сохраняются в MinIO при `USE_S3=True`.

## Модели

```
User ──────────────── Address (many)
     └──────────────── Wishlist → Product
     └──────────────── Order (many)
     └──────────────── Review (many)

Category (MPTT tree)
Brand
Product ──────────── ProductImage (many)
        ──────────── ProductVideo (many)
        ──────────── ProductVariant (color + size + stock)
        ──────────── Review (many)

Cart ─────────────── CartItem → ProductVariant
Order ────────────── OrderItem (snapshot)
      ────────────── Payment
      ────────────── OrderStatusHistory
```
