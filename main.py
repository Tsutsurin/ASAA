"""Точка входа ASAA."""

import logging
import sys

from src.config import load_settings
from src.logger_setup import setup_logging


logger = logging.getLogger(
    'auto_responsible.main'
)


def run_rescan(settings) -> None:
    from src.rescan_service import (
        run_rescan_mode,
    )

    print('RESCAN MODE STARTED')

    logger.info(
        'Запуск режима Пересканировать'
    )

    try:
        processed = run_rescan_mode(
            settings=settings,
        )

        print(
            'RESCAN FINISHED. '
            f'PROCESSED: {processed}'
        )

        logger.info(
            'Режим Пересканировать завершён. '
            'Обработано папок: %s',
            processed,
        )

    except Exception as exc:
        print(
            'RESCAN ERROR: '
            f'{type(exc).__name__}: {exc}'
        )

        logger.exception(
            'Ошибка сценария Пересканировать'
        )

        raise


def run_feedback(settings) -> None:
    from src.exchange_client import (
        get_account,
    )
    from src.feedback_service import (
        process_feedback,
    )

    print('FEEDBACK MODE STARTED')

    logger.info(
        'Запуск режима обратной связи'
    )

    account = get_account(
        settings.ews
    )

    try:
        processed = process_feedback(
            settings=settings,
            account=account,
        )

        logger.info(
            'Режим обратной связи завершён. '
            'Обработано писем: %s',
            processed,
        )

        print(
            'FEEDBACK FINISHED. '
            f'PROCESSED: {processed}'
        )

    except Exception as exc:
        print(
            'FEEDBACK ERROR: '
            f'{type(exc).__name__}: {exc}'
        )

        logger.exception(
            'Ошибка сценария '
            'обратной связи'
        )

        raise


def run_normal(settings) -> None:
    from src.config import (
        BASE_DIR,
        load_columns,
    )
    from src.dispatch_directory_service import (
        process_dispatch_directory,
    )
    from src.exchange_client import (
        get_account,
    )
    from src.report_formatter import (
        set_formatter_config,
    )
    from src.search_directory_service import (
        process_search_directory,
    )

    logger.info(
        'Запуск обычного режима ASAA'
    )

    columns_config = load_columns()

    set_formatter_config(
        BASE_DIR
        / settings.report_formatter_config
    )

    logger.info(
        'Старт обработки через EWS'
    )

    account = get_account(
        settings.ews
    )

    try:
        processed_dispatch_directory = (
            process_dispatch_directory(
                settings=settings,
                account=account,
            )
        )

    except Exception:
        logger.exception(
            'Ошибка сценария Отработать '
            'из сетевой папки'
        )

        processed_dispatch_directory = False

    try:
        processed_search_directory = (
            process_search_directory(
                settings=settings,
                columns_config=columns_config,
                account=account,
            )
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
    print('ASAA STARTED')

    print(
        f'RAW ARGUMENTS: {sys.argv}'
    )

    setup_logging()

    logger.info(
        'ASAA запущен. Аргументы: %s',
        sys.argv,
    )

    settings = load_settings()

    args = [
        argument.strip().lower()
        for argument in sys.argv[1:]
    ]

    print(
        f'NORMALIZED ARGUMENTS: {args}'
    )

    logger.info(
        'Нормализованные аргументы: %s',
        args,
    )

    if '--rescan' in args:
        print('MODE: RESCAN')

        logger.info(
            'Выбран режим: Пересканировать'
        )

        run_rescan(
            settings=settings,
        )

        logger.info(
            'Обработка завершена'
        )

        print(
            'ASAA RESCAN COMPLETED'
        )

        return

    if '--feedback' in args:
        print('MODE: FEEDBACK')

        logger.info(
            'Выбран режим: '
            'Обратная связь'
        )

        run_feedback(
            settings=settings,
        )

        logger.info(
            'Обработка завершена'
        )

        print(
            'ASAA FEEDBACK COMPLETED'
        )

        return

    print('MODE: NORMAL')

    logger.info(
        'Выбран обычный режим'
    )

    run_normal(
        settings=settings,
    )

    logger.info(
        'Обработка завершена'
    )

    print(
        'ASAA NORMAL COMPLETED'
    )


if __name__ == '__main__':
    main()