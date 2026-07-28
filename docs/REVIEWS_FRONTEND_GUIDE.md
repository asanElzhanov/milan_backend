# Отзывы: гайд для frontend

## Базовые правила

Базовый URL локального API:

```text
http://localhost:8000/api/v1
```

Оставить отзыв может только авторизованный пользователь, если:

- заказ принадлежит ему;
- статус заказа — `paid` или `completed`;
- товар присутствует в заказе;
- для этого товара в рамках этого заказа ещё нет отзыва.

Новый отзыв создаётся со статусом `pending`. В публичной выдаче он появится
только после перехода в `published`.

Поддерживаемые вложения:

- изображения: `jpg`, `jpeg`, `png`, `webp`, `gif`, `avif`, до 10 МБ;
- видео: `mp4`, `webm`, `mov`, `m4v`, `ogv`, до 50 МБ;
- максимум 5 файлов на отзыв.

Лимиты на backend настраиваются через `REVIEW_MAX_MEDIA_FILES`,
`REVIEW_MAX_IMAGE_SIZE_MB` и `REVIEW_MAX_VIDEO_SIZE_MB`.

## Типы данных

```ts
export type ReviewStatus = "pending" | "published" | "rejected" | "hidden";

export type ReviewMedia = {
  id: number;
  url: string;
  media_type: "image" | "video";
};

export type PublicReview = {
  id: number;
  user_name: string;
  rating: number;
  text: string;
  media: ReviewMedia[];
  is_verified_purchase: boolean;
  created_at: string;
};

export type MyReview = {
  id: number;
  product: {
    id: number;
    slug: string;
    name_ru: string;
    name_kz: string;
    name_en: string;
  };
  order: {
    id: number;
    order_number: string;
  };
  user_name: string;
  rating: number;
  text: string;
  status: ReviewStatus;
  media: ReviewMedia[];
  is_verified_purchase: boolean;
  moderation_comment: string;
  moderated_at: string | null;
  created_at: string;
  updated_at: string;
};

export type Page<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
```

## 1. Получить публичные отзывы товара

Авторизация не требуется.

```http
GET /api/v1/catalog/products/{product_slug}/reviews/?page=1
```

Ответ `200`:

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 31,
      "user_name": "Амина Садыкова",
      "rating": 5,
      "text": "Отличные кроссовки",
      "media": [
        {
          "id": 52,
          "url": "http://localhost:8000/media/reviews/2026/07/29/photo.jpg",
          "media_type": "image"
        },
        {
          "id": 53,
          "url": "http://localhost:8000/media/reviews/2026/07/29/video.mp4",
          "media_type": "video"
        }
      ],
      "is_verified_purchase": true,
      "created_at": "2026-07-29T12:00:00+05:00"
    }
  ]
}
```

```ts
export async function getProductReviews(slug: string, page = 1) {
  const response = await fetch(
    `${API_URL}/catalog/products/${encodeURIComponent(slug)}/reviews/?page=${page}`,
  );

  if (!response.ok) throw await apiError(response);
  return response.json() as Promise<Page<PublicReview>>;
}
```

`GET /api/v1/catalog/products/{slug}/` также содержит `average_rating`,
`reviews_count` и первые пять опубликованных отзывов в поле `reviews`.
Для пагинации полного списка используется отдельный endpoint выше.

## 2. Создать отзыв без файлов

```http
POST /api/v1/catalog/reviews/
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "product_slug": "nike-air",
  "order_number": "ORD-ABC12345",
  "rating": 5,
  "text": "Отличные кроссовки"
}
```

Вместо `product_slug` можно передать `product_id`, а вместо `order_number` —
`order_id`. Не следует одновременно передавать ID и slug/number одного объекта.

```ts
export async function createTextReview(
  accessToken: string,
  payload: {
    productSlug: string;
    orderNumber: string;
    rating: number;
    text: string;
  },
) {
  const response = await fetch(`${API_URL}/catalog/reviews/`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      product_slug: payload.productSlug,
      order_number: payload.orderNumber,
      rating: payload.rating,
      text: payload.text,
    }),
  });

  if (!response.ok) throw await apiError(response);
  return response.json() as Promise<MyReview>;
}
```

## 3. Создать отзыв с фотографиями или видео

Файлы передаются повторяющимся полем `media`.

```http
POST /api/v1/catalog/reviews/
Authorization: Bearer <access_token>
Content-Type: multipart/form-data; boundary=...
```

```text
product_slug=nike-air
order_number=ORD-ABC12345
rating=5
text=Отличные кроссовки
media=<photo.jpg>
media=<unboxing.mp4>
```

При использовании `FormData` нельзя вручную устанавливать `Content-Type`:
браузер сам добавит корректный `boundary`.

```ts
export async function createReviewWithMedia(
  accessToken: string,
  payload: {
    productSlug: string;
    orderNumber: string;
    rating: number;
    text: string;
    files: File[];
  },
) {
  const formData = new FormData();
  formData.append("product_slug", payload.productSlug);
  formData.append("order_number", payload.orderNumber);
  formData.append("rating", String(payload.rating));
  formData.append("text", payload.text);

  for (const file of payload.files) {
    formData.append("media", file);
  }

  const response = await fetch(`${API_URL}/catalog/reviews/`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
    body: formData,
  });

  if (!response.ok) throw await apiError(response);
  return response.json() as Promise<MyReview>;
}
```

Ответ `201` для JSON и multipart одинаковый:

```json
{
  "id": 31,
  "product": {
    "id": 8,
    "slug": "nike-air",
    "name_ru": "Nike Air",
    "name_kz": "",
    "name_en": "Nike Air"
  },
  "order": {
    "id": 17,
    "order_number": "ORD-ABC12345"
  },
  "user_name": "Амина Садыкова",
  "rating": 5,
  "text": "Отличные кроссовки",
  "status": "pending",
  "media": [
    {
      "id": 52,
      "url": "http://localhost:8000/media/reviews/2026/07/29/photo.jpg",
      "media_type": "image"
    }
  ],
  "is_verified_purchase": true,
  "moderation_comment": "",
  "moderated_at": null,
  "created_at": "2026-07-29T12:00:00+05:00",
  "updated_at": "2026-07-29T12:00:00+05:00"
}
```

После `201` интерфейс должен показать сообщение «Отзыв отправлен на
модерацию». Не нужно сразу добавлять его в публичный список.

## 4. Получить все свои отзывы

Endpoint предназначен для личного кабинета и возвращает отзывы во всех
статусах: `pending`, `published`, `rejected`, `hidden`.

```http
GET /api/v1/catalog/reviews/mine/?page=1
Authorization: Bearer <access_token>
```

Ответ `200` имеет формат `Page<MyReview>`:

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 31,
      "product": {
        "id": 8,
        "slug": "nike-air",
        "name_ru": "Nike Air",
        "name_kz": "",
        "name_en": "Nike Air"
      },
      "order": {
        "id": 17,
        "order_number": "ORD-ABC12345"
      },
      "user_name": "Амина Садыкова",
      "rating": 5,
      "text": "Отличные кроссовки",
      "status": "pending",
      "media": [],
      "is_verified_purchase": true,
      "moderation_comment": "",
      "moderated_at": null,
      "created_at": "2026-07-29T12:00:00+05:00",
      "updated_at": "2026-07-29T12:00:00+05:00"
    }
  ]
}
```

```ts
export async function getMyReviews(accessToken: string, page = 1) {
  const response = await fetch(`${API_URL}/catalog/reviews/mine/?page=${page}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (!response.ok) throw await apiError(response);
  return response.json() as Promise<Page<MyReview>>;
}
```

Рекомендуемые подписи статусов:

```ts
export const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  pending: "На модерации",
  published: "Опубликован",
  rejected: "Отклонён",
  hidden: "Скрыт",
};
```

Для `rejected` можно показать пользователю `moderation_comment`, если менеджер
его заполнил.

## 5. Отображение вложений

```tsx
function ReviewMediaList({ media }: { media: ReviewMedia[] }) {
  return (
    <div className="review-media">
      {media.map((item) =>
        item.media_type === "video" ? (
          <video key={item.id} src={item.url} controls preload="metadata" />
        ) : (
          <img key={item.id} src={item.url} alt="Вложение к отзыву" loading="lazy" />
        ),
      )}
    </div>
  );
}
```

Storage обычно возвращает абсолютный URL. Если окружение возвращает путь вида
`/media/...`, frontend должен добавить origin backend.

## 6. Обработка ошибок

```ts
async function apiError(response: Response) {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = { detail: "Не удалось прочитать ответ сервера" };
  }
  return { status: response.status, body };
}
```

Основные статусы:

- `201` — отзыв создан;
- `400` — ошибка данных или бизнес-правила;
- `401` — отсутствует или истёк access token;
- `413` — запрос целиком превышает лимит reverse proxy/web server;
- `500` — внутренняя ошибка backend.

Примеры `400`:

```json
{
  "rating": ["Убедитесь, что это значение больше либо равно 1."]
}
```

```json
{
  "media": ["Убедитесь, что в этом поле не больше 5 элементов."]
}
```

```json
{
  "non_field_errors": [
    "Вы уже оставили отзыв на этот товар в рамках этого заказа."
  ]
}
```

Backend остаётся источником истины. Даже если frontend показывает кнопку только
для заказов `paid/completed`, он обязан обработать `400`: статус заказа или
состав заказа могли измениться.

## 7. Сценарий личного кабинета

1. Получить историю заказов пользователя.
2. Для позиций заказов `paid/completed` показать действие «Оставить отзыв».
3. Отправить JSON, если файлов нет, или multipart, если они выбраны.
4. После `201` показать статус «На модерации».
5. Раздел «Мои отзывы» загрузить через `/catalog/reviews/mine/`.
6. Для опубликованных отзывов дать ссылку на `/products/{product.slug}`.
7. Для отклонённых показать `moderation_comment`, если он заполнен.

API редактирования и удаления собственных отзывов сейчас не предусмотрено.
