"""Модуль загрузки и проверки блэклиста email."""

import json
import logging
from pathlib import Path

from .config import BASE_DIR
from .utils import normalize_text

logger = logging.getLogger('auto_responsible.blacklist')


def load_blacklist(
    path: str | Path | None,
) -> list[str]:
    if not path:
        logger.warning('Файл блэклиста не настроен')
        return []

    path = Path(path)

    if not path.is_absolute():
        path = BASE_DIR / path

    if not path.exists():
        raise FileNotFoundError(
            f'Файл блэклиста не найден: {path}'
        )

    try:
        with open(
            path,
            'r',
            encoding='utf-8-sig',
        ) as file:
            data = json.load(file)

    except Exception as error:
        raise RuntimeError(
            f'Не удалось прочитать блэклист: {path}'
        ) from error

    emails = []

    if isinstance(data, list):
        emails = [
            str(email).strip()
            for email in data
            if str(email or '').strip()
        ]

    elif isinstance(data, dict):
        raw_emails = data.get(
            'blocked_emails',
            [],
        )

        if isinstance(raw_emails, list):
            emails = [
                str(email).strip()
                for email in raw_emails
                if str(email or '').strip()
            ]

    else:
        raise ValueError(
            f'Некорректный формат блэклиста: {path}'
        )

    emails = list(dict.fromkeys(emails))

    logger.info(
        'Блэклист загружен: %s записей | файл=%s',
        len(emails),
        path,
    )

    return emails


def is_blocked(
    email: str,
    blacklist: list[str],
) -> bool:
    normalized_email = normalize_text(email)

    if not normalized_email:
        return False

    blocked = {
        normalize_text(item)
        for item in blacklist
        if normalize_text(item)
    }

    return normalized_email in blocked