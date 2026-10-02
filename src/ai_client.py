"""Клиент локальной LLM через Ollama API."""

import json
import logging
import re
from dataclasses import dataclass

import requests

from .config import AiSettings


logger = logging.getLogger(
    'auto_responsible.ai_client'
)


VALID_CATEGORIES = {
    'rescan',
    'closed',
    'other',
}


@dataclass
class AiAnalysisResult:
    category: str
    ticket_number: int | None
    summary: str


def _build_prompt(
    subject: str,
    body: str,
) -> str:
    return f"""
Ты анализируешь ответы на заявки по устранению уязвимостей.

Определи категорию письма.

Допустимы только три категории:

rescan
Пользователь просит провести повторную проверку,
пересканирование или перепроверить устранение уязвимостей.

closed
Пользователь сообщает, что уязвимости устранены,
работы завершены или заявка закрыта,
но явно не просит провести повторную проверку.

other
Любой другой ответ.

ВАЖНО:
Если пользователь одновременно сообщает об устранении
и просит провести повторную проверку,
категория должна быть rescan.

Также определи номер заявки.
Номер может находиться в теме или тексте письма.
Если номер определить невозможно, верни null.

Сделай краткое резюме сути ответа на русском языке.
Не добавляй факты, которых нет в письме.

Верни ТОЛЬКО JSON.
Никакого Markdown.
Никаких пояснений.
Никакого текста до или после JSON.

Формат:

{{
  "category": "rescan",
  "ticket_number": 742,
  "summary": "Уязвимости устранены, просят провести повторную проверку"
}}

Тема письма:
{subject}

Текст нового сообщения:
{body}
""".strip()


def _extract_json(
    value: str,
) -> dict:
    value = value.strip()

    try:
        return json.loads(value)

    except json.JSONDecodeError:
        pass

    match = re.search(
        r'\{.*\}',
        value,
        flags=re.DOTALL,
    )

    if not match:
        raise ValueError(
            'Ollama не вернула JSON'
        )

    return json.loads(
        match.group(0)
    )


def _normalize_ticket_number(
    value,
) -> int | None:
    if value is None:
        return None

    if isinstance(value, int):
        return value

    match = re.search(
        r'\d+',
        str(value),
    )

    if not match:
        return None

    return int(
        match.group(0)
    )


def analyze_feedback(
    settings: AiSettings,
    subject: str,
    body: str,
) -> AiAnalysisResult:
    if not settings.enabled:
        raise RuntimeError(
            'AI отключён в settings.json'
        )

    url = (
        settings.base_url.rstrip('/')
        + '/api/generate'
    )

    payload = {
        'model': settings.model,
        'prompt': _build_prompt(
            subject=subject,
            body=body,
        ),
        'stream': False,
        'format': 'json',
        'options': {
            'temperature': 0,
        },
    }

    logger.info(
        'Отправка письма в AI | '
        'model=%s | subject=%s',
        settings.model,
        subject,
    )

    response = requests.post(
        url,
        json=payload,
        timeout=settings.timeout,
    )

    response.raise_for_status()

    response_data = response.json()

    raw_result = str(
        response_data.get(
            'response',
            '',
        )
    ).strip()

    if not raw_result:
        raise ValueError(
            'Ollama вернула пустой ответ'
        )

    result = _extract_json(
        raw_result
    )

    category = str(
        result.get(
            'category',
            'other',
        )
    ).strip().lower()

    if category not in VALID_CATEGORIES:
        logger.warning(
            'AI вернула неизвестную '
            'категорию %r. Использую other.',
            category,
        )

        category = 'other'

    ticket_number = (
        _normalize_ticket_number(
            result.get(
                'ticket_number'
            )
        )
    )

    summary = str(
        result.get(
            'summary',
            '',
        )
    ).strip()

    if not summary:
        summary = (
            'Не удалось получить '
            'краткое описание ответа'
        )

    logger.info(
        'AI классификация | '
        'category=%s | ticket=%s',
        category,
        ticket_number,
    )

    return AiAnalysisResult(
        category=category,
        ticket_number=ticket_number,
        summary=summary,
    )