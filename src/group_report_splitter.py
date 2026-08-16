"""Модуль разделения Excel-отчёта по группам на отдельные файлы."""

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.report_formatter import stream_transform
from src.utils import normalize_text, normalize_value, safe_filename, split_emails

logger = logging.getLogger('auto_responsible.group_splitter')


@dataclass
class GroupReport:
    group_name: str
    display_name: str
    file_path: Path
    has_group: bool
    ip_or_fqdn: str
    vulnerability_ids: str
    emails: str
    service_name: str
    service_owner_admin: str
    group_member_emails: str
    manual_emails: str
    service_routing_emails: str


def _find_column(columns, name: str) -> str:
    target = normalize_text(name)
    for column in columns:
        if normalize_text(column) == target:
            return column
    raise ValueError(f'Столбец "{name}" не найден. Есть: {list(columns)}')


def _find_optional_column(columns, name: str) -> str | None:
    target = normalize_text(name)
    for column in columns:
        if normalize_text(column) == target:
            return column
    return None


def _unique_join(values) -> str:
    result = [normalize_value(v) for v in values if normalize_value(v)]
    return '; '.join(dict.fromkeys(result))


def _emails_join(values) -> str:
    result = []
    for value in values:
        if not value:
            continue
        for email in str(value).replace(',', ';').split(';'):
            email = email.strip()
            if email:
                result.append(email)
    return '; '.join(dict.fromkeys(result))


def _get_all_hosts(df: pd.DataFrame, ip_col, fqdn_col) -> str:
    hosts = []
    if ip_col:
        hosts.extend(normalize_value(v) for v in df[ip_col] if normalize_value(v))
    if fqdn_col:
        hosts.extend(normalize_value(v) for v in df[fqdn_col] if normalize_value(v))
    return '; '.join(dict.fromkeys(hosts))


def split_report_by_group(
    source_file: Path,
    output_dir: Path,
    group_column: str,
    ip_column: str,
    fqdn_column: str,
    vulnerability_column: str,
) -> list[GroupReport]:
    source_file = Path(source_file)
    output_dir = Path(output_dir)

    logger.info('Разделение отчета по группам: %s', source_file)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_excel(source_file, dtype=str, keep_default_na=False)

    # Находим реальные имена колонок
    group_col = _find_column(df.columns, group_column)
    ip_col = _find_optional_column(df.columns, ip_column)
    fqdn_col = _find_optional_column(df.columns, fqdn_column)
    vuln_col = _find_optional_column(df.columns, vulnerability_column)
    emails_col = _find_optional_column(df.columns, 'Почты')
    service_col = _find_optional_column(df.columns, 'Наименование ИС')
    owner_admin_col = _find_optional_column(df.columns, 'Ответственный ИС / Администратор ИС')
    members_col = _find_optional_column(df.columns, 'Члены группы')
    manual_col = _find_optional_column(df.columns, 'Ручной ввод')
    routing_col = _find_optional_column(df.columns, 'Маршрутизация ИС')

    df[group_col] = df[group_col].apply(normalize_value)

    grouped = df.groupby(group_col, dropna=False, sort=True)
    result: list[GroupReport] = []

    logger.info('Групп для разделения: %s', grouped.ngroups)

    for group_name, group_df in grouped:
        group_name = normalize_value(group_name)
        display_name = group_name or 'Без группы'
        has_group = bool(group_name)

        service_name = _unique_join(group_df[service_col]) if service_col else ''

        # Если группа пустая, но указано ИС — использовать ИС как группу
        if not has_group and service_name:
            display_name = service_name
            has_group = True

        output_file = output_dir / f'{safe_filename(display_name)}.xlsx'
        group_df.to_excel(output_file, index=False)
        stream_transform(output_file)

        report = GroupReport(
            group_name=group_name,
            display_name=display_name,
            file_path=output_file,
            has_group=has_group,
            ip_or_fqdn=_get_all_hosts(group_df, ip_col, fqdn_col),
            vulnerability_ids=_unique_join(group_df[vuln_col]) if vuln_col else '',
            emails=_emails_join(group_df[emails_col]) if emails_col else '',
            service_name=service_name,
            service_owner_admin=_emails_join(group_df[owner_admin_col]) if owner_admin_col else '',
            group_member_emails=_emails_join(group_df[members_col]) if members_col else '',
            manual_emails=_emails_join(group_df[manual_col]) if manual_col else '',
            service_routing_emails=_emails_join(group_df[routing_col]) if routing_col else '',
        )

        result.append(report)

        logger.info(
            'Группа: %s | строк=%s | файл=%s | хостов=%s | service=%s | owner_admin=%s | members=%s | manual=%s | routing=%s',
            display_name,
            len(group_df),
            output_file.name,
            len(report.ip_or_fqdn.split(';')) if report.ip_or_fqdn else 0,
            service_name,
            report.service_owner_admin,
            report.group_member_emails,
            report.manual_emails,
            report.service_routing_emails,
        )

    logger.info('Разделение завершено. Групп: %s', len(result))
    return result