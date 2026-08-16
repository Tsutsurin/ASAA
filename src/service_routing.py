import json
import logging
import re
from pathlib import Path

from src.config import BASE_DIR, ServiceRoutingSettings

logger = logging.getLogger('auto_responsible.service_routing')


def normalize_service(value: str) -> str:
    value = str(value or '').strip().lower()
    value = value.replace('ё', 'е')
    value = re.sub(r'\s+', ' ', value)
    return value


def split_service_names(value: str) -> list[str]:
    result = []

    for item in str(value or '').replace(',', ';').split(';'):
        item = item.strip()

        if item:
            result.append(item)

    return list(dict.fromkeys(result))


def load_service_routing(
    settings: ServiceRoutingSettings,
) -> dict[str, list[str]]:
    if not settings.enabled:
        logger.info('Маршрутизация по ИС отключена')
        return {}

    path = Path(settings.file)

    if not path.is_absolute():
        path = BASE_DIR / path

    if not path.exists():
        raise RuntimeError(
            f'Файл маршрутизации по ИС не найден: {path}'
        )

    with open(path, 'r', encoding='utf-8-sig') as file:
        raw_data = json.load(file)

    result = {}

    for service_name, recipients in raw_data.items():
        normalized_name = normalize_service(service_name)

        if isinstance(recipients, str):
            recipients = [recipients]

        clean_recipients = [
            str(email).strip()
            for email in recipients
            if str(email).strip()
        ]

        if normalized_name and clean_recipients:
            result[normalized_name] = clean_recipients

    logger.info(
        'Загружена маршрутизация по ИС: %s записей | ключи=%s',
        len(result),
        list(result.keys()),
    )

    return result


def get_service_recipients(
    service_name: str,
    routing: dict[str, list[str]],
) -> list[str]:
    service_names = split_service_names(service_name)

    logger.info(
        'Проверяю маршрутизацию по ИС: raw="%s" | parsed=%s',
        service_name,
        service_names,
    )

    for name in service_names:
        normalized_name = normalize_service(name)

        recipients = routing.get(normalized_name)

        if recipients:
            logger.info(
                'Найдена маршрутизация по ИС: %s -> %s',
                name,
                recipients,
            )
            return recipients

    logger.info(
        'Маршрутизация по ИС не найдена: %s',
        service_name,
    )

    return []