STATUS_LABELS = {
    'order': {
        'new': {'ru': 'Новый', 'kz': 'Жаңа', 'en': 'New'},
        'waiting_payment': {
            'ru': 'Ожидает оплаты', 'kz': 'Төлем күтілуде', 'en': 'Awaiting payment',
        },
        'paid': {'ru': 'Оплачен', 'kz': 'Төленді', 'en': 'Paid'},
        'processing': {'ru': 'В обработке', 'kz': 'Өңделуде', 'en': 'Processing'},
        'shipped': {'ru': 'Отправлен', 'kz': 'Жөнелтілді', 'en': 'Shipped'},
        'completed': {'ru': 'Завершён', 'kz': 'Аяқталды', 'en': 'Completed'},
        'cancelled': {'ru': 'Отменён', 'kz': 'Бас тартылды', 'en': 'Cancelled'},
        'returned': {'ru': 'Возвращён', 'kz': 'Қайтарылды', 'en': 'Returned'},
    },
    'order_payment': {
        'unpaid': {'ru': 'Не оплачен', 'kz': 'Төленбеген', 'en': 'Unpaid'},
        'waiting': {
            'ru': 'Ожидает оплаты', 'kz': 'Төлем күтілуде', 'en': 'Awaiting payment',
        },
        'paid': {'ru': 'Оплачен', 'kz': 'Төленді', 'en': 'Paid'},
        'failed': {'ru': 'Ошибка оплаты', 'kz': 'Төлем қатесі', 'en': 'Payment failed'},
        'refunded': {
            'ru': 'Средства возвращены', 'kz': 'Қаражат қайтарылды', 'en': 'Refunded',
        },
        'cancelled': {'ru': 'Отменён', 'kz': 'Бас тартылды', 'en': 'Cancelled'},
        'expired': {
            'ru': 'Время оплаты истекло',
            'kz': 'Төлем уақыты өтті',
            'en': 'Payment time expired',
        },
    },
    'payment': {
        'pending': {'ru': 'Ожидает', 'kz': 'Күтілуде', 'en': 'Pending'},
        'success': {'ru': 'Успешно', 'kz': 'Сәтті', 'en': 'Successful'},
        'failed': {'ru': 'Ошибка', 'kz': 'Қате', 'en': 'Failed'},
        'refunded': {'ru': 'Возвращён', 'kz': 'Қайтарылды', 'en': 'Refunded'},
        'cancelled': {'ru': 'Отменён', 'kz': 'Бас тартылды', 'en': 'Cancelled'},
        'expired': {
            'ru': 'Время оплаты истекло',
            'kz': 'Төлем уақыты өтті',
            'en': 'Payment time expired',
        },
    },
    'import_job': {
        'pending': {
            'ru': 'Ожидает обработки', 'kz': 'Өңдеуді күтуде', 'en': 'Pending processing',
        },
        'processing': {'ru': 'В обработке', 'kz': 'Өңделуде', 'en': 'Processing'},
        'completed': {'ru': 'Завершён', 'kz': 'Аяқталды', 'en': 'Completed'},
        'completed_with_errors': {
            'ru': 'Завершён с ошибками',
            'kz': 'Қателермен аяқталды',
            'en': 'Completed with errors',
        },
        'failed': {'ru': 'Ошибка', 'kz': 'Қате', 'en': 'Failed'},
    },
    'review': {
        'pending': {
            'ru': 'На модерации', 'kz': 'Модерацияда', 'en': 'Pending moderation',
        },
        'published': {'ru': 'Опубликован', 'kz': 'Жарияланған', 'en': 'Published'},
        'rejected': {'ru': 'Отклонён', 'kz': 'Қабылданбаған', 'en': 'Rejected'},
        'hidden': {'ru': 'Скрыт', 'kz': 'Жасырылған', 'en': 'Hidden'},
    },
    'notification': {
        'unread': {'ru': 'Не прочитано', 'kz': 'Оқылмаған', 'en': 'Unread'},
        'read': {'ru': 'Прочитано', 'kz': 'Оқылған', 'en': 'Read'},
    },
}


def get_status_labels(group, value):
    """Return all language labels for a stable machine status value."""
    return STATUS_LABELS[group][str(value)]


def get_status_registry():
    """Return a JSON-ready registry grouped by domain."""
    return {
        group: [
            {'value': value, 'labels': labels}
            for value, labels in statuses.items()
        ]
        for group, statuses in STATUS_LABELS.items()
    }
