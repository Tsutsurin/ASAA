"""Точка входа ASAA. Оркестрирует 3 сценария: отработка, поиск, обогащение."""

import logging

from src.config import BASE_DIR, load_columns, load_settings
from src.dispatch_directory_service import process_dispatch_directory
from src.excel_parser import build_output_report, extract_params_from_files
from src.exchange_client import (
    download_excel_attachments,
    find_latest_email_in_folder,
    get_account,
    mark_as_read,
)
from src.exchange_sender import send_html_email
from src.logger_setup import setup_logging
from src.report_formatter import set_formatter_config
from src.responsible_service import enrich_with_responsibles
from src.search_directory_service import process_search_directory

logger = logging.getLogger('auto_responsible.main')


def process_enrich_folder(settings, columns_config, account) -> bool:
    message = find_latest_email_in_folder(
        account=account,
        folder_name=settings.enrich_folder,
        only_unread=settings.only_unread,
        subject_contains=settings.subject_contains,
    )

    if message is None:
        logger.info('В папке обогащения нет подходящих писем')
        return False

    excel_files = download_excel_attachments(message)

    if not excel_files:
        logger.warning('Excel-вложения не найдены')
        return False

    params = extract_params_from_files(
        files=excel_files,
        columns_config=columns_config,
    )

    if params.empty:
        logger.warning('Входные параметры fqdn/ip не найдены')
        return False

    try:
        enriched = enrich_with_responsibles(
            params=params,
            settings=settings,
        )
    except Exception:
        logger.exception('Ошибка обогащения данных из API')
        return False

    source_file = excel_files[0]

    try:
        build_output_report(
            source_file=source_file,
            enriched_params=enriched,
            output_file=source_file,
            columns_config=columns_config,
        )
    except Exception:
        logger.exception('Ошибка формирования отчета')
        return False

    if settings.send_email.enabled:
        try:
            send_html_email(
                account=account,
                to=settings.send_email.to,
                cc=settings.send_email.cc,
                subject=settings.send_email.subject,
                html_body=settings.send_email.body,
                attachments=[source_file],
            )
        except Exception:
            logger.exception('Ошибка отправки письма с обогащенным отчетом')
            return False

    mark_as_read(message)
    logger.info('Сценарий обогащения завершен')
    return True


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

    try:
        processed_enrich = process_enrich_folder(
            settings=settings,
            columns_config=columns_config,
            account=account,
        )
    except Exception:
        logger.exception('Ошибка сценария обогащения из почты')
        processed_enrich = False

    if (
        not processed_dispatch_directory
        and not processed_search_directory
        and not processed_enrich
    ):
        logger.info('Новых задач для обработки нет')

    logger.info('Обработка завершена')


if __name__ == '__main__':
    main()