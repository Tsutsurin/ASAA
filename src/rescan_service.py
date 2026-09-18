"""Режим повторной проверки заявок по результатам перескана."""

import logging
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .config import Settings
from .utils import normalize_text

logger = logging.getLogger(
    'auto_responsible.rescan'
)


RESULT_DIR_NAME = 'Результат'
ARCHIVE_DIR_NAME = 'Архив'
TEMPLATE_FILE_NAME = 'шаблон.txt'

VULNERABILITY_ID_COLUMN = (
    'Идентификатор уязвимости VM'
)

RESULT_COLUMNS = [
    'IP',
    'FQDN',
    'Описание',
    'Способ устранения',
    'CVE',
    'CVSS',
    'Уровень опасности',
    VULNERABILITY_ID_COLUMN,
]

STATUS_COLUMN = 'Статус'


def _is_excel_file(
    file_path: Path,
) -> bool:
    """
    Проверяет, является ли файл подходящим
    Excel-файлом.
    """
    if not file_path.is_file():
        return False

    if file_path.name.startswith('~$'):
        return False

    return file_path.suffix.lower() in {
        '.xlsx',
        '.xlsm',
    }


def _get_ticket_directories(
    tasks_dir: Path,
) -> list[Path]:
    """
    Возвращает числовые директории заявок:
    1, 2, 3, ...
    """
    if not tasks_dir.exists():
        raise FileNotFoundError(
            'Директория заявок не найдена: '
            f'{tasks_dir}'
        )

    directories = [
        path
        for path in tasks_dir.iterdir()
        if path.is_dir()
        and path.name.isdigit()
    ]

    directories.sort(
        key=lambda path: int(path.name)
    )

    return directories


def _get_excel_files(
    ticket_dir: Path,
) -> list[Path]:
    """
    Возвращает Excel-файлы только из корня
    папки заявки.

    Файлы из Результат/Архив сюда не попадают.
    """
    files = [
        path
        for path in ticket_dir.iterdir()
        if _is_excel_file(path)
    ]

    files.sort(
        key=lambda path: path.stat().st_mtime
    )

    return files


def _find_column(
    dataframe: pd.DataFrame,
    candidates: list[str],
) -> str | None:
    """
    Ищет колонку по одному из возможных названий.
    Сравнение выполняется через normalize_text().
    """
    normalized_columns = {
        normalize_text(column): column
        for column in dataframe.columns
    }

    for candidate in candidates:
        normalized_candidate = (
            normalize_text(candidate)
        )

        if (
            normalized_candidate
            in normalized_columns
        ):
            return normalized_columns[
                normalized_candidate
            ]

    return None


def _clean_value(
    value,
) -> str:
    """Преобразует значение Excel в строку."""
    if pd.isna(value):
        return ''

    value = str(value).strip()

    if value.lower() == 'nan':
        return ''

    return value


def _unique_values(
    values: list[str],
) -> list[str]:
    """
    Удаляет пустые значения и дубликаты,
    сохраняя исходный порядок.
    """
    result = []

    for value in values:
        value = _clean_value(value)

        if not value:
            continue

        if value not in result:
            result.append(value)

    return result


def _quote_values(
    values: list[str],
) -> str:
    """
    Превращает:
        ['1.2.3.4', '5.6.7.8']

    в:
        "1.2.3.4", "5.6.7.8"
    """
    return ', '.join(
        f'"{value}"'
        for value in values
    )


def _build_template_text(
    ip_addresses: list[str],
    fqdns: list[str],
) -> str:
    """
    Формирует содержимое шаблон.txt.

    Пример:

    1.2.3.4; 5.6.7.8
    aboba; aboba2
    Host.IpAddress in ["1.2.3.4", "5.6.7.8"]
    host.fqdn in ["aboba", "aboba2"]
    WebSite.DomainName in ["aboba", "aboba2"]
    """
    ip_line = '; '.join(
        ip_addresses
    )

    fqdn_line = '; '.join(
        fqdns
    )

    quoted_ips = _quote_values(
        ip_addresses
    )

    quoted_fqdns = _quote_values(
        fqdns
    )

    lines = [
        ip_line,
        fqdn_line,
        (
            'Host.IpAddress in '
            f'[{quoted_ips}]'
        ),
        (
            'host.fqdn in '
            f'[{quoted_fqdns}]'
        ),
        (
            'WebSite.DomainName in '
            f'[{quoted_fqdns}]'
        ),
    ]

    return '\n'.join(lines)


def _create_template_if_missing(
    ticket_dir: Path,
    original_file: Path,
) -> None:
    """
    Создаёт шаблон.txt, если его ещё нет.

    IP/FQDN берутся из оригинального Excel.
    """
    template_file = (
        ticket_dir
        / TEMPLATE_FILE_NAME
    )

    if template_file.exists():
        return

    try:
        dataframe = pd.read_excel(
            original_file
        )

    except Exception:
        logger.exception(
            'Не удалось прочитать Excel '
            'для создания шаблона: %s',
            original_file,
        )
        return

    ip_column = _find_column(
        dataframe,
        [
            'IP',
            'IP-адрес',
            'IP адрес',
            'Host.IpAddress',
            'IP Address',
            'IpAddress',
        ],
    )

    fqdn_column = _find_column(
        dataframe,
        [
            'FQDN',
            'Host.Fqdn',
            'Доменное имя',
            'Hostname',
        ],
    )

    ip_addresses = []

    if ip_column:
        ip_addresses = _unique_values(
            dataframe[
                ip_column
            ].tolist()
        )

    fqdns = []

    if fqdn_column:
        fqdns = _unique_values(
            dataframe[
                fqdn_column
            ].tolist()
        )

    template_text = (
        _build_template_text(
            ip_addresses=ip_addresses,
            fqdns=fqdns,
        )
    )

    template_file.write_text(
        template_text,
        encoding='utf-8',
    )

    logger.info(
        'Создан шаблон: %s | '
        'IP=%s | FQDN=%s',
        template_file,
        len(ip_addresses),
        len(fqdns),
    )


def _ensure_result_directories(
    ticket_dir: Path,
) -> tuple[Path, Path]:
    """
    Создаёт:

    <заявка>/Результат
    <заявка>/Результат/Архив
    """
    result_dir = (
        ticket_dir
        / RESULT_DIR_NAME
    )

    archive_dir = (
        result_dir
        / ARCHIVE_DIR_NAME
    )

    result_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    archive_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    return (
        result_dir,
        archive_dir,
    )


def _normalize_vulnerability_id(
    value,
) -> str:
    """
    Нормализует идентификатор уязвимости
    для сравнения.
    """
    value = _clean_value(value)

    return value.casefold()


def _get_vulnerability_column(
    dataframe: pd.DataFrame,
) -> str:
    """
    Находит колонку идентификатора
    уязвимости.
    """
    column = _find_column(
        dataframe,
        [
            VULNERABILITY_ID_COLUMN,
        ],
    )

    if not column:
        raise ValueError(
            'В Excel отсутствует колонка '
            f'"{VULNERABILITY_ID_COLUMN}"'
        )

    return column


def _get_original_and_rescan(
    excel_files: list[Path],
) -> tuple[Path, Path]:
    """
    Из двух Excel определяет:

    старый файл -> оригинал;
    новый файл -> перескан.

    Используется время изменения файла.
    """
    if len(excel_files) != 2:
        raise ValueError(
            'Для сравнения должно быть '
            'ровно 2 Excel-файла. '
            f'Найдено: {len(excel_files)}'
        )

    sorted_files = sorted(
        excel_files,
        key=lambda path: (
            path.stat().st_mtime,
            path.name,
        ),
    )

    return (
        sorted_files[0],
        sorted_files[1],
    )


def _get_result_source_column(
    dataframe: pd.DataFrame,
    target_column: str,
) -> str | None:
    """
    Определяет исходную колонку для
    результирующего отчёта.
    """
    aliases = {
        'IP': [
            'IP',
            'IP-адрес',
            'IP адрес',
            'Host.IpAddress',
            'IP Address',
            'IpAddress',
        ],
        'FQDN': [
            'FQDN',
            'Host.Fqdn',
            'Доменное имя',
            'Hostname',
        ],
        'Описание': [
            'Описание',
            'Description',
        ],
        'Способ устранения': [
            'Способ устранения',
            'Рекомендации',
            'Рекомендация',
            'Remediation',
        ],
        'CVE': [
            'CVE',
        ],
        'CVSS': [
            'CVSS',
            'CVSS Score',
        ],
        'Уровень опасности': [
            'Уровень опасности',
            'Severity',
            'Критичность',
        ],
        VULNERABILITY_ID_COLUMN: [
            VULNERABILITY_ID_COLUMN,
        ],
    }

    return _find_column(
        dataframe,
        aliases.get(
            target_column,
            [target_column],
        ),
    )


def _build_result_dataframe(
    original_df: pd.DataFrame,
    rescan_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Создаёт результат сравнения.

    ВАЖНО:
    основой результата является ТОЛЬКО
    оригинальный файл.

    Новые уязвимости из перескана
    в результат не добавляются.

    Если ID оригинальной уязвимости:
    - найден в перескане -> неустранено;
    - отсутствует -> устранено.
    """
    original_vulnerability_column = (
        _get_vulnerability_column(
            original_df
        )
    )

    rescan_vulnerability_column = (
        _get_vulnerability_column(
            rescan_df
        )
    )

    rescan_ids = {
        _normalize_vulnerability_id(
            value
        )
        for value in rescan_df[
            rescan_vulnerability_column
        ].tolist()
        if _normalize_vulnerability_id(
            value
        )
    }

    source_columns = {
        target_column: (
            _get_result_source_column(
                original_df,
                target_column,
            )
        )
        for target_column
        in RESULT_COLUMNS
    }

    result_rows = []

    for _, row in original_df.iterrows():
        vulnerability_id = (
            _clean_value(
                row.get(
                    original_vulnerability_column,
                    '',
                )
            )
        )

        normalized_id = (
            _normalize_vulnerability_id(
                vulnerability_id
            )
        )

        if (
            normalized_id
            and normalized_id
            in rescan_ids
        ):
            status = 'неустранено'
        else:
            status = 'устранено'

        result_row = {}

        for target_column in RESULT_COLUMNS:
            source_column = (
                source_columns[
                    target_column
                ]
            )

            if source_column:
                result_row[
                    target_column
                ] = _clean_value(
                    row.get(
                        source_column,
                        '',
                    )
                )
            else:
                result_row[
                    target_column
                ] = ''

        result_row[
            STATUS_COLUMN
        ] = status

        result_rows.append(
            result_row
        )

    return pd.DataFrame(
        result_rows,
        columns=(
            RESULT_COLUMNS
            + [STATUS_COLUMN]
        ),
    )


def _format_result_excel(
    result_file: Path,
) -> None:
    """
    Форматирует результирующий Excel:
    - фильтр;
    - закрепление первой строки;
    - оформление заголовка;
    - границы;
    - перенос текста;
    - ширина колонок.

    Сортировка по Статусу выполняется
    по алфавиту А -> Я.
    """
    wb = load_workbook(
        result_file
    )

    ws = wb.active
    ws.title = 'Проверка'

    thin = Side(
        style='thin',
    )

    border = Border(
        left=thin,
        right=thin,
        top=thin,
        bottom=thin,
    )

    header_fill = PatternFill(
        fill_type='solid',
        fgColor='1F2933',
    )

    header_font = Font(
        color='FFFFFF',
        bold=True,
    )

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.border = border
        cell.alignment = Alignment(
            horizontal='center',
            vertical='center',
            wrap_text=True,
        )

    for row in ws.iter_rows(
        min_row=2,
    ):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(
                vertical='top',
                wrap_text=True,
            )

    ws.freeze_panes = 'A2'

    ws.auto_filter.ref = (
        f'A1:'
        f'{get_column_letter(ws.max_column)}'
        f'{ws.max_row}'
    )

    # Физически сортируем строки по статусу
    # А -> Я.
    #
    # "неустранено" будет выше
    # "устранено".
    status_column_index = None

    for column_index in range(
        1,
        ws.max_column + 1,
    ):
        if (
            normalize_text(
                ws.cell(
                    row=1,
                    column=column_index,
                ).value
            )
            == normalize_text(
                STATUS_COLUMN
            )
        ):
            status_column_index = (
                column_index
            )
            break

    if (
        status_column_index
        and ws.max_row > 2
    ):
        data = [
            [
                ws.cell(
                    row=row_index,
                    column=column_index,
                ).value
                for column_index
                in range(
                    1,
                    ws.max_column + 1,
                )
            ]
            for row_index
            in range(
                2,
                ws.max_row + 1,
            )
        ]

        data.sort(
            key=lambda row: (
                str(
                    row[
                        status_column_index - 1
                    ]
                    or ''
                ).casefold()
            )
        )

        for row_offset, values in enumerate(
            data,
            start=2,
        ):
            for column_index, value in enumerate(
                values,
                start=1,
            ):
                ws.cell(
                    row=row_offset,
                    column=column_index,
                    value=value,
                )

    widths = {
        'IP': 18,
        'FQDN': 35,
        'Описание': 55,
        'Способ устранения': 55,
        'CVE': 22,
        'CVSS': 12,
        'Уровень опасности': 20,
        VULNERABILITY_ID_COLUMN: 30,
        STATUS_COLUMN: 18,
    }

    for column_index in range(
        1,
        ws.max_column + 1,
    ):
        header = _clean_value(
            ws.cell(
                row=1,
                column=column_index,
            ).value
        )

        ws.column_dimensions[
            get_column_letter(
                column_index
            )
        ].width = widths.get(
            header,
            20,
        )

    wb.save(
        result_file
    )

    wb.close()


def _create_result_file(
    ticket_dir: Path,
    result_dir: Path,
    original_file: Path,
    rescan_file: Path,
) -> Path:
    """
    Сравнивает оригинал и перескан
    и создаёт итоговый Excel.
    """
    original_df = pd.read_excel(
        original_file
    )

    rescan_df = pd.read_excel(
        rescan_file
    )

    result_df = (
        _build_result_dataframe(
            original_df=original_df,
            rescan_df=rescan_df,
        )
    )

    date_string = (
        datetime.now().strftime(
            '%d.%m.%Y'
        )
    )

    result_file = (
        result_dir
        / (
            f'{ticket_dir.name}'
            f'_проверка_'
            f'{date_string}.xlsx'
        )
    )

    # Если в этот же день режим запустили
    # повторно, старый результат не затираем.
    if result_file.exists():
        timestamp = (
            datetime.now().strftime(
                '%H%M%S'
            )
        )

        result_file = (
            result_dir
            / (
                f'{ticket_dir.name}'
                f'_проверка_'
                f'{date_string}_'
                f'{timestamp}.xlsx'
            )
        )

    result_df.to_excel(
        result_file,
        index=False,
    )

    _format_result_excel(
        result_file
    )

    unresolved_count = int(
        (
            result_df[STATUS_COLUMN]
            == 'неустранено'
        ).sum()
    )

    resolved_count = int(
        (
            result_df[STATUS_COLUMN]
            == 'устранено'
        ).sum()
    )

    logger.info(
        'Создан результат перескана | '
        'ticket=%s | original=%s | '
        'rescan=%s | resolved=%s | '
        'unresolved=%s | result=%s',
        ticket_dir.name,
        original_file.name,
        rescan_file.name,
        resolved_count,
        unresolved_count,
        result_file,
    )

    return result_file


def _move_rescan_to_archive(
    rescan_file: Path,
    archive_dir: Path,
) -> Path:
    """
    Перемещает успешно обработанный
    перескан в Результат/Архив.
    """
    destination = (
        archive_dir
        / rescan_file.name
    )

    if destination.exists():
        timestamp = (
            datetime.now().strftime(
                '%Y%m%d_%H%M%S'
            )
        )

        destination = (
            archive_dir
            / (
                f'{rescan_file.stem}_'
                f'{timestamp}'
                f'{rescan_file.suffix}'
            )
        )

    shutil.move(
        str(rescan_file),
        str(destination),
    )

    logger.info(
        'Перескан перемещён в архив: %s',
        destination,
    )

    return destination


def _prepare_ticket_directory(
    ticket_dir: Path,
) -> None:
    """
    Подготавливает одну заявку:
    - Результат;
    - Результат/Архив;
    - шаблон.txt.

    Если Excel пока один, сравнение
    не выполняется.
    """
    result_dir, archive_dir = (
        _ensure_result_directories(
            ticket_dir
        )
    )

    excel_files = _get_excel_files(
        ticket_dir
    )

    if not excel_files:
        logger.warning(
            'В заявке %s нет Excel-файлов',
            ticket_dir.name,
        )
        return

    # Самый старый Excel считаем оригиналом.
    original_file = min(
        excel_files,
        key=lambda path: (
            path.stat().st_mtime,
            path.name,
        ),
    )

    _create_template_if_missing(
        ticket_dir=ticket_dir,
        original_file=original_file,
    )

    if len(excel_files) == 1:
        logger.info(
            'Заявка %s подготовлена. '
            'Перескан пока отсутствует.',
            ticket_dir.name,
        )
        return

    if len(excel_files) > 2:
        logger.error(
            'В заявке %s найдено больше '
            'двух Excel-файлов: %s. '
            'Сравнение пропущено.',
            ticket_dir.name,
            [
                path.name
                for path in excel_files
            ],
        )
        return

    original_file, rescan_file = (
        _get_original_and_rescan(
            excel_files
        )
    )

    # Сначала полностью создаём результат.
    # Если здесь возникнет ошибка,
    # перескан останется в корне заявки.
    _create_result_file(
        ticket_dir=ticket_dir,
        result_dir=result_dir,
        original_file=original_file,
        rescan_file=rescan_file,
    )

    # Только после успешного формирования
    # результата переносим перескан.
    _move_rescan_to_archive(
        rescan_file=rescan_file,
        archive_dir=archive_dir,
    )


def run_rescan_mode(
    settings: Settings,
) -> int:
    """
    Запускает режим "Пересканировать"
    для всех числовых папок заявок.

    Используется тот же network_tasks_dir,
    в котором основной режимсоздаёт
    папки заявок.
    """
    tasks_dir = Path(
        settings.dispatch.network_tasks_dir
    )

    ticket_directories = (
        _get_ticket_directories(
            tasks_dir
        )
    )

    logger.info(
        'Запуск режима пересканирования. '
        'Папок заявок: %s',
        len(ticket_directories),
    )

    processed = 0
    failed = 0

    for ticket_dir in ticket_directories:
        try:
            _prepare_ticket_directory(
                ticket_dir
            )

            processed += 1

        except Exception:
            failed += 1

            logger.exception(
                'Ошибка режима перескана '
                'для заявки %s',
                ticket_dir.name,
            )

    logger.info(
        'Режим пересканирования завершён. '
        'Обработано=%s | ошибок=%s',
        processed,
        failed,
    )

    return processed