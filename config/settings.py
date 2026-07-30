from pathlib import Path
from decouple import config
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='change-me-in-production')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*').split(',')

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'mptt',
    'parler',
    'phonenumber_field',
    'storages',
]

LOCAL_APPS = [
    'apps.accounts',
    'apps.catalog',
    'apps.cms',
    'apps.orders',
    'apps.payments',
    'apps.notifications',
    'apps.recommendations',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.recommendations.middleware.RecommendationAnonymousActorMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# --- Database ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='shop_db'),
        'USER': config('DB_USER', default='shop_user'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

# --- Cache / Redis ---
REDIS_URL = config('REDIS_URL', default='redis://127.0.0.1:6379/0')
CACHE_REDIS_URL = config('CACHE_REDIS_URL', default=REDIS_URL)
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': CACHE_REDIS_URL,
        'KEY_PREFIX': config('CACHE_KEY_PREFIX', default='shop'),
        'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'},
    }
}

# --- Celery ---
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default=REDIS_URL)
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default=REDIS_URL)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True

# --- Orders / payment timeout ---
# Через сколько минут неоплаченный заказ автоматически отменяется.
ORDER_PAYMENT_TIMEOUT_MINUTES = config('ORDER_PAYMENT_TIMEOUT_MINUTES', default=30, cast=int)
# Как часто (в минутах) Celery-beat проверяет заказы на истечение времени оплаты.
ORDER_EXPIRY_CHECK_MINUTES = config('ORDER_EXPIRY_CHECK_MINUTES', default=5, cast=int)

# --- Auth ---
AUTH_USER_MODEL = 'accounts.User'

# --- JWT ---
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# --- OTP verification ---
OTP_CODE_TTL_MINUTES = config('OTP_CODE_TTL_MINUTES', default=10, cast=int)
OTP_RESEND_COOLDOWN_SECONDS = config('OTP_RESEND_COOLDOWN_SECONDS', default=60, cast=int)
OTP_MAX_ATTEMPTS_PER_HOUR = config('OTP_MAX_ATTEMPTS_PER_HOUR', default=5, cast=int)

# --- DRF ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 24,
    'DEFAULT_THROTTLE_RATES': {
        'recommendation_events': config('RECOMMENDATION_EVENTS_RATE', default='60/min'),
    },
}

# --- Review media ---
REVIEW_MAX_MEDIA_FILES = config('REVIEW_MAX_MEDIA_FILES', default=5, cast=int)
REVIEW_MAX_IMAGE_SIZE = config('REVIEW_MAX_IMAGE_SIZE_MB', default=10, cast=int) * 1024 * 1024
REVIEW_MAX_VIDEO_SIZE = config('REVIEW_MAX_VIDEO_SIZE_MB', default=50, cast=int) * 1024 * 1024

# --- Recommendations ---
RECOMMENDATIONS_ENABLED = config('RECOMMENDATIONS_ENABLED', default=True, cast=bool)
RECOMMENDATION_ALGORITHM_VERSION = config('RECOMMENDATION_ALGORITHM_VERSION', default='v1')
RECOMMENDATION_EVENT_WEIGHTS = {
    'view': 1.0,
    'search': 0.0,
    'search_click': 2.0,
    'favorite_add': 4.0,
    'favorite_remove': -4.0,
    'cart_add': 5.0,
    'cart_remove': -4.0,
    'order_created': 2.0,
    'purchase': 10.0,
    'order_cancel': -10.0,
    'return': -12.0,
    'rating': 0.0,
    'recommendation_impression': 0.0,
    'recommendation_click': 2.0,
    'recommendation_hide': -10.0,
}
RECOMMENDATION_RATING_WEIGHTS = {1: -8.0, 2: -4.0, 3: 0.0, 4: 4.0, 5: 8.0}
RECOMMENDATION_EVENT_HALF_LIFE_DAYS = {
    'view': 7,
    'search': 7,
    'search_click': 14,
    'favorite_add': 90,
    'favorite_remove': 90,
    'cart_add': 30,
    'cart_remove': 30,
    'order_created': 30,
    'purchase': 180,
    'order_cancel': 180,
    'return': 365,
    'rating': 365,
    'recommendation_impression': 14,
    'recommendation_click': 14,
    'recommendation_hide': 180,
}
RECOMMENDATION_MAX_CANDIDATES = config('RECOMMENDATION_MAX_CANDIDATES', default=300, cast=int)
RECOMMENDATION_SEED_PRODUCTS = config('RECOMMENDATION_SEED_PRODUCTS', default=30, cast=int)
RECOMMENDATION_MAX_PER_CATEGORY = config('RECOMMENDATION_MAX_PER_CATEGORY', default=4, cast=int)
RECOMMENDATION_MAX_RESULTS = config('RECOMMENDATION_MAX_RESULTS', default=100, cast=int)
RECOMMENDATION_RELATIONS_PER_PRODUCT = config('RECOMMENDATION_RELATIONS_PER_PRODUCT', default=100, cast=int)
RECOMMENDATION_CO_PURCHASE_MIN_SUPPORT = config('RECOMMENDATION_CO_PURCHASE_MIN_SUPPORT', default=2, cast=int)
RECOMMENDATION_RECENT_PURCHASE_DAYS = config('RECOMMENDATION_RECENT_PURCHASE_DAYS', default=30, cast=int)
RECOMMENDATION_EVENT_BATCH_LIMIT = config('RECOMMENDATION_EVENT_BATCH_LIMIT', default=20, cast=int)
RECOMMENDATION_VIEW_DEDUP_MINUTES = config('RECOMMENDATION_VIEW_DEDUP_MINUTES', default=30, cast=int)
RECOMMENDATION_MAX_VIEWS_PER_DAY = config('RECOMMENDATION_MAX_VIEWS_PER_DAY', default=3, cast=int)
RECOMMENDATION_EVENT_RETENTION_DAYS = config('RECOMMENDATION_EVENT_RETENTION_DAYS', default=395, cast=int)
RECOMMENDATION_SEARCH_RETENTION_DAYS = config('RECOMMENDATION_SEARCH_RETENTION_DAYS', default=60, cast=int)
RECOMMENDATION_GENERATION_RETENTION_DAYS = config('RECOMMENDATION_GENERATION_RETENTION_DAYS', default=30, cast=int)
RECOMMENDATION_MAX_GENERATIONS = config('RECOMMENDATION_MAX_GENERATIONS', default=5, cast=int)
RECOMMENDATION_GENERATION_EXPIRY_HOURS = config('RECOMMENDATION_GENERATION_EXPIRY_HOURS', default=24, cast=int)
RECOMMENDATION_SEARCH_QUERY_ENABLED = config('RECOMMENDATION_SEARCH_QUERY_ENABLED', default=False, cast=bool)
RECOMMENDATION_TASK_BATCH_SIZE = config('RECOMMENDATION_TASK_BATCH_SIZE', default=500, cast=int)
RECOMMENDATION_ANONYMOUS_COOKIE_NAME = config('RECOMMENDATION_ANONYMOUS_COOKIE_NAME', default='reco_actor')
RECOMMENDATION_ANONYMOUS_COOKIE_AGE = config('RECOMMENDATION_ANONYMOUS_COOKIE_AGE', default=31536000, cast=int)
RECOMMENDATION_CACHE_TTLS = {
    'personal': config('RECOMMENDATION_CACHE_PERSONAL_TTL', default=1800, cast=int),
    'popular': config('RECOMMENDATION_CACHE_POPULAR_TTL', default=900, cast=int),
    'similar': config('RECOMMENDATION_CACHE_SIMILAR_TTL', default=14400, cast=int),
    'bought_together': config('RECOMMENDATION_CACHE_BOUGHT_TTL', default=43200, cast=int),
    'cart': config('RECOMMENDATION_CACHE_CART_TTL', default=300, cast=int),
}

CELERY_BEAT_SCHEDULE = {
    'recommendations-popularity': {
        'task': 'recommendations.aggregate_product_popularity',
        'schedule': timedelta(minutes=config('RECOMMENDATION_POPULARITY_MINUTES', default=30, cast=int)),
    },
    'recommendations-preferences': {
        'task': 'recommendations.rebuild_user_category_preferences',
        'schedule': timedelta(hours=config('RECOMMENDATION_PREFERENCES_HOURS', default=1, cast=int)),
    },
    'recommendations-content-relations': {
        'task': 'recommendations.rebuild_content_relations',
        'schedule': timedelta(hours=config('RECOMMENDATION_CONTENT_HOURS', default=24, cast=int)),
    },
    'recommendations-co-purchase': {
        'task': 'recommendations.rebuild_co_purchase_relations',
        'schedule': timedelta(hours=config('RECOMMENDATION_CO_PURCHASE_HOURS', default=24, cast=int)),
    },
    'recommendations-personal': {
        'task': 'recommendations.generate_user_recommendations',
        'schedule': timedelta(hours=config('RECOMMENDATION_GENERATION_HOURS', default=6, cast=int)),
    },
    'recommendations-cleanup': {
        'task': 'recommendations.cleanup_recommendation_data',
        'schedule': timedelta(hours=config('RECOMMENDATION_CLEANUP_HOURS', default=24, cast=int)),
    },
    'recommendations-reconcile': {
        'task': 'recommendations.reconcile_recommendation_aggregates',
        'schedule': timedelta(hours=config('RECOMMENDATION_RECONCILE_HOURS', default=24, cast=int)),
    },
}

# --- Spectacular (Swagger) ---
SPECTACULAR_SETTINGS = {
    'TITLE': 'Fashion Shop API',
    'DESCRIPTION': 'Premium women\'s shoes & accessories store',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# --- CORS ---
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000'
).split(',')
CORS_ALLOW_CREDENTIALS = True

# --- Internationalization ---
LANGUAGE_CODE = 'ru'
LANGUAGES = [
    ('ru', 'Русский'),
    ('kk', 'Қазақша'),
    ('en', 'English'),
]
TIME_ZONE = 'Asia/Almaty'
USE_I18N = True
USE_TZ = True

LOCALE_PATHS = [BASE_DIR / 'locale']

# --- Static & Media ---
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# --- S3 / MinIO media storage ---
USE_S3 = config('USE_S3', default=False, cast=bool)
if USE_S3:
    AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='us-east-1')
    AWS_S3_ENDPOINT_URL = config('AWS_S3_ENDPOINT_URL', default=None)
    AWS_S3_CUSTOM_DOMAIN = config(
        'AWS_S3_CUSTOM_DOMAIN',
        default=f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com',
    )
    AWS_S3_URL_PROTOCOL = config('AWS_S3_URL_PROTOCOL', default='https:')
    AWS_S3_ADDRESSING_STYLE = config('AWS_S3_ADDRESSING_STYLE', default='path')
    AWS_S3_SIGNATURE_VERSION = config('AWS_S3_SIGNATURE_VERSION', default='s3v4')
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = config('AWS_QUERYSTRING_AUTH', default=False, cast=bool)
    AWS_S3_FILE_OVERWRITE = False

    STORAGES['default'] = {
        'BACKEND': 'config.storage_backends.MediaStorage',
    }
    MEDIA_URL = f'{AWS_S3_URL_PROTOCOL}//{AWS_S3_CUSTOM_DOMAIN}/media/'

# --- Email ---
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@fashionshop.kz')

# --- Payments (FreedomPay) ---
FREEDOMPAY_MERCHANT_ID = config('FREEDOMPAY_MERCHANT_ID', default='')
FREEDOMPAY_SECRET_KEY = config('FREEDOMPAY_SECRET_KEY', default='')
FREEDOMPAY_API_URL = config('FREEDOMPAY_API_URL', default='https://api.freedompay.kz')
FREEDOMPAY_TESTING_MODE = config('FREEDOMPAY_TESTING_MODE', default=1, cast=int)

# Публичный URL бэкенда (должен быть доступен FreedomPay для result_url callback)
BACKEND_PUBLIC_URL = config('BACKEND_PUBLIC_URL', default='http://localhost:8000')
# URL фронтенда для построения success_url / fail_url
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:3000')

# --- Phone numbers ---
PHONENUMBER_DEFAULT_REGION = 'KZ'

# --- Notifications ---
LOW_STOCK_THRESHOLD = config('LOW_STOCK_THRESHOLD', default=3, cast=int)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
