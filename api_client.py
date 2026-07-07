import logging
from typing import Any

import pandas as pd
import requests
import urllib3

from config import ApiSettings

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


def parse_group_and_emails(
    data: dict[str, Any] | None,
) -> tuple[str, str, str, str]:
    if not data:
        return '', '', '', ''

    groups_found: list[str] = []
    emails_found: list[str] = []
    leaders_found: list[str] = []

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

                emails_found.append(email)

                if role_name == 'Support Group Lead':
                    leaders_found.append(email)

    users = data.get('users', {})
    supported_users = users.get('Supported by', [])

    for user in supported_users:
        email = user.get('internet_e_mail')

        if email:
            emails_found.append(email)

    unique_groups = list(dict.fromkeys(groups_found))
    unique_leaders = list(dict.fromkeys(leaders_found))
    unique_emails = list(dict.fromkeys(emails_found))

    return (
        '; '.join(unique_groups),
        '; '.join(unique_leaders),
        '; '.join(unique_emails),
        service,
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

        group, leader, emails, service = parse_group_and_emails(data)

        rows.append(
            {
                'fqdn': fqdn,
                'ip': ip,
                'Группа': group,
                'Лидер группы': leader,
                'Почты': emails,
                'Наименование ИС': service,
            }
        )

    result = pd.DataFrame(rows)

    logger.info(
        'API-обогащение завершено. Строк: %s',
        len(result),
    )

    return result