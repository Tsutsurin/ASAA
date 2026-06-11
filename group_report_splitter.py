import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

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
    value = value.strip()

    if not value:
        value = 'Без группы'

    value = re.sub(r'[<>:"/\\|?*]', '_', value)
    value = re.sub(r'\s+', ' ', value)

    return value[:120]


def normalize_value(value) -> str:
    return str(value or '').strip()


def normalize_header(value) -> str:
    return (
        str(value or '')
        .replace('\n', ' ')
        .replace('\r', ' ')
        .replace('\t', ' ')
        .strip()
        .lower()
    )


def reset_filters_and_show_rows(ws) -> None:
    ws.auto_filter.ref = None

    for row_idx in range(1, ws.max_row + 1):
        ws.row_dimensions[row_idx].hidden = False


def get_headers(ws) -> list[str]:
    return [
        str(cell.value).strip() if cell.value is not None else ''
        for cell in ws[1]
    ]


def find_optional_column_index(
    headers: list[str],
    column_name: str,
) -> int | None:
    target = normalize_header(column_name)

    for idx, header in enumerate(headers, start=1):
        if normalize_header(header) == target:
            return idx

    return None


def find_column_index(headers: list[str], column_name: str) -> int:
    col_idx = find_optional_column_index(
        headers=headers,
        column_name=column_name,
    )

    if col_idx is None:
        raise ValueError(
            f'В отчете не найден столбец "{column_name}". '
            f'Есть столбцы: {headers}'
        )

    return col_idx


def build_severity_rank(severity_order: list[str]) -> dict[str, int]:
    return {
        normalize_header(value): index
        for index, value in enumerate(severity_order)
    }


def get_sort_key(
    ws,
    row_idx: int,
    sort_col_indices: list[int],
    severity_col_idx: int | None,
    severity_rank: dict[str, int],
) -> tuple:
    key = []

    for col_idx in sort_col_indices:
        value = normalize_value(
            ws.cell(row=row_idx, column=col_idx).value
        )

        if severity_col_idx and col_idx == severity_col_idx:
            key.append(
                severity_rank.get(
                    normalize_header(value),
                    999,
                )
            )
        else:
            key.append(normalize_header(value))

    return tuple(key)


def sort_worksheet_rows(
    ws,
    headers: list[str],
    sort_columns: list[str],
    severity_order: list[str],
) -> None:
    if not sort_columns:
        logger.info('Сортировка отключена: sort_columns пустой')
        return

    logger.info('Заголовки файла: %s', headers)

    sort_col_indices = []

    for column_name in sort_columns:
        col_idx = find_optional_column_index(
            headers=headers,
            column_name=column_name,
        )

        if col_idx:
            sort_col_indices.append(col_idx)
        else:
            logger.warning(
                'Столбец сортировки не найден и будет пропущен: %s',
                column_name,
            )

    if not sort_col_indices:
        logger.warning('Не найдено ни одного столбца для сортировки')
        return

    severity_col_idx = None

    for column_name in sort_columns:
        normalized_column = normalize_header(column_name)

        if 'опасн' in normalized_column or 'критич' in normalized_column:
            severity_col_idx = find_optional_column_index(
                headers=headers,
                column_name=column_name,
            )
            break

    severity_rank = build_severity_rank(severity_order)

    rows = []

    for row_idx in range(2, ws.max_row + 1):
        values = [
            ws.cell(row=row_idx, column=col_idx).value
            for col_idx in range(1, ws.max_column + 1)
        ]

        rows.append(
            (
                get_sort_key(
                    ws=ws,
                    row_idx=row_idx,
                    sort_col_indices=sort_col_indices,
                    severity_col_idx=severity_col_idx,
                    severity_rank=severity_rank,
                ),
                values,
            )
        )

    rows.sort(key=lambda item: item[0])

    for target_row_idx, (_, values) in enumerate(rows, start=2):
        for col_idx, value in enumerate(values, start=1):
            ws.cell(
                row=target_row_idx,
                column=col_idx,
                value=value,
            )

    logger.info(
        'Лист отсортирован по столбцам: %s',
        sort_columns,
    )


def get_groups_ranges(
    ws,
    group_col_idx: int,
) -> list[tuple[str, int, int]]:
    result = []

    current_group = None
    start_row = None

    for row_idx in range(2, ws.max_row + 1):
        group_name = normalize_value(
            ws.cell(row=row_idx, column=group_col_idx).value
        )

        if current_group is None:
            current_group = group_name
            start_row = row_idx
            continue

        if group_name != current_group:
            result.append(
                (
                    current_group,
                    start_row,
                    row_idx - 1,
                )
            )

            current_group = group_name
            start_row = row_idx

    if current_group is not None and start_row is not None:
        result.append(
            (
                current_group,
                start_row,
                ws.max_row,
            )
        )

    non_empty = [
        item for item in result
        if item[0]
    ]

    empty = [
        item for item in result
        if not item[0]
    ]

    return non_empty + empty


def get_first_ip_or_fqdn_from_range(
    ws,
    ip_col_idx: int | None,
    fqdn_col_idx: int | None,
    start_row: int,
    end_row: int,
) -> str:
    for row_idx in range(start_row, end_row + 1):
        if ip_col_idx:
            ip_value = normalize_value(
                ws.cell(row=row_idx, column=ip_col_idx).value
            )

            if ip_value:
                return ip_value

        if fqdn_col_idx:
            fqdn_value = normalize_value(
                ws.cell(row=row_idx, column=fqdn_col_idx).value
            )

            if fqdn_value:
                return fqdn_value

    return ''


def get_values_from_range(
    ws,
    column_idx: int | None,
    start_row: int,
    end_row: int,
) -> str:
    if not column_idx:
        return ''

    values = []

    for row_idx in range(start_row, end_row + 1):
        value = normalize_value(
            ws.cell(row=row_idx, column=column_idx).value
        )

        if value:
            values.append(value)

    return '; '.join(dict.fromkeys(values))


def get_emails_from_range(
    ws,
    column_idx: int | None,
    start_row: int,
    end_row: int,
) -> str:
    if not column_idx:
        return ''

    emails = []

    for row_idx in range(start_row, end_row + 1):
        value = ws.cell(row=row_idx, column=column_idx).value

        if not value:
            continue

        for email in str(value).replace(',', ';').split(';'):
            email = email.strip()

            if email:
                emails.append(email)

    return '; '.join(dict.fromkeys(emails))


def delete_rows_outside_range(
    ws,
    start_row: int,
    end_row: int,
) -> None:
    rows_after = ws.max_row - end_row

    if rows_after > 0:
        ws.delete_rows(
            idx=end_row + 1,
            amount=rows_after,
        )

    rows_before = start_row - 2

    if rows_before > 0:
        ws.delete_rows(
            idx=2,
            amount=rows_before,
        )


def split_report_by_group(
    source_file: Path,
    output_dir: Path,
    group_column: str,
    ip_column: str,
    fqdn_column: str,
    vulnerability_column: str,
    sort_columns: list[str],
    severity_order: list[str],
) -> list[GroupReport]:
    logger.info(
        'Начинаю разделение отчета по группам: %s',
        source_file,
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    wb = load_workbook(source_file)
    ws = wb.active

    reset_filters_and_show_rows(ws)

    headers = get_headers(ws)

    group_col_idx = find_column_index(
        headers=headers,
        column_name=group_column,
    )

    ip_col_idx = find_optional_column_index(
        headers=headers,
        column_name=ip_column,
    )

    fqdn_col_idx = find_optional_column_index(
        headers=headers,
        column_name=fqdn_column,
    )

    vulnerability_col_idx = find_optional_column_index(
        headers=headers,
        column_name=vulnerability_column,
    )

    emails_col_idx = find_optional_column_index(
        headers=headers,
        column_name='Почты',
    )

    sort_worksheet_rows(
        ws=ws,
        headers=headers,
        sort_columns=sort_columns,
        severity_order=severity_order,
    )

    sorted_source_file = output_dir / '_sorted_source.xlsx'
    wb.save(sorted_source_file)

    group_ranges = get_groups_ranges(
        ws=ws,
        group_col_idx=group_col_idx,
    )

    logger.info(
        'Найдено групп для разделения: %s',
        len(group_ranges),
    )

    result: list[GroupReport] = []

    for group_name, start_row, end_row in group_ranges:
        display_name = group_name if group_name else 'Без группы'
        filename = safe_filename(display_name) + '.xlsx'
        output_file = output_dir / filename

        shutil.copy2(
            sorted_source_file,
            output_file,
        )

        group_wb = load_workbook(output_file)
        group_ws = group_wb.active

        delete_rows_outside_range(
            ws=group_ws,
            start_row=start_row,
            end_row=end_row,
        )
        
        reset_filters_and_show_rows(group_ws)

        group_wb.save(output_file)

        ip_or_fqdn = get_first_ip_or_fqdn_from_range(
            ws=ws,
            ip_col_idx=ip_col_idx,
            fqdn_col_idx=fqdn_col_idx,
            start_row=start_row,
            end_row=end_row,
        )

        vulnerability_ids = get_values_from_range(
            ws=ws,
            column_idx=vulnerability_col_idx,
            start_row=start_row,
            end_row=end_row,
        )

        emails = get_emails_from_range(
            ws=ws,
            column_idx=emails_col_idx,
            start_row=start_row,
            end_row=end_row,
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
            'Создан отчет группы: %s | rows=%s-%s | файл=%s | emails=%s',
            display_name,
            start_row,
            end_row,
            output_file,
            emails,
        )

    try:
        sorted_source_file.unlink()
    except Exception:
        logger.warning(
            'Не удалось удалить временный отсортированный файл: %s',
            sorted_source_file,
        )

    logger.info(
        'Разделение завершено. Групп: %s',
        len(result),
    )

    return result