"""Модуль бэкэнд-маппинга: соответствие веб-публикаций и бэкэнд-серверов."""

import json
import logging
from pathlib import Path

logger = logging.getLogger('auto_responsible.backend')


def load_backend_mapping(path: str | Path | None) -> dict[str, list[str]]:
    """Загрузка маппинга веб-публикаций → список бэкэнд FQDN из JSON-файла.

    Поддерживает форматы значений:
        - "single.backend.ru"          → ["single.backend.ru"]
        - ["be1.ru", "be2.ru"]         → ["be1.ru", "be2.ru"]
    """
    if not path:
        return {}

    path = Path(path)

    if not path.exists():
        logger.warning('Файл бэкэнд-маппинга не найден: %s', path)
        return {}

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        logger.exception('Ошибка чтения бэкэнд-маппинга: %s', path)
        return {}

    result: dict[str, list[str]] = {}

    for key, value in data.items():
        if not isinstance(key, str):
            continue

        backends: list[str] = []

        if isinstance(value, str):
            backends = [value.strip()]
        elif isinstance(value, list):
            backends = [str(v).strip() for v in value if str(v).strip()]

        if backends:
            result[key.strip().lower()] = backends

    logger.info('Загружен бэкэнд-маппинг: %s записей', len(result))
    return result


def get_backend_fqdns(host: str, mapping: dict[str, list[str]]) -> list[str]:
    """Поиск бэкэндов по хосту (case-insensitive). Возвращает список."""
    return mapping.get(host.strip().lower(), [])