# Статические страницы: интеграция фронтенда

Базовый URL CMS API: `/api/v1/cms/`.

API публичный и read-only: токен авторизации для чтения не нужен. Редактирование
страниц и блоков выполняется через Django Admin: `/django-admin/cms/staticpage/`.

## Стандартные страницы

Миграция создаёт записи для пяти страниц, не перезаписывая уже существующие:

| Страница | slug | Endpoint |
|---|---|---|
| О компании | `about` | `/api/v1/cms/pages/about/` |
| Доставка | `delivery` | `/api/v1/cms/pages/delivery/` |
| Оплата | `payment` | `/api/v1/cms/pages/payment/` |
| FAQ | `faq` | `/api/v1/cms/pages/faq/` |
| Контакты | `contacts` | `/api/v1/cms/pages/contacts/` |

Если страница выключена в админке (`is_active = false`), её нет в списке, а
детальный endpoint возвращает `404`.

## Endpoints

### Список страниц

```http
GET /api/v1/cms/pages/
```

Ответ пагинируется стандартной пагинацией DRF:

```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "slug": "about",
      "title_ru": "О компании",
      "title_kz": "Компания туралы",
      "title_en": "About company"
    }
  ]
}
```

### Детальная страница с блоками

```http
GET /api/v1/cms/pages/{slug}/
```

Пример ответа:

```json
{
  "id": 1,
  "slug": "delivery",
  "title_ru": "Доставка",
  "title_kz": "Жеткізу",
  "title_en": "Delivery",
  "content_ru": "Необязательный вводный текст страницы",
  "content_kz": "",
  "content_en": "",
  "seo_title": "Доставка",
  "seo_description": "Условия доставки",
  "blocks": [
    {
      "id": 10,
      "title_ru": "Доставка по городу",
      "title_kz": "Қала бойынша жеткізу",
      "title_en": "City delivery",
      "content_ru": "Основной текст блока",
      "content_kz": "Блоктың негізгі мәтіні",
      "content_en": "Main block text",
      "sort_order": 10
    }
  ]
}
```

В `blocks` попадают только активные блоки. Они уже отсортированы по
`sort_order` по возрастанию; при одинаковом значении порядок стабилизируется по
`id`.

## Типы для TypeScript

```ts
type CmsLanguage = 'ru' | 'kk' | 'en';
type KnownStaticPageSlug = 'about' | 'delivery' | 'payment' | 'faq' | 'contacts';

interface StaticPageBlock {
  id: number;
  title_ru: string;
  title_kz: string;
  title_en: string;
  content_ru: string;
  content_kz: string;
  content_en: string;
  sort_order: number;
}

interface StaticPage {
  id: number;
  slug: string; // KnownStaticPageSlug для пяти стандартных страниц
  title_ru: string;
  title_kz: string;
  title_en: string;
  content_ru: string;
  content_kz: string;
  content_en: string;
  seo_title: string;
  seo_description: string;
  blocks: StaticPageBlock[];
}
```

В настройках Django код казахского языка — `kk`, но исторические имена полей
API используют суффикс `_kz`. На фронте для языка `kk` нужно читать поля `_kz`.
Если перевод пустой, рекомендуется fallback: выбранный язык → русский.

Текст возвращается как строка. Для обычного текста с переносами строк безопасно
использовать CSS `white-space: pre-line`. Если редакторы вводят HTML, перед
рендерингом через `dangerouslySetInnerHTML` его необходимо санитизировать.

## Работа в Django Admin

1. Выполнить `python manage.py migrate`.
2. Открыть `/django-admin/cms/staticpage/`.
3. Выбрать нужную страницу.
4. Заполнить название и при необходимости вводный текст на RU/KZ/EN.
5. В секции блоков добавить заголовок и основной текст на RU/KZ/EN.
6. Указать `sort_order`: например, `10`, `20`, `30`.
7. Сохранить страницу.

Блок можно временно скрыть через `is_active`, не удаляя его из админки.
