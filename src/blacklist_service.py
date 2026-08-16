"""Модуль загрузки и проверки блэклиста email из отдельного JSON-файла."""

import json
import logging
from pathlib import Path

from src.utils import normalize_text

logger = logging.getLogger('auto_responsible.blacklist')


def load_blacklist(path: str | Path | None) -> list[str]:
    """Загрузка блэклиста из JSON-файла.

    Поддерживает форматы:
        - ["email1@x.ru", "email2@x.ru"]  # массив строк
        - {"blocked_emails": ["email1@x.ru"]}  # объект с ключом
    """
    if not path:
        return []

    path = Path(path)

    if not path.exists():
        logger.warning('Файл блэклиста не найден: %s', path)
        return []

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        logger.exception('Ошибка чтения блэклиста: %s', path)
        return []

    emails: list[str] = []

    if isinstance(data, list):
        emails = [str(e).strip() for e in data if str(e).strip()]
    elif isinstance(data, dict):
        raw = data.get('blocked_emails', [])
        if isinstance(raw, list):
            emails = [str(e).strip() for e in raw if str(e).strip()]

    logger.info('Блэклист загружен: %s записей из %s', len(emails), path)
    return emails


def is_blocked(email: str, blacklist: list[str]) -> bool:
    """Проверка email на вхождение в блэклист (case-insensitive)."""
    normalized = normalize_text(email)
    blocked_set = {normalize_text(e) for e in blacklist if normalize_text(e)}
    return normalized in blocked_set