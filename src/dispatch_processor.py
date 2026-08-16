"""Модуль обработки Excel-файлов на отработку (создание заявок и рассылка)."""

import logging
import time
from pathlib import Path

from openpyxl import load_workbook

from src.ad_user_service import resolve_dispatch_recipients
from src.blacklist_service import is_blocked, load_blacklist
from src.config import BASE_DIR, Settings
from src.exchange_sender import send_html_email
from src.group_report_splitter import split_report_by_group
from src.html_template import render_html_template
from src.service_routing import get_service_recipients, load_service_routing
from src.ticket_number_service import (
    copy_report_to_ticket_folder,
    create_ticket_folder,
    get_max_ticket_number,
)
from src.ticket_registry import append_ticket_to_registry
from src.utils import join_emails, normalize_text

logger = logging.getLogger('auto_responsible.dispatch')


def _build_ticket_subject(base: str, number: int) -> str:
    base = base.rstrip()
    if base.endswith('№'):
        return f'{base}{number}'
    return f'{base} №{number}'


def _wait_before_next(settings: Settings) -> None:
    pause = settings.dispatch.pause_between_emails_seconds
    if pause > 0:
        time.sleep(pause)


def _remove_attachment_columns(file_path: Path, names: list[str]) -> None:
    if not names:
        return

    targets = {normalize_text(n) for n in names if normalize_text(n)}
    if not targets:
        return

    wb = load_workbook(file_path)
    ws = wb.active

    to_delete = [
        col_idx
        for col_idx in range(1, ws.max_column + 1)
        if normalize_text(ws.cell(row=1, column=col_idx).value) in targets
    ]

    if not to_delete:
        wb.close()
        logger.info('Колонки для удаления не найдены: %s', names)
        return

    for col_idx in sorted(to_delete, reverse=True):
        ws.delete_cols(col_idx)

    wb.save(file_path)
    wb.close()

    logger.info('Из вложения удалены колонки: %s', names)


def _filter_blocked(raw_emails: str, blacklist_file: str | None, context: str) -> list[str]:
    """Фильтрация email по блэклисту."""
    blacklist = load_blacklist(blacklist_file)
    allowed = []
    for email in join_emails(raw_emails).split('; ') if raw_emails else []:
        if not email:
            continue
        if is_blocked(email=email, blacklist=blacklist):
            logger.warning('Заблокирован черным списком: %s | %s', email, context)
            continue
        allowed.append(email)
    return list(dict.fromkeys(allowed))


def _filter_and_limit(raw_emails: str, settings: Settings, context: str) -> list[str]:
    """Фильтрация по блэклисту + лимит количества получателей."""
    blacklist_file = settings.dispatch.recipient_filter.blacklist_file
    allowed = _filter_blocked(
        raw_emails=raw_emails,
        blacklist_file=blacklist_file,
        context=context,
    )

    max_recipients = settings.dispatch.recipient_filter.max_recipients
    if max_recipients > 0 and len(allowed) > max_recipients:
        logger.warning(
            'Лимит получателей: %s → %s | %s',
            len(allowed),
            max_recipients,
            context,
        )
        allowed = allowed[:max_recipients]

    return allowed


def _resolve_recipients(
    group_report,
    settings: Settings,
    service_routing: dict[str, list[str]],
) -> tuple[str, str | None, Path, str, str]:
    """Определение получателей по приоритетам.

    Returns:
        (to, cc, template_path, template_value, route_source)
    """
    normal_tpl = BASE_DIR / settings.dispatch.template_path
    service_tpl = BASE_DIR / settings.dispatch.service_template_path

    # 1. Ручной ввод — минуя всё, только блеклист
    if group_report.manual_emails:
        recipients = _filter_and_limit(
            raw_emails=group_report.manual_emails,
            settings=settings,
            context=f'manual | {group_report.display_name}',
        )
        if recipients:
            return (
                '; '.join(recipients),
                None,
                normal_tpl,
                group_report.display_name,
                'manual',
            )

    # 2. Жёсткая маршрутизация ИС из столбца — только блеклист
    if group_report.service_routing_emails:
        recipients = _filter_and_limit(
            raw_emails=group_report.service_routing_emails,
            settings=settings,
            context=f'service_routing_column | {group_report.display_name}',
        )
        if recipients:
            return (
                '; '.join(recipients),
                None,
                service_tpl,
                group_report.service_name,
                'service_routing_column',
            )

    # 3. Маршрутизация ИС из JSON (service_routing.json) — только блеклист
    if service_routing and group_report.service_name:
        json_recipients = get_service_recipients(
            service_name=group_report.service_name,
            routing=service_routing,
        )
        if json_recipients:
            recipients = _filter_and_limit(
                raw_emails='; '.join(json_recipients),
                settings=settings,
                context=f'service_routing_json | {group_report.service_name}',
            )
            if recipients:
                return (
                    '; '.join(recipients),
                    None,
                    service_tpl,
                    group_report.service_name,
                    'service_routing_json',
                )

    # 4. Ответственный ИС / Администратор ИС — только блеклист
    if group_report.service_owner_admin:
        recipients = _filter_and_limit(
            raw_emails=group_report.service_owner_admin,
            settings=settings,
            context=f'service_owner_admin | {group_report.service_name}',
        )
        if recipients:
            return (
                '; '.join(recipients),
                None,
                service_tpl,
                group_report.service_name,
                'service_owner_admin',
            )

    # 5. Члены группы — с AD-фильтрацией + блеклист
    if group_report.group_member_emails:
        to, cc = resolve_dispatch_recipients(
            raw_emails=group_report.group_member_emails,
            default_to=settings.dispatch.to,
            settings=settings.dispatch.recipient_filter,
        )
        return (
            to,
            cc,
            normal_tpl,
            group_report.display_name,
            'ad_filter',
        )

    # 6. Fallback — legacy общие почты
    to, cc = resolve_dispatch_recipients(
        raw_emails=group_report.emails,
        default_to=settings.dispatch.to,
        settings=settings.dispatch.recipient_filter,
    )
    return (
        to,
        cc,
        normal_tpl,
        group_report.display_name,
        'ad_filter_fallback',
    )


def process_dispatch_excel_file(
    settings: Settings,
    account,
    source_file: Path,
) -> int:
    """Обработка одного Excel-файла: разделение, создание заявок, рассылка."""
    output_dir = BASE_DIR / settings.dispatch.output_dir / source_file.stem

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

    no_group_tpl = BASE_DIR / settings.dispatch.no_group_template_path
    service_routing = load_service_routing(settings.dispatch.service_routing)

    created_count = 0
    failed_count = 0
    max_emails = settings.dispatch.max_emails_per_run

    for group_report in group_reports:
        if max_emails > 0 and created_count >= max_emails:
            logger.warning('Лимит писем за запуск: %s', max_emails)
            break

        try:
            if group_report.has_group:
                ticket_number = next_ticket_number
                next_ticket_number += 1

                ticket_folder = create_ticket_folder(
                    tasks_dir=tasks_dir,
                    ticket_number=ticket_number,
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

                to, cc, template_path, template_value, route_source = (
                    _resolve_recipients(
                        group_report=group_report,
                        settings=settings,
                        service_routing=service_routing,
                    )
                )

                html_body = render_html_template(
                    template_path=template_path,
                    placeholder=settings.dispatch.placeholder,
                    group_name=template_value,
                )

                _remove_attachment_columns(
                    file_path=group_report.file_path,
                    names=settings.dispatch.attachment_drop_columns,
                )

                report_in_ticket = copy_report_to_ticket_folder(
                    report_file=group_report.file_path,
                    ticket_folder=ticket_folder,
                )

                send_html_email(
                    account=account,
                    to=to,
                    cc=cc or settings.dispatch.cc,
                    subject=_build_ticket_subject(
                        settings.dispatch.subject,
                        ticket_number,
                    ),
                html_body=html_body,
                    attachments=[group_report.file_path],
                )

                logger.info(
                    'Заявка %s | группа=%s | route=%s | файл=%s',
                    ticket_number,
                    group_report.display_name,
                    route_source,
                    report_in_ticket,
                )

            else:
                html_body = render_html_template(
                    template_path=no_group_tpl,
                    placeholder=settings.dispatch.placeholder,
                    group_name=group_report.display_name,
                )

                _remove_attachment_columns(
                    file_path=group_report.file_path,
                    names=settings.dispatch.attachment_drop_columns,
                )

                send_html_email(
                    account=account,
                    to=settings.dispatch.no_group_to,
                    cc=settings.dispatch.no_group_cc,
                    subject=settings.dispatch.no_group_subject,
                    html_body=html_body,
                    attachments=[group_report.file_path],
                )

                logger.info('Письмо без группы отправлено')

            created_count += 1
            _wait_before_next(settings)

        except Exception:
            failed_count += 1
            logger.exception(
                'Ошибка для группы: %s',
                group_report.display_name,
            )

    if failed_count > 0:
        raise RuntimeError(
            f'Ошибки отправки: {failed_count}. '
            f'Успешно: {created_count}. '
            f'Файл не архивируется.'
        )

    logger.info(
        'Файл обработан: %s | писем: %s',
        source_file,
        created_count,
    )

    return created_count