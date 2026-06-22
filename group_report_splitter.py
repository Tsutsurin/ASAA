import logging
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from report_formatter import stream_transform

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


def safe_filename(value: str) -> str:
    value = str(value or '').strip()

    if not value:
        value = 'Без группы'

    value = re.sub(r'[<>:"/\\|?*]', '_', value)
    value = re.sub(r'\s+', ' ', value)

    return value[:120]


def normalize_header(value) -> str:
    return (
        str(value or '')
        .replace('\n', ' ')
        .replace('\r', ' ')
        .replace('\t', ' ')
        .strip()
        .lower()
    )


def normalize_value(value) -> str:
    if value is None:
        return ''

    if pd.isna(value):
        return ''

    value = str(value).strip()

    if value.endswith('.0'):
        value = value[:-2]

    return value


def find_column(
    columns,
    column_name: str,
) -> str:
    target = normalize_header(column_name)

    for column in columns:
        if normalize_header(column) == target:
            return column

    raise ValueError(
        f'В отчете не найден столбец "{column_name}". '
        f'Есть столбцы: {list(columns)}'
    )


def find_optional_column(
    columns,
    column_name: str,
) -> str | None:
    target = normalize_header(column_name)

    for column in columns:
        if normalize_header(column) == target:
            return column

    return None


def unique_join(values) -> str:
    result = []

    for value in values:
        value = normalize_value(value)

        if value:
            result.append(value)

    return '; '.join(dict.fromkeys(result))


def emails_join(values) -> str:
    result = []

    for value in values:
        if not value:
            continue

        for email in str(value).replace(',', ';').split(';'):
            email = email.strip()

            if email:
                result.append(email)

    return '; '.join(dict.fromkeys(result))


def get_all_ip_or_fqdn(
    df: pd.DataFrame,
    ip_column: str | None,
    fqdn_column: str | None,
) -> str:
    hosts = []

    if ip_column:
        for value in df[ip_column]:
            value = normalize_value(value)

            if value:
                hosts.append(value)

    if fqdn_column:
        for value in df[fqdn_column]:
            value = normalize_value(value)

            if value:
                hosts.append(value)

    unique_hosts = list(dict.fromkeys(hosts))

    return '; '.join(unique_hosts)


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
        'Начинаю разделение отчета по группам через pandas: %s',
        source_file,
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_excel(
        source_file,
        dtype=str,
        keep_default_na=False,
    )

    group_real_column = find_column(
        columns=df.columns,
        column_name=group_column,
    )

    ip_real_column = find_optional_column(
        columns=df.columns,
        column_name=ip_column,
    )

    fqdn_real_column = find_optional_column(
        columns=df.columns,
        column_name=fqdn_column,
    )

    vulnerability_real_column = find_optional_column(
        columns=df.columns,
        column_name=vulnerability_column,
    )

    emails_real_column = find_optional_column(
        columns=df.columns,
        column_name='Почты',
    )

    df[group_real_column] = df[group_real_column].apply(normalize_value)

    grouped = df.groupby(
        group_real_column,
        dropna=False,
        sort=True,
    )

    result: list[GroupReport] = []

    logger.info(
        'Найдено групп для разделения: %s',
        grouped.ngroups,
    )

    for group_name, group_df in grouped:
        group_name = normalize_value(group_name)

        display_name = group_name if group_name else 'Без группы'
        filename = safe_filename(display_name) + '.xlsx'
        output_file = output_dir / filename

        group_df.to_excel(
            output_file,
            index=False,
        )

        stream_transform(output_file)

        ip_or_fqdn = get_all_ip_or_fqdn(
            df=group_df,
            ip_column=ip_real_column,
            fqdn_column=fqdn_real_column,
        )

        vulnerability_ids = (
            unique_join(group_df[vulnerability_real_column])
            if vulnerability_real_column
            else ''
        )

        emails = (
            emails_join(group_df[emails_real_column])
            if emails_real_column
            else ''
        )

        group_report = GroupReport(
            group_name=group_name,
            display_name=display_name,
            file_path=output_file,
            has_group=bool(group_name.strip()),
            ip_or_fqdn=ip_or_fqdn,
            vulnerability_ids=vulnerability_ids,
            emails=emails,
        )

        result.append(group_report)

        logger.info(
            'Создан отчет группы: %s | строк=%s | файл=%s | хостов=%s | emails=%s',
            display_name,
            len(group_df),
            output_file,
            len(ip_or_fqdn.split(';')) if ip_or_fqdn else 0,
            emails,
        )

    logger.info(
        'Разделение завершено. Групп: %s',
        len(result),
    )

    return result