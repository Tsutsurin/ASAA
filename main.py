"""Точка входа ASAA. Оркестрирует сценарии: отработка, поиск."""

import logging

from src.config import BASE_DIR, load_columns, load_settings
from src.dispatch_directory_service import process_dispatch_directory
from src.exchange_client import get_account
from src.logger_setup import setup_logging
from src.report_formatter import set_formatter_config
from src.search_directory_service import process_search_directory

logger = logging.getLogger('auto_responsible.main')


def main() -> None:
    setup_logging()

    settings = load_settings()
    columns_config = load_columns()

    set_formatter_config(BASE_DIR / settings.report_formatter_config)

    logger.info('Старт обработки через EWS')

    account = get_account(settings.ews)

    try:
        processed_dispatch_directory = process_dispatch_directory(
            settings=settings,
            account=account,
        )
    except Exception:
        logger.exception('Ошибка сценария Отработать из сетевой папки')
        processed_dispatch_directory = False

    try:
        processed_search_directory = process_search_directory(
            settings=settings,
            columns_config=columns_config,
            account=account,
        )
    except Exception:
        logger.exception('Ошибка сценария поиска из сетевой папки')
        processed_search_directory = False

    if not processed_dispatch_directory and not processed_search_directory:
        logger.info('Новых задач для обработки нет')

    logger.info('Обработка завершена')


if __name__ == '__main__':
    main()