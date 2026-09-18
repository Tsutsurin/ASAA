"""Точка входа ASAA. Оркестрирует сценарии: отработка, поиск, перескан."""

import logging
import sys

from src.config import BASE_DIR, load_columns, load_settings
from src.dispatch_directory_service import process_dispatch_directory
from src.exchange_client import get_account
from src.logger_setup import setup_logging
from src.report_formatter import set_formatter_config
from src.rescan_service import run_rescan_mode
from src.search_directory_service import process_search_directory

logger = logging.getLogger('auto_responsible.main')


def run_rescan(settings) -> None:
    """Запускает только режим пересканирования."""
    logger.info('Запуск режима Пересканировать')

    try:
        processed = run_rescan_mode(
            settings=settings,
        )

        logger.info(
            'Режим Пересканировать завершён. '
            'Обработано папок: %s',
            processed,
        )

    except Exception:
        logger.exception(
            'Ошибка сценария Пересканировать'
        )
        raise


def run_normal(
    settings,
    columns_config,
) -> None:
    """
    Обычный режим ASAA:
    - Отработать;
    - Поиск.
    """
    logger.info('Старт обработки через EWS')

    account = get_account(settings.ews)

    try:
        processed_dispatch_directory = process_dispatch_directory(
            settings=settings,
            account=account,
        )

    except Exception:
        logger.exception(
            'Ошибка сценария Отработать '
            'из сетевой папки'
        )
        processed_dispatch_directory = False

    try:
        processed_search_directory = process_search_directory(
            settings=settings,
            columns_config=columns_config,
            account=account,
        )

    except Exception:
        logger.exception(
            'Ошибка сценария поиска '
            'из сетевой папки'
        )
        processed_search_directory = False

    if (
        not processed_dispatch_directory
        and not processed_search_directory
    ):
        logger.info(
            'Новых задач для обработки нет'
        )


def main() -> None:
    setup_logging()

    settings = load_settings()
    columns_config = load_columns()

    set_formatter_config(
        BASE_DIR
        / settings.report_formatter_config
    )

    # Отдельный режим перескана.
    #
    # ASAA.exe --rescan
    #
    # В этом режиме Exchange/EWS
    # вообще не подключается.
    if '--rescan' in sys.argv:
        run_rescan(settings)
        logger.info('Обработка завершена')
        return

    # Обычный режим:
    #
    # ASAA.exe
    #
    # Поведение остаётся таким же,
    # как было раньше.
    run_normal(
        settings=settings,
        columns_config=columns_config,
    )

    logger.info('Обработка завершена')


if __name__ == '__main__':
    main()