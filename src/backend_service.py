"""Модуль бэкэнд-маппинга: соответствие веб-публикаций и бэкэнд-серверов."""

import json
import logging
from pathlib import Path

from .config import BASE_DIR

logger = logging.getLogger('auto_responsible.backend')


def load_backend_mapping(
    path: str | Path | None,
) -> dict[str, list[str]]:
    if not path:
        logger.info('Бэкэнд-маппинг не настроен')
        return {}

    path = Path(path)

    if not path.is_absolute():
        path = BASE_DIR / path

    if not path.exists():
        logger.error(
            'Файл бэкэнд-маппинга не найден: %s',
            path,
        )
        return {}

    try:
        with open(
            path,
            'r',
            encoding='utf-8-sig',
        ) as file:
            data = json.load(file)

    except Exception:
        logger.exception(
            'Ошибка чтения бэкэнд-маппинга: %s',
            path,
        )
        return {}

    if not isinstance(data, dict):
        logger.error(
            'Некорректный формат бэкэнд-маппинга: %s',
            path,
        )
        return {}

    result: dict[str, list[str]] = {}

    for key, value in data.items():
        if not isinstance(key, str):
            continue

        backends = []

        if isinstance(value, str):
            backend = value.strip()

            if backend:
                backends.append(backend)

        elif isinstance(value, list):
            for item in value:
                backend = str(item or '').strip()

                if backend:
                    backends.append(backend)

        if not backends:
            continue

        normalized_key = key.strip().lower()

        if normalized_key:
            result[normalized_key] = list(
                dict.fromkeys(backends)
            )

    logger.info(
        'Загружен бэкэнд-маппинг: %s записей | файл=%s',
        len(result),
        path,
    )

    return result


def get_backend_fqdns(
    host: str,
    mapping: dict[str, list[str]],
) -> list[str]:
    host = str(host or '').strip().lower()

    if not host:
        return []

    return mapping.get(host, [])