"""Модуль записи заявок в реестр-Excel."""

import logging
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from src.utils import normalize_text

logger = logging.getLogger('auto_responsible.ticket_registry')


def _get_header_map(ws) -> dict[str, int]:
    return {
        normalize_text(cell.value): idx
        for idx, cell in enumerate(ws[1], start=1)
        if normalize_text(cell.value)
    }


def append_ticket_to_registry(
    registry_file: Path,
    registry_columns: dict[str, str],
    ticket_number: int,
    group_name: str,
    ip_or_fqdn: str,
    vulnerability_id: str,
    status: str,
) -> None:
    if not registry_file.exists():
        raise FileNotFoundError(f'Реестр не найден: {registry_file}')

    wb = load_workbook(registry_file)
    ws = wb.active

    header_map = _get_header_map(ws)
    logger.info('Колонки реестра: %s', list(header_map.keys()))

    values = {
        registry_columns['ticket_number']: ticket_number,
        registry_columns['group']: group_name,
        registry_columns['host']: ip_or_fqdn,
        registry_columns['date']: datetime.now().strftime('%d.%m.%Y'),
        registry_columns['status']: status,
    }

    vuln_col = registry_columns.get('vulnerability_id')
    if vuln_col:
        values[vuln_col] = vulnerability_id

    missing = [name for name in values if name not in header_map]
    if missing:
        raise ValueError(f'В реестре отсутствуют колонки: {missing}')

    row_idx = ws.max_row + 1
    for column_name, value in values.items():
        ws.cell(row=row_idx, column=header_map[column_name], value=value)

    wb.save(registry_file)

    logger.info(
        'Реестр: ticket=%s group=%s host=%s vuln=%s',
        ticket_number,
        group_name,
        ip_or_fqdn,
        vulnerability_id,
    )