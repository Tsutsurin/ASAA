import logging

from config import load_columns, load_settings
from dispatch_directory_service import process_dispatch_directory
from dispatch_service import process_dispatch_folder
from excel_parser import (
    build_output_report,
    extract_params_from_files,
)
from exchange_client import (
    download_excel_attachments,
    find_latest_email_in_folder,
    get_account,
    mark_as_read,
)
from exchange_sender import send_html_email
from logger_setup import setup_logging
from responsible_service import enrich_with_responsibles
from search_directory_service import process_search_directory

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

    enriched = enrich_with_responsibles(
        params=params,
        settings=settings,
    )

    source_file = excel_files[0]

    build_output_report(
        source_file=source_file,
        enriched_params=enriched,
        output_file=source_file,
        columns_config=columns_config,
    )

    if settings.send_email.enabled:
        send_html_email(
            account=account,
            to=settings.send_email.to,
            cc=settings.send_email.cc,
            subject=settings.send_email.subject,
            html_body=settings.send_email.body,
            attachments=[source_file],
        )

    mark_as_read(message)

    logger.info('Сценарий обогащения завершен')
    return True


def main() -> None:
    setup_logging()

    settings = load_settings()
    columns_config = load_columns()

    logger.info('Старт обработки через EWS')

    account = get_account(settings.ews)

    try:
        processed_dispatch_mail = process_dispatch_folder(
            settings=settings,
            account=account,
        )
    except Exception:
        logger.exception('Ошибка сценария Отработать из почты')
        processed_dispatch_mail = False

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
        not processed_dispatch_mail
        and not processed_dispatch_directory
        and not processed_search_directory
        and not processed_enrich
    ):
        logger.info('Новых задач для обработки нет')

    logger.info('Обработка завершена')


if __name__ == '__main__':
    main()