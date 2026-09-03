# Системные статусы: гайд для frontend

Все машинные значения статусов остаются стабильными и не переводятся. Для
отображения backend возвращает подписи на русском, казахском и английском.

## Получить полный справочник

Endpoint публичный, авторизация не требуется:

```http
GET /api/v1/statuses/
```

Ответ сгруппирован по назначению:

```json
{
  "order": [
    {
      "value": "new",
      "labels": {"ru": "Новый", "kz": "Жаңа", "en": "New"}
    }
  ],
  "order_payment": [],
  "payment": [],
  "import_job": [],
  "review": [],
  "notification": []
}
```

Группы:

- `order` — жизненный цикл заказа;
- `order_payment` — состояние оплаты на заказе;
- `payment` — внутренняя транзакция платёжного провайдера;
- `import_job` — импорт каталога;
- `review` — модерация отзыва;
- `notification` — прочитано ли уведомление.

## TypeScript

```ts
export type Language = "ru" | "kz" | "en";

export type StatusLabels = Record<Language, string>;

export type StatusOption = {
  value: string;
  labels: StatusLabels;
};

export type SystemStatusRegistry = Record<
  | "order"
  | "order_payment"
  | "payment"
  | "import_job"
  | "review"
  | "notification",
  StatusOption[]
>;

export async function getSystemStatuses() {
  const response = await fetch(`${API_URL}/statuses/`);
  if (!response.ok) throw new Error(`Statuses request failed: ${response.status}`);
  return response.json() as Promise<SystemStatusRegistry>;
}
```

Справочник можно загрузить один раз при старте приложения и закешировать.

## Статусы заказа

| value | Русский | Қазақша | English |
|---|---|---|---|
| `new` | Новый | Жаңа | New |
| `waiting_payment` | Ожидает оплаты | Төлем күтілуде | Awaiting payment |
| `paid` | Оплачен | Төленді | Paid |
| `processing` | В обработке | Өңделуде | Processing |
| `shipped` | Отправлен | Жөнелтілді | Shipped |
| `completed` | Завершён | Аяқталды | Completed |
| `cancelled` | Отменён | Бас тартылды | Cancelled |
| `returned` | Возвращён | Қайтарылды | Returned |

Объекты заказа содержат `status` и `status_labels`.

## Статусы оплаты заказа

| value | Русский | Қазақша | English |
|---|---|---|---|
| `unpaid` | Не оплачен | Төленбеген | Unpaid |
| `waiting` | Ожидает оплаты | Төлем күтілуде | Awaiting payment |
| `paid` | Оплачен | Төленді | Paid |
| `failed` | Ошибка оплаты | Төлем қатесі | Payment failed |
| `refunded` | Средства возвращены | Қаражат қайтарылды | Refunded |
| `cancelled` | Отменён | Бас тартылды | Cancelled |

Объекты заказа и payment-status endpoint содержат `payment_status` и
`payment_status_labels`.

## Статусы платёжной транзакции

| value | Русский | Қазақша | English |
|---|---|---|---|
| `pending` | Ожидает | Күтілуде | Pending |
| `success` | Успешно | Сәтті | Successful |
| `failed` | Ошибка | Қате | Failed |
| `refunded` | Возвращён | Қайтарылды | Refunded |

## Статусы импорта

| value | Русский | Қазақша | English |
|---|---|---|---|
| `pending` | Ожидает обработки | Өңдеуді күтуде | Pending processing |
| `processing` | В обработке | Өңделуде | Processing |
| `completed` | Завершён | Аяқталды | Completed |
| `completed_with_errors` | Завершён с ошибками | Қателермен аяқталды | Completed with errors |
| `failed` | Ошибка | Қате | Failed |

Объекты импорта содержат `status` и `status_labels`.

## Статусы отзывов

| value | Русский | Қазақша | English |
|---|---|---|---|
| `pending` | На модерации | Модерацияда | Pending moderation |
| `published` | Опубликован | Жарияланған | Published |
| `rejected` | Отклонён | Қабылданбаған | Rejected |
| `hidden` | Скрыт | Жасырылған | Hidden |

Собственные отзывы содержат `status` и `status_labels`.

## Статусы уведомлений

| value | Русский | Қазақша | English |
|---|---|---|---|
| `unread` | Не прочитано | Оқылмаған | Unread |
| `read` | Прочитано | Оқылған | Read |

Уведомление сохраняет совместимое поле `is_read`, а дополнительно возвращает:

```json
{
  "is_read": false,
  "read_status": "unread",
  "read_status_labels": {
    "ru": "Не прочитано",
    "kz": "Оқылмаған",
    "en": "Unread"
  }
}
```

## Использование локализованной подписи

```ts
function statusLabel(
  labels: StatusLabels,
  language: Language,
): string {
  return labels[language] ?? labels.ru;
}
```

Frontend должен принимать бизнес-решения по машинному значению, например
`order.status === "completed"`, а `labels` использовать только для отображения.
