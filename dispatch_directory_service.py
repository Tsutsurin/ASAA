import logging
import shutil
from datetime import datetime
from pathlib import Path

from config import Settings, TEMP_DIR
from dispatch_service import process_dispatch_excel_file

logger = logging.getLogger('auto_responsible.dispatch_directory')


def is_excel_file(path: Path) -> bool:
    return path.suffix.lower() in {'.xlsx', '.xls'}


def get_excel_files(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        logger.warning('Папка отработки не существует: %s', input_dir)
        return []

    files = [
        path for path in input_dir.iterdir()
        if path.is_file() and is_excel_file(path)
    ]

    return sorted(files, key=lambda path: path.stat().st_mtime)


def make_work_copy(source_file: Path) -> Path:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    work_file = TEMP_DIR / f'{timestamp}_{source_file.name}'

    shutil.copy2(source_file, work_file)

    logger.info(
        'Файл отработки скопирован для обработки: %s -> %s',
        source_file,
        work_file,
    )

    return work_file


def archive_or_delete_source(
    source_file: Path,
    archive_dir: Path | None,
    delete_after_processing: bool,
) -> None:
    if delete_after_processing:
        source_file.unlink()
        logger.info('Исходный файл отработки удален: %s', source_file)
        return

    if archive_dir is None:
        logger.info(
            'Архив не указан, исходный файл отработки оставлен: %s',
            source_file,
        )
        return

    archive_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_file = archive_dir / f'{timestamp}_{source_file.name}'

    shutil.move(str(source_file), str(archive_file))

    logger.info(
        'Исходный файл отработки перемещен в архив: %s',
        archive_file,
    )


def process_dispatch_directory(
    settings: Settings,
    account,
) -> bool:
    if not settings.dispatch_directory.enabled:
        logger.info('Сценарий отработки из папки отключен')
        return False

    input_dir = Path(settings.dispatch_directory.input_dir)

    archive_dir = (
        Path(settings.dispatch_directory.archive_dir)
        if settings.dispatch_directory.archive_dir
        else None
    )

    files = get_excel_files(input_dir)

    if not files:
        logger.info('В папке отработки нет Excel-файлов')
        return False

    processed_any = False

    for source_file in files:
        logger.info(
            'Начинаю обработку файла из папки отработки: %s',
            source_file,
        )

        work_file = make_work_copy(source_file)

        try:
            process_dispatch_excel_file(
                settings=settings,
                account=account,
                source_file=work_file,
            )

        except Exception:
            logger.exception(
                'Ошибка обработки файла отработки. '
                'Исходный файл НЕ будет архивирован: %s',
                source_file,
            )
            continue

        archive_or_delete_source(
            source_file=source_file,
            archive_dir=archive_dir,
            delete_after_processing=(
                settings.dispatch_directory.delete_after_processing
            ),
        )

        processed_any = True

        logger.info(
            'Файл из папки отработки обработан: %s',
            source_file,
        )

    return processed_any