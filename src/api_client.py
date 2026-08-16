"""Модуль HTTP-запросов к API ответственных (CMDB)."""

import logging
from typing import Any

import pandas as pd
import requests
import urllib3

from src.config import ApiSettings

logger = logging.getLogger('auto_responsible.api')

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ResponsibleApiClient:
    def __init__(self, settings: ApiSettings):
        self.settings = settings

    def request_by_ip(self, ip: str) -> dict[str, Any] | None:
        return self._request({'ipaddress': ip})

    def request_by_hostname(self, hostname: str) -> dict[str, Any] | None:
        return self._request({'hostname': hostname})

    def _request(self, params: dict[str, str]) -> dict[str, Any] | None:
        try:
            response = requests.get(
                self.settings.base_url,
                params=params,
                verify=self.settings.verify_ssl,
                timeout=self.settings.timeout,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.exception('Ошибка API-запроса. params=%s', params)
            return None


def get_emails_from_users(users) -> list[str]:
    result = []
    if not isinstance(users, list):
        return result
    for user in users:
        if not isinstance(user, dict):
            continue
        email = user.get('internet_e_mail')
        if email:
            result.append(str(email).strip())
    return [email for email in result if email]


def parse_group_and_emails(
    data: dict[str, Any] | None,
) -> tuple[str, str, str, str]:
    """Возвращает: (group, group_members, service, service_owner_admin)"""
    if not data:
        return '', '', '', ''

    groups_found: list[str] = []
    group_member_emails: list[str] = []
    service_owner_admin_emails: list[str] = []

    service = str(data.get('service') or '').strip()

    groups = data.get('groups', {})
    supported_by = groups.get('Supported by', {})

    for group_name, group_data in supported_by.items():
        groups_found.append(group_name)
        for role_name, role_users in group_data.items():
            if not isinstance(role_users, list):
                continue
            for user in role_users:
                email = user.get('internet_e_mail')
                if not email:
                    continue
                group_member_emails.append(email)
                if role_name == 'Support Group Lead':
                    pass  # leader removed, all go to group_members

    users = data.get('users', {})
    supported_users = users.get('Supported by', [])
    for user in supported_users:
        email = user.get('internet_e_mail')
        if email:
            group_member_emails.append(email)

    serviceusers = data.get('serviceusers', {})
    service_owner_admin_emails.extend(
        get_emails_from_users(serviceusers.get('Owned by', []))
    )
    service_owner_admin_emails.extend(
        get_emails_from_users(serviceusers.get('Supported by', []))
    )

    unique_groups = list(dict.fromkeys(groups_found))
    unique_group_members = list(dict.fromkeys(group_member_emails))
    unique_service_owner_admin = list(dict.fromkeys(service_owner_admin_emails))

    return (
        '; '.join(unique_groups),
        '; '.join(unique_group_members),
        service,
        '; '.join(unique_service_owner_admin),
    )


def enrich_params_with_api(
    params: pd.DataFrame,
    settings: ApiSettings,
) -> pd.DataFrame:
    client = ResponsibleApiClient(settings)
    rows = []

    for _, row in params.iterrows():
        fqdn = str(row.get('fqdn', '') or '').strip()
        ip = str(row.get('ip', '') or '').strip()

        data = None
        if ip:
            logger.info('Запрос API по IP: %s', ip)
            data = client.request_by_ip(ip)
        if not data and fqdn:
            logger.info('Запрос API по hostname: %s', fqdn)
            data = client.request_by_hostname(fqdn)

        group, group_members, service, service_owner_admin = (
            parse_group_and_emails(data)
        )

        rows.append({
            'fqdn': fqdn,
            'ip': ip,
            'Группа': group,
            'Члены группы': group_members,
            'Наименование ИС': service,
            'Ответственный ИС / Администратор ИС': service_owner_admin,
        })

    result = pd.DataFrame(rows)
    logger.info('API-обогащение завершено. Строк: %s', len(result))
    return result