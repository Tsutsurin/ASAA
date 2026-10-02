"""Обработка обратной связи по заявкам."""

import html
import logging
import re
from dataclasses import dataclass

from .ai_client import (
    AiAnalysisResult,
    analyze_feedback,
)
from .config import Settings
from .exchange_sender import send_html_email


logger = logging.getLogger(
    'auto_responsible.feedback'
)


TICKET_PATTERNS = [
    re.compile(
        r'заявк[аиу]?\s*'
        r'(?:на\s+устранение\s+'
        r'уязвимостей\s*)?'
        r'№\s*(\d+)',
        re.IGNORECASE,
    ),
    re.compile(
        r'№\s*(\d+)',
        re.IGNORECASE,
    ),
]


REPLY_SEPARATORS = [
    re.compile(
        r'^\s*-{2,}\s*'
        r'original message'
        r'\s*-{2,}\s*$',
        re.IGNORECASE
        | re.MULTILINE,
    ),
    re.compile(
        r'^\s*from:\s+',
        re.IGNORECASE
        | re.MULTILINE,
    ),
    re.compile(
        r'^\s*от:\s+',
        re.IGNORECASE
        | re.MULTILINE,
    ),
    re.compile(
        r'^\s*sent:\s+',
        re.IGNORECASE
        | re.MULTILINE,
    ),
    re.compile(
        r'^\s*отправлено:\s+',
        re.IGNORECASE
        | re.MULTILINE,
    ),
]


@dataclass
class FeedbackItem:
    category: str
    ticket_number: int | None
    summary: str
    subject: str
    sender: str


def _html_to_text(
    value,
) -> str:
    text = str(
        value or ''
    )

    text = re.sub(
        r'(?is)<(script|style).*?>.*?</\1>',
        '',
        text,
    )

    text = re.sub(
        r'(?i)<br\s*/?>',
        '\n',
        text,
    )

    text = re.sub(
        r'(?i)</p\s*>',
        '\n',
        text,
    )

    text = re.sub(
        r'(?i)</div\s*>',
        '\n',
        text,
    )

    text = re.sub(
        r'<[^>]+>',
        '',
        text,
    )

    text = html.unescape(
        text
    )

    text = text.replace(
        '\r\n',
        '\n',
    ).replace(
        '\r',
        '\n',
    )

    lines = []

    for line in text.split('\n'):
        line = line.strip()

        if line:
            lines.append(
                line
            )

    return '\n'.join(
        lines
    ).strip()


def _remove_reply_history(
    text: str,
) -> str:
    cut_position = None

    for pattern in REPLY_SEPARATORS:
        match = pattern.search(
            text
        )

        if not match:
            continue

        if (
            cut_position is None
            or match.start()
            < cut_position
        ):
            cut_position = (
                match.start()
            )

    if cut_position is not None:
        text = text[
            :cut_position
        ]

    return text.strip()


def _extract_ticket_from_subject(
    subject: str,
) -> int | None:
    for pattern in TICKET_PATTERNS:
        match = pattern.search(
            subject or ''
        )

        if match:
            return int(
                match.group(1)
            )

    return None


def _get_sender(
    message,
) -> str:
    sender = getattr(
        message,
        'sender',
        None,
    )

    if sender is None:
        sender = getattr(
            message,
            'author',
            None,
        )

    if sender is None:
        return ''

    email_address = getattr(
        sender,
        'email_address',
        None,
    )

    if email_address:
        return str(
            email_address
        )

    return str(
        sender
    )


def _analyze_message(
    settings: Settings,
    message,
) -> FeedbackItem:
    subject = str(
        message.subject or ''
    ).strip()

    body = _html_to_text(
        message.body
    )

    body = _remove_reply_history(
        body
    )

    if not body:
        body = (
            'Пустой текст ответа'
        )

    ticket_from_subject = (
        _extract_ticket_from_subject(
            subject
        )
    )

    ai_result: AiAnalysisResult = (
        analyze_feedback(
            settings=settings.ai,
            subject=subject,
            body=body,
        )
    )

    ticket_number = (
        ticket_from_subject
        if ticket_from_subject is not None
        else ai_result.ticket_number
    )

    return FeedbackItem(
        category=ai_result.category,
        ticket_number=ticket_number,
        summary=ai_result.summary,
        subject=subject,
        sender=_get_sender(
            message
        ),
    )


def _escape(
    value,
) -> str:
    return html.escape(
        str(
            value or ''
        )
    )


def _render_item(
    item: FeedbackItem,
) -> str:
    if item.ticket_number is None:
        ticket = (
            'Без номера заявки'
        )
    else:
        ticket = (
            f'№{item.ticket_number}'
        )

    return (
        '<div style="'
        'margin-bottom: 18px;'
        '">'
        f'<b>{_escape(ticket)}</b><br>'
        f'{_escape(item.summary)}<br>'
        '<span style="color: #666;">'
        f'От: {_escape(item.sender)}'
        '</span>'
        '</div>'
    )


def _render_section(
    title: str,
    items: list[FeedbackItem],
) -> str:
    if not items:
        return ''

    content = ''.join(
        _render_item(item)
        for item in items
    )

    return (
        f'<h3>{_escape(title)}</h3>'
        f'{content}'
    )


def _build_report(
    items: list[FeedbackItem],
) -> str:
    rescans = [
        item
        for item in items
        if item.category == 'rescan'
    ]

    closed = [
        item
        for item in items
        if item.category == 'closed'
    ]

    other = [
        item
        for item in items
        if item.category == 'other'
    ]

    parts = [
        '<html><body>',
        '<h2>ASAA — обратная связь</h2>',
        (
            '<p>'
            'Обработано непрочитанных '
            f'писем: <b>{len(items)}</b>'
            '</p>'
        ),
        _render_section(
            'Требуется пересканирование',
            rescans,
        ),
        _render_section(
            'Подтверждено устранение / закрыто',
            closed,
        ),
        _render_section(
            'Остальное',
            other,
        ),
        '</body></html>',
    ]

    return ''.join(
        parts
    )


def process_feedback(
    settings: Settings,
    account,
) -> int:
    if not settings.feedback.enabled:
        logger.info(
            'Обратная связь отключена'
        )
        return 0

    if not settings.ai.enabled:
        logger.warning(
            'AI отключён. '
            'Обратная связь не обработана.'
        )
        return 0

    messages = list(
        account.inbox.filter(
            is_read=False
        ).order_by(
            'datetime_received'
        )
    )

    if not messages:
        logger.info(
            'Непрочитанных писем '
            'во Входящих нет'
        )
        return 0

    logger.info(
        'Найдено непрочитанных писем '
        'во Входящих: %s',
        len(messages),
    )

    processed_items = []
    processed_messages = []

    for message in messages:
        try:
            item = _analyze_message(
                settings=settings,
                message=message,
            )

            processed_items.append(
                item
            )

            processed_messages.append(
                message
            )

            logger.info(
                'Обработано письмо | '
                'ticket=%s | '
                'category=%s | '
                'subject=%s',
                item.ticket_number,
                item.category,
                item.subject,
            )

        except Exception:
            logger.exception(
                'Не удалось обработать письмо: %s',
                message.subject,
            )

    if not processed_items:
        logger.warning(
            'Ни одно письмо не удалось '
            'обработать'
        )
        return 0

    report_body = _build_report(
        processed_items
    )

    send_html_email(
        account=account,
        to=settings.feedback.report_to,
        cc=settings.feedback.report_cc,
        subject=(
            settings.feedback.report_subject
        ),
        html_body=report_body,
    )

    # Помечаем прочитанными только после
    # успешной отправки итоговой сводки.
    #
    # Если отправка отчета упадет,
    # письма останутся непрочитанными
    # и попадут в следующий запуск.
    for message in processed_messages:
        try:
            message.is_read = True

            message.save(
                update_fields=[
                    'is_read',
                ]
            )

        except Exception:
            logger.exception(
                'Не удалось пометить письмо '
                'прочитанным: %s',
                message.subject,
            )

    logger.info(
        'Обратная связь обработана. '
        'Писем=%s',
        len(processed_items),
    )

    return len(
        processed_items
    )