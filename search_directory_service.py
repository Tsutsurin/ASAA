import logging
import shutil
from datetime import datetime
from pathlib import Path

from config import Settings, TEMP_DIR
from excel_parser import (
    build_output_report,
    extract_params_from_files,
)
from responsible_service import enrich_with_responsibles

logger = logging.getLogger('auto_responsible.search_directory')


def is_excel_file(path: Path) -> bool:
    return path.suffix.lower() in {'.xlsx', '.xls'}


def get_excel_files(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        logger.warning('Папка поиска не существует: %s', input_dir)
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
        'Файл скопирован для обработки: %s -> %s',
        source_file,
        work_file,
    )

    return work_file


def save_result_file(
    work_file: Path,
    source_file: Path,
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    result_file = output_dir / source_file.name

    if result_file.exists():
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        result_file = output_dir / f'{timestamp}_{source_file.name}'

    shutil.copy2(work_file, result_file)

    logger.info(
        'Обогащенный файл сохранен: %s',
        result_file,
    )

    return result_file


def archive_or_delete_source(
    source_file: Path,
    archive_dir: Path | None,
    delete_after_processing: bool,
) -> None:
    if delete_after_processing:
        source_file.unlink()
        logger.info('Исходный файл удален: %s', source_file)
        return

    if archive_dir is None:
        logger.info(
            'Архив не указан, исходный файл оставлен: %s',
            source_file,
        )
        return

    archive_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_file = archive_dir / f'{timestamp}_{source_file.name}'

    shutil.move(str(source_file), str(archive_file))

    logger.info(
        'Исходный файл перемещен в архив: %s',
        archive_file,
    )


def process_search_directory(
    settings: Settings,
    columns_config: dict[str, list[str]],
    account,
) -> bool:
    if not settings.search_directory.enabled:
        logger.info('Сценарий поиска из папки отключен')
        return False

    input_dir = Path(settings.search_directory.input_dir)
    output_dir = Path(settings.search_directory.output_dir)

    archive_dir = (
        Path(settings.search_directory.archive_dir)
        if settings.search_directory.archive_dir
        else None
    )

    files = get_excel_files(input_dir)

    if not files:
        logger.info('В папке поиска нет Excel-файлов')
        return False

    processed_any = False

    for source_file in files:
        logger.info(
            'Начинаю обработку файла из папки поиска: %s',
            source_file,
        )

        work_file = make_work_copy(source_file)

        params = extract_params_from_files(
            files=[work_file],
            columns_config=columns_config,
        )

        if params.empty:
            logger.warning(
                'В файле не найдены входные параметры fqdn/ip: %s',
                source_file,
            )

            archive_or_delete_source(
                source_file=source_file,
                archive_dir=archive_dir,
                delete_after_processing=(
                    settings.search_directory.delete_after_processing
                ),
            )

            continue

        enriched = enrich_with_responsibles(
            params=params,
            settings=settings,
        )

        build_output_report(
            source_file=work_file,
            enriched_params=enriched,
            output_file=work_file,
            columns_config=columns_config,
        )

        save_result_file(
            work_file=work_file,
            source_file=source_file,
            output_dir=output_dir,
        )

        archive_or_delete_source(
            source_file=source_file,
            archive_dir=archive_dir,
            delete_after_processing=(
                settings.search_directory.delete_after_processing
            ),
        )

        processed_any = True

        logger.info(
            'Файл из папки поиска обработан: %s',
            source_file,
        )

    return processed_any