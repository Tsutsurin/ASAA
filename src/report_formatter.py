import configparser
import logging
import sys
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import (
    Alignment,
    Border,
    Color,
    Font,
    PatternFill,
    Side,
)

logger = logging.getLogger('auto_responsible.formatter')

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

_formatter_config_path: Path | None = None


def set_formatter_config(path: str | Path) -> None:
    """Установка пути к config.ini для форматирования Excel."""
    global _formatter_config_path
    _formatter_config_path = Path(path)
    logger.info('Форматирование Excel: конфиг=%s', _formatter_config_path)


def _get_config_path() -> Path:
    """Получение пути к config.ini."""
    if _formatter_config_path is not None:
        return _formatter_config_path
    return BASE_DIR / 'config.ini'


def load_settings_from_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config.read(_get_config_path(), encoding='utf-8')
    return config


def get_cell_style(config, section, key, default=None):
    try:
        return config.get(section, key)
    except (configparser.NoSectionError, configparser.NoOptionError):
        return default


def get_fill_color(config, section, key, default=None):
    color = get_cell_style(config, section, key, default)
    if color:
        return PatternFill(start_color=color, end_color=color, fill_type='solid')
    return None


def get_font(config, section, key, default=None):
    font_settings = get_cell_style(config, section, key, default)
    if font_settings:
        name, size, bold, color = font_settings.split(',')
        return Font(name=name, size=int(size), bold=bold == 'True', color=color)
    return None


def get_border(config, section, key, default=None):
    border_settings = get_cell_style(config, section, key, default)
    if border_settings:
        style, color = border_settings.split(',')
        side = Side(style=style, color=color)
        return Border(left=side, right=side, top=side, bottom=side)
    return None


def get_alignment(config, section, key, default=None):
    alignment_settings = get_cell_style(config, section, key, default)
    if alignment_settings:
        horizontal, vertical, wrap_text = alignment_settings.split(',')
        return Alignment(
            horizontal=horizontal,
            vertical=vertical,
            wrap_text=wrap_text == 'True',
        )
    return None


def get_width(config, section, key, default=None):
    width = get_cell_style(config, section, key, default)
    if width:
        return float(width)
    return None


def apply_cell_style(ws, cell, config, section):
    fill_color = get_fill_color(config, section, 'fill_color')
    if fill_color:
        cell.fill = fill_color

    font = get_font(config, section, 'font')
    if font:
        cell.font = font

    border = get_border(config, section, 'border')
    if border:
        cell.border = border

    alignment = get_alignment(config, section, 'alignment')
    if alignment:
        cell.alignment = alignment


def apply_header_style(ws, cell, config):
    apply_cell_style(ws, cell, config, 'HeaderStyle')


def apply_data_style(ws, cell, config):
    apply_cell_style(ws, cell, config, 'DataStyle')


def apply_severity_style(ws, cell, severity):
    config = load_settings_from_config()
    section = f'Severity{severity}'
    if not config.has_section(section):
        section = 'SeverityUnknown'
    apply_cell_style(ws, cell, config, section)


def auto_fit_columns(ws, config):
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2)
        ws.column_dimensions[column_letter].width = adjusted_width


def apply_styles(ws, config):
    for row in ws.iter_rows():
        for cell in row:
            if cell.row == 1:
                apply_header_style(ws, cell, config)
            else:
                apply_data_style(ws, cell, config)
                severity = ws.cell(
                    row=cell.row,
                    column=1,
                ).value
                if severity:
                    apply_severity_style(ws, cell, severity)


def stream_transform(file_path: Path) -> None:
    config = load_settings_from_config()

    wb = load_workbook(file_path)
    ws = wb.active

    apply_styles(ws, config)
    auto_fit_columns(ws, config)

    wb.save(file_path)
    logger.info(f'Файл отформатирован: {file_path}')