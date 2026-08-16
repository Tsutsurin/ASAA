"""Общие утилиты проекта ASAA."""

import logging
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger('auto_responsible.utils')


def normalize_text(value) -> str:
    """Нормализация строки: strip, lower, замена переносов на пробелы."""
    return (
        str(value or '')
        .replace('\n', ' ')
        .replace('\r', ' ')
        .replace('\t', ' ')
        .strip()
        .lower()
    )


def normalize_value(value) -> str:
    """Нормализация значения ячейки: None/NaN → '', убираем .0 в конце."""
    if value is None or pd.isna(value):
        return ''

    text = str(value).strip()

    if text.endswith('.0'):
        text = text[:-2]

    return text


def is_blank(value) -> bool:
    """Проверка на пустое значение."""
    return str(value or '').strip() == ''


def split_emails(raw: str) -> list[str]:
    """Разделение строки с email на список, дедупликация, фильтрация пустых."""
    result = []

    for item in str(raw or '').replace(',', ';').split(';'):
        email = item.strip()

        if email:
            result.append(email)

    return list(dict.fromkeys(result))


def join_emails(*sources: str) -> str:
    """Объединение нескольких строк с email в одну с дедупликацией."""
    result = []

    for source in sources:
        result.extend(split_emails(source))

    return '; '.join(dict.fromkeys(result))


def safe_filename(value: str) -> str:
    """Очистка строки для использования в имени файла."""
    text = str(value or '').strip()

    if not text:
        text = 'unnamed'

    text = re.sub(r'[<>"\:/\\|?*]', '_', text)
    text = re.sub(r'\s+', ' ', text)

    return text[:120]


def ensure_dir(path: str | Path) -> Path:
    """Создание директории если не существует, возврат Path."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path