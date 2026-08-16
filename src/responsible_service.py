"""Модуль обогащения параметров данными об ответственных через API."""

import logging

import pandas as pd

from src.api_client import (
    ResponsibleApiClient,
    enrich_params_with_api,
    parse_group_and_emails,
)
from src.backend_service import get_backend_fqdns, load_backend_mapping
from src.config import Settings
from src.service_routing import get_service_recipients, load_service_routing
from src.utils import normalize_value

logger = logging.getLogger('auto_responsible.service')


def _dedupe_join(*values: str) -> str:
    """Объединение строк через ';', удаление дублей и пустых."""
    emails = []
    for value in values:
        if not value:
            continue
        for part in str(value).replace(',', ';').split(';'):
            part = part.strip()
            if part:
                emails.append(part)
    return '; '.join(dict.fromkeys(emails))


def _fill_service_routing(result: pd.DataFrame, settings: Settings) -> None:
    """Заполнение колонки 'Маршрутизация ИС' из JSON-файла маршрутизации."""
    service_routing = load_service_routing(settings.dispatch.service_routing)

    if not service_routing:
        return

    for idx, row in result.iterrows():
        service_name = normalize_value(row.get('Наименование ИС'))

        if not service_name:
            continue

        routing_emails = get_service_recipients(
            service_name=service_name,
            routing=service_routing,
        )

        if routing_emails:
            result.at[idx, 'Маршрутизация ИС'] = '; '.join(routing_emails)

    count = (result['Маршрутизация ИС'] != '').sum()
    logger.info('Маршрутизация ИС заполнена: %s записей', count)


def _backend_fallback(result: pd.DataFrame, settings: Settings) -> None:
    """Fallback: если API не вернул данные, пробуем бэкэнд-маппинг + повторный API."""
    backend_mapping = load_backend_mapping(settings.backend_mapping_file)

    if not backend_mapping:
        return

    client = ResponsibleApiClient(settings.api)

    for idx, row in result.iterrows():
        group = normalize_value(row.get('Группа'))
        service = normalize_value(row.get('Наименование ИС'))

        if group or service:
            continue

        fqdn = normalize_value(row.get('fqdn'))
        ip = normalize_value(row.get('ip'))

        backends: list[str] = []
        if fqdn:
            backends = get_backend_fqdns(fqdn, backend_mapping)
        if not backends and ip:
            backends = get_backend_fqdns(ip, backend_mapping)

        if not backends:
            continue

        logger.info('Бэкэнд(ы) для %s: %s', fqdn or ip, backends)

        all_groups: list[str] = []
        all_members: list[str] = []
        all_services: list[str] = []
        all_owners: list[str] = []

        for backend in backends:
            data = client.request_by_hostname(backend)
            if not data:
                continue

            g, gm, s, soa = parse_group_and_emails(data)

            if g:
                all_groups.append(g)
            if gm:
                all_members.append(gm)
            if s:
                all_services.append(s)
            if soa:
                all_owners.append(soa)

        if not all_groups and not all_services:
            continue

        result.at[idx, 'Группа'] = _dedupe_join(*all_groups)
        result.at[idx, 'Члены группы'] = _dedupe_join(*all_members)
        result.at[idx, 'Наименование ИС'] = _dedupe_join(*all_services)
        result.at[idx, 'Ответственный ИС / Администратор ИС'] = _dedupe_join(*all_owners)
        result.at[idx, 'Бэкэнд сервер'] = '; '.join(backends)


def _get_unique_params(params: pd.DataFrame) -> pd.DataFrame:
    """Дедупликация параметров по fqdn/ip."""
    df = params.copy()
    df['fqdn'] = df['fqdn'].apply(normalize_value)
    df['ip'] = df['ip'].apply(normalize_value)
    df = df[(df['fqdn'] != '') | (df['ip'] != '')]
    return df.drop_duplicates(subset=['fqdn', 'ip'], keep='first').reset_index(drop=True)


def _stub(params: pd.DataFrame) -> pd.DataFrame:
    """Заглушка при отключённом API."""
    result = params.copy()
    result['Группа'] = 'TEST_GROUP'
    result['Члены группы'] = 'test@company.ru'
    result['Наименование ИС'] = ''
    result['Ответственный ИС / Администратор ИС'] = ''
    result['Маршрутизация ИС'] = ''
    result['Бэкэнд сервер'] = ''
    logger.info('Используется заглушка вместо API')
    return result


def enrich_with_responsibles(
    params: pd.DataFrame,
    settings: Settings,
) -> pd.DataFrame:
    """Обогащение DataFrame данными об ответственных через API + backend fallback."""
    if params.empty:
        logger.warning('Пустой набор входных параметров')
        return params

    unique_params = _get_unique_params(params)

    logger.info(
        'Строк в отчете: %s | уникальных fqdn/ip: %s',
        len(params),
        len(unique_params),
    )

    if unique_params.empty:
        logger.warning('После дедупликации не осталось fqdn/ip')
        return unique_params

    if not settings.api.enabled:
        return _stub(unique_params)

    result = enrich_params_with_api(
        params=unique_params,
        settings=settings.api,
    )

    _backend_fallback(result, settings)
    _fill_service_routing(result, settings)

    logger.info(
        'Обогащение завершено. Строк: %s | бэкэнд: %s | маршрутизация: %s',
        len(result),
        (result.get('Бэкэнд сервер', '') != '').sum(),
        (result.get('Маршрутизация ИС', '') != '').sum(),
    )

    return result