import logging
import time
from pathlib import Path

from ad_user_service import resolve_dispatch_recipients
from config import BASE_DIR, Settings
from exchange_client import (
    download_excel_attachments,
    find_latest_email_in_folder,
    mark_as_read,
)
from exchange_sender import send_html_email
from group_report_splitter import split_report_by_group
from html_template import render_html_template
from ticket_number_service import (
    copy_report_to_ticket_folder,
    create_ticket_folder,
    get_max_ticket_number,
)
from ticket_registry import append_ticket_to_registry

logger = logging.getLogger('auto_responsible.dispatch')


def build_ticket_subject(base_subject: str, ticket_number: int) -> str:
    if base_subject.endswith('№'):
        return f'{base_subject}{ticket_number}'

    if base_subject.endswith('№ '):
        return f'{base_subject}{ticket_number}'

    return f'{base_subject} №{ticket_number}'


def wait_before_next_email(settings: Settings) -> None:
    pause = settings.dispatch.pause_between_emails_seconds

    if pause > 0:
        time.sleep(pause)


def process_dispatch_excel_file(
    settings: Settings,
    account,
    source_file: Path,
) -> int:
    output_dir = (
        BASE_DIR
        / settings.dispatch.output_dir
        / source_file.stem
    )

    group_reports = split_report_by_group(
        source_file=source_file,
        output_dir=output_dir,
        group_column=settings.dispatch.group_column,
        ip_column=settings.dispatch.ip_column,
        fqdn_column=settings.dispatch.fqdn_column,
        vulnerability_column=settings.dispatch.vulnerability_column,
    )

    tasks_dir = Path(settings.dispatch.network_tasks_dir)
    registry_file = Path(settings.dispatch.registry_file)

    next_ticket_number = get_max_ticket_number(tasks_dir) + 1

    normal_template_path = BASE_DIR / settings.dispatch.template_path
    no_group_template_path = BASE_DIR / settings.dispatch.no_group_template_path

    created_count = 0
    failed_count = 0
    max_emails = settings.dispatch.max_emails_per_run

    for group_report in group_reports:
        if max_emails > 0 and created_count >= max_emails:
            logger.warning(
                'Достигнут лимит писем за запуск: %s. Остальные группы не обработаны.',
                max_emails,
            )
            break

        try:
            if group_report.has_group:
                ticket_number = next_ticket_number
                next_ticket_number += 1

                ticket_folder = create_ticket_folder(
                    tasks_dir=tasks_dir,
                    ticket_number=ticket_number,
                )

                report_in_ticket_folder = copy_report_to_ticket_folder(
                    report_file=group_report.file_path,
                    ticket_folder=ticket_folder,
                )

                append_ticket_to_registry(
                    registry_file=registry_file,
                    registry_columns=settings.dispatch.registry_columns,
                    ticket_number=ticket_number,
                    group_name=group_report.display_name,
                    ip_or_fqdn=group_report.ip_or_fqdn,
                    vulnerability_id=group_report.vulnerability_ids,
                    status=settings.dispatch.status_value,
                )

                html_body = render_html_template(
                    template_path=normal_template_path,
                    placeholder=settings.dispatch.placeholder,
                    group_name=group_report.display_name,
                )

                filtered_to, filtered_cc = resolve_dispatch_recipients(
                    raw_emails=group_report.emails,
                    default_to=settings.dispatch.to,
                    settings=settings.dispatch.recipient_filter,
                )

                logger.info(
                    'Получатели после фильтрации для группы %s: to=%s | cc=%s',
                    group_report.display_name,
                    filtered_to,
                    filtered_cc or settings.dispatch.cc,
                )

                send_html_email(
                    account=account,
                    to=filtered_to,
                    cc=filtered_cc or settings.dispatch.cc,
                    subject=build_ticket_subject(
                        settings.dispatch.subject,
                        ticket_number,
                    ),
                    html_body=html_body,
                    attachments=[group_report.file_path],
                )

                logger.info(
                    'Создана и отправлена заявка %s для группы %s | файл в заявке: %s',
                    ticket_number,
                    group_report.display_name,
                    report_in_ticket_folder,
                )

            else:
                html_body = render_html_template(
                    template_path=no_group_template_path,
                    placeholder=settings.dispatch.placeholder,
                    group_name=group_report.display_name,
                )

                send_html_email(
                    account=account,
                    to=settings.dispatch.no_group_to,
                    cc=settings.dispatch.no_group_cc,
                    subject=settings.dispatch.no_group_subject,
                    html_body=html_body,
                    attachments=[group_report.file_path],
                )

                logger.info(
                    'Отправлено письмо для строк без группы без номера заявки'
                )

            created_count += 1
            wait_before_next_email(settings)

        except Exception:
            failed_count += 1

            logger.exception(
                'Ошибка отправки/создания заявки для группы: %s',
                group_report.display_name,
            )

    if failed_count > 0:
        raise RuntimeError(
            f'Ошибки при отправке писем: {failed_count}. '
            f'Успешно отправлено: {created_count}. '
            f'Исходный файл не должен архивироваться.'
        )

    logger.info(
        'Обработка Excel-файла на отработку завершена: %s | отправлено писем: %s',
        source_file,
        created_count,
    )

    return created_count


def process_dispatch_folder(settings: Settings, account) -> bool:
    if not settings.dispatch.enabled:
        logger.info('Сценарий Отработать отключен')
        return False

    message = find_latest_email_in_folder(
        account=account,
        folder_name=settings.dispatch_folder,
        only_unread=settings.only_unread,
        subject_contains='[отработать]',
    )

    if message is None:
        logger.info('В папке Отработать нет подходящих писем')
        return False

    logger.info(
        'Найдено письмо на отработку: subject=%s',
        str(message.subject or ''),
    )

    excel_files = download_excel_attachments(message)

    if not excel_files:
        logger.warning('В письме Отработать нет Excel-вложений')
        return False

    source_file = excel_files[0]

    process_dispatch_excel_file(
        settings=settings,
        account=account,
        source_file=source_file,
    )

    mark_as_read(message)

    logger.info('Сценарий Отработать из почты завершен')

    return True