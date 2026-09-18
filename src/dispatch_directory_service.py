"""Обработка файлов из сетевой директории "Отработать"."""

import logging
import shutil
from datetime import datetime
from pathlib import Path

from .config import Settings
from .dispatch_processor import process_dispatch_excel_file

logger = logging.getLogger(
    'auto_responsible.dispatch_directory'
)


def _is_excel_file(file_path: Path) -> bool:
    """Проверяет, является ли файл Excel-файлом."""
    if not file_path.is_file():
        return False

    if file_path.name.startswith('~$'):
        return False

    return file_path.suffix.lower() in {
        '.xlsx',
        '.xlsm',
    }


def find_dispatch_files(
    directory: Path,
) -> list[Path]:
    """
    Возвращает Excel-файлы из директории
    "Отработать".
    """
    if not directory.exists():
        logger.warning(
            'Директория "Отработать" '
            'не существует: %s',
            directory,
        )
        return []

    if not directory.is_dir():
        logger.error(
            'Путь "Отработать" '
            'не является директорией: %s',
            directory,
        )
        return []

    files = [
        file_path
        for file_path in directory.iterdir()
        if _is_excel_file(file_path)
    ]

    files.sort(
        key=lambda path: path.stat().st_mtime
    )

    logger.info(
        'В директории "Отработать" '
        'найдено файлов: %s',
        len(files),
    )

    return files


def make_work_copy(
    source_file: Path,
) -> Path:
    """
    Создаёт рабочую копию исходного файла.

    Временное имя содержит timestamp, чтобы
    избежать конфликтов между файлами.

    ВАЖНО:
    это имя не должно попадать в колонку
    "Система" общего реестра заявок.
    """
    timestamp = datetime.now().strftime(
        '%Y%m%d_%H%M%S_%f'
    )

    work_file = source_file.with_name(
        f'{timestamp}_{source_file.name}'
    )

    shutil.copy2(
        source_file,
        work_file,
    )

    logger.info(
        'Создана рабочая копия: %s -> %s',
        source_file,
        work_file,
    )

    return work_file


def _move_file(
    source_file: Path,
    destination_dir: Path,
) -> Path:
    """Перемещает файл в указанную директорию."""
    destination_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination_file = (
        destination_dir
        / source_file.name
    )

    if destination_file.exists():
        timestamp = datetime.now().strftime(
            '%Y%m%d_%H%M%S'
        )

        destination_file = (
            destination_dir
            / (
                f'{source_file.stem}_'
                f'{timestamp}'
                f'{source_file.suffix}'
            )
        )

    shutil.move(
        str(source_file),
        str(destination_file),
    )

    return destination_file


def archive_dispatch_file(
    source_file: Path,
    archive_dir: Path,
) -> Path:
    """
    Перемещает успешно обработанный
    исходный файл в архив.
    """
    archived_file = _move_file(
        source_file=source_file,
        destination_dir=archive_dir,
    )

    logger.info(
        'Исходный файл перемещён в архив: %s',
        archived_file,
    )

    return archived_file


def move_dispatch_file_to_error(
    source_file: Path,
    error_dir: Path,
) -> Path:
    """
    Перемещает исходный файл в директорию
    ошибок.
    """
    error_file = _move_file(
        source_file=source_file,
        destination_dir=error_dir,
    )

    logger.error(
        'Исходный файл перемещён '
        'в директорию ошибок: %s',
        error_file,
    )

    return error_file


def _remove_work_file(
    work_file: Path,
) -> None:
    """Удаляет временную рабочую копию."""
    try:
        if work_file.exists():
            work_file.unlink()

            logger.info(
                'Рабочая копия удалена: %s',
                work_file,
            )

    except Exception:
        logger.exception(
            'Не удалось удалить '
            'рабочую копию: %s',
            work_file,
        )


def process_dispatch_directory(
    settings: Settings,
    account,
) -> int:
    """
    Обрабатывает все Excel-файлы
    из директории "Отработать".

    Для каждого файла:
    1. Сохраняет оригинальное имя.
    2. Создаёт рабочую копию.
    3. Передаёт копию в dispatch_processor.
    4. В общий реестр передаётся именно
       оригинальное имя файла.
    5. После успешной обработки исходный
       файл перемещается в архив.
    """

    source_dir = Path(
        settings.dispatch.source_dir
    )

    archive_dir = Path(
        settings.dispatch.archive_dir
    )

    error_dir = Path(
        settings.dispatch.error_dir
    )

    source_files = find_dispatch_files(
        source_dir
    )

    processed_count = 0

    for source_file in source_files:
        # КРИТИЧНО:
        # сохраняем имя ДО создания
        # временной рабочей копии.
        original_file_name = (
            source_file.name
        )

        logger.info(
            'Начинаю обработку файла: %s',
            original_file_name,
        )

        work_file = None

        try:
            work_file = make_work_copy(
                source_file
            )

            process_dispatch_excel_file(
                settings=settings,
                account=account,
                source_file=work_file,
                original_file_name=(
                    original_file_name
                ),
            )

            archive_dispatch_file(
                source_file=source_file,
                archive_dir=archive_dir,
            )

            processed_count += 1

            logger.info(
                'Обработка файла завершена: %s',
                original_file_name,
            )

        except Exception:
            logger.exception(
                'Ошибка обработки файла: %s',
                original_file_name,
            )

            try:
                if source_file.exists():
                    move_dispatch_file_to_error(
                        source_file=source_file,
                        error_dir=error_dir,
                    )

            except Exception:
                logger.exception(
                    'Не удалось переместить '
                    'исходный файл в ошибки: %s',
                    source_file,
                )

        finally:
            if work_file is not None:
                _remove_work_file(
                    work_file
                )

    logger.info(
        'Обработка директории завершена. '
        'Успешно обработано файлов: %s',
        processed_count,
    )

    return processed_count