"""Модуль разделения Excel-отчёта по группам на отдельные файлы."""

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.report_formatter import stream_transform
from src.utils import normalize_text, normalize_value, safe_filename

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

    raise ValueError(
        f'Столбец "{name}" не найден. '
        f'Есть: {list(columns)}'
    )


def _find_optional_column(
    columns,
    name: str,
) -> str | None:
    target = normalize_text(name)

    for column in columns:
        if normalize_text(column) == target:
            return column

    return None


def _unique_join(values) -> str:
    result = []

    for value in values:
        value = normalize_value(value)

        if value:
            result.append(value)

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


def _get_all_hosts(
    df: pd.DataFrame,
    ip_col: str | None,
    fqdn_col: str | None,
) -> str:
    hosts = []

    if ip_col:
        for value in df[ip_col]:
            value = normalize_value(value)

            if value:
                hosts.append(value)

    if fqdn_col:
        for value in df[fqdn_col]:
            value = normalize_value(value)

            if value:
                hosts.append(value)

    return '; '.join(dict.fromkeys(hosts))


def _build_dispatch_key(
    row: pd.Series,
    group_col: str,
    service_col: str | None,
) -> str:
    group_name = normalize_value(row.get(group_col, ''))

    service_name = (
        normalize_value(row.get(service_col, ''))
        if service_col
        else ''
    )

    if group_name:
        return f'group::{group_name}'

    if service_name:
        return f'service::{service_name}'

    return 'no_group::'


def _make_unique_output_file(
    output_dir: Path,
    display_name: str,
    dispatch_key: str,
) -> Path:
    base_name = safe_filename(display_name)
    output_file = output_dir / f'{base_name}.xlsx'

    if not output_file.exists():
        return output_file

    if dispatch_key.startswith('service::'):
        suffix = 'ИС'
    elif dispatch_key.startswith('group::'):
        suffix = 'Группа'
    else:
        suffix = 'Без группы'

    output_file = output_dir / (
        f'{base_name} - {suffix}.xlsx'
    )

    counter = 2

    while output_file.exists():
        output_file = output_dir / (
            f'{base_name} - {suffix} {counter}.xlsx'
        )
        counter += 1

    return output_file


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

    logger.info(
        'Разделение отчета по группам: %s',
        source_file,
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    df = pd.read_excel(
        source_file,
        dtype=str,
        keep_default_na=False,
    )

    group_col = _find_column(
        df.columns,
        group_column,
    )

    ip_col = _find_optional_column(
        df.columns,
        ip_column,
    )

    fqdn_col = _find_optional_column(
        df.columns,
        fqdn_column,
    )

    vuln_col = _find_optional_column(
        df.columns,
        vulnerability_column,
    )

    emails_col = _find_optional_column(
        df.columns,
        'Почты',
    )

    service_col = _find_optional_column(
        df.columns,
        'Наименование ИС',
    )

    owner_admin_col = _find_optional_column(
        df.columns,
        'Ответственный ИС / Администратор ИС',
    )

    members_col = _find_optional_column(
        df.columns,
        'Члены группы',
    )

    manual_col = _find_optional_column(
        df.columns,
        'Ручной ввод',
    )

    routing_col = _find_optional_column(
        df.columns,
        'Маршрутизация ИС',
    )

    df[group_col] = df[group_col].apply(
        normalize_value
    )

    if service_col:
        df[service_col] = df[service_col].apply(
            normalize_value
        )

    dispatch_key_column = '__dispatch_key__'

    df[dispatch_key_column] = df.apply(
        lambda row: _build_dispatch_key(
            row=row,
            group_col=group_col,
            service_col=service_col,
        ),
        axis=1,
    )

    grouped = df.groupby(
        dispatch_key_column,
        dropna=False,
        sort=True,
    )

    result: list[GroupReport] = []

    logger.info(
        'Групп для разделения после учета ИС: %s',
        grouped.ngroups,
    )

    for dispatch_key, group_df in grouped:
        group_df = group_df.copy()

        group_name = _unique_join(
            group_df[group_col]
        )

        service_name = (
            _unique_join(group_df[service_col])
            if service_col
            else ''
        )

        if dispatch_key.startswith('group::'):
            display_name = group_name
            has_group = True

        elif dispatch_key.startswith('service::'):
            display_name = service_name
            has_group = True

        else:
            display_name = 'Без группы'
            has_group = False

        logger.info(
            'Маршрут группировки: key=%s | '
            'group=%s | service=%s | '
            'display=%s | has_group=%s | строк=%s',
            dispatch_key,
            group_name,
            service_name,
            display_name,
            has_group,
            len(group_df),
        )

        export_df = group_df.drop(
            columns=[dispatch_key_column],
            errors='ignore',
        )

        output_file = _make_unique_output_file(
            output_dir=output_dir,
            display_name=display_name,
            dispatch_key=str(dispatch_key),
        )

        export_df.to_excel(
            output_file,
            index=False,
        )

        stream_transform(output_file)

        report = GroupReport(
            group_name=group_name,
            display_name=display_name,
            file_path=output_file,
            has_group=has_group,
            ip_or_fqdn=_get_all_hosts(
                group_df,
                ip_col,
                fqdn_col,
            ),
            vulnerability_ids=(
                _unique_join(group_df[vuln_col])
                if vuln_col
                else ''
            ),
            emails=(
                _emails_join(group_df[emails_col])
                if emails_col
                else ''
            ),
            service_name=service_name,
            service_owner_admin=(
                _emails_join(
                    group_df[owner_admin_col]
                )
                if owner_admin_col
                else ''
            ),
            group_member_emails=(
                _emails_join(
                    group_df[members_col]
                )
                if members_col
                else ''
            ),
            manual_emails=(
                _emails_join(
                    group_df[manual_col]
                )
                if manual_col
                else ''
            ),
            service_routing_emails=(
                _emails_join(
                    group_df[routing_col]
                )
                if routing_col
                else ''
            ),
        )

        result.append(report)

        logger.info(
            'Создан отчет: %s | '
            'строк=%s | '
            'файл=%s | '
            'хостов=%s | '
            'service=%s | '
            'owner_admin=%s | '
            'members=%s | '
            'manual=%s | '
            'routing=%s',
            display_name,
            len(group_df),
            output_file.name,
            (
                len(report.ip_or_fqdn.split(';'))
                if report.ip_or_fqdn
                else 0
            ),
            service_name,
            report.service_owner_admin,
            report.group_member_emails,
            report.manual_emails,
            report.service_routing_emails,
        )

    logger.info(
        'Разделение завершено. Отчетов: %s',
        len(result),
    )

    return result