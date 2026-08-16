"""Модуль работы с Exchange Web Services (EWS): подключение, поиск писем, скачивание вложений."""

import logging
from datetime import datetime
from pathlib import Path

from exchangelib import (
    Account,
    Configuration,
    Credentials,
    DELEGATE,
    FileAttachment,
    NTLM,
)
from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter

from src.config import EwsSettings, TEMP_DIR
from src.utils import safe_filename

logger = logging.getLogger('auto_responsible.exchange_client')


def get_account(settings: EwsSettings) -> Account:
    if not settings.verify_ssl:
        BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter

    auth_type = NTLM if settings.auth_type.upper() == 'NTLM' else None

    credentials = Credentials(
        username=settings.username,
        password=settings.password,
    )

    config = Configuration(
        service_endpoint=settings.service_endpoint,
        credentials=credentials,
        auth_type=auth_type,
    )

    account = Account(
        primary_smtp_address=settings.email,
        config=config,
        autodiscover=False,
        access_type=DELEGATE,
    )

    logger.info('EWS подключение: %s', settings.email)
    return account


def _find_folder(account: Account, folder_name: str):
    for folder in account.root.walk():
        if folder.name.lower() == folder_name.lower():
            logger.info('EWS папка: %s', folder.name)
            return folder
    raise ValueError(f'EWS папка не найдена: {folder_name}')


def find_latest_email_in_folder(
    account: Account,
    folder_name: str,
    only_unread: bool = True,
    subject_contains: str | None = None,
):
    folder = _find_folder(account, folder_name)
    items = folder.all().order_by('-datetime_received')

    logger.info('EWS проверяю письма в: %s', folder_name)

    for index, item in enumerate(items[:20], start=1):
        subject = str(item.subject or '')
        is_read = bool(item.is_read)

        attachment_names = [
            attachment.name
            for attachment in item.attachments
            if isinstance(attachment, FileAttachment)
        ]

        logger.info(
            'EWS письмо #%s | read=%s | subject=%r | attachments=%s',
            index,
            is_read,
            subject,
            attachment_names,
        )

        if only_unread and is_read:
            continue

        if subject_contains and subject_contains.lower() not in subject.lower():
            continue

        has_excel = any(
            name.lower().endswith(('.xlsx', '.xls'))
            for name in attachment_names
        )

        if not has_excel:
            continue

        logger.info('EWS найдено письмо: %s', subject)
        return item

    return None


def download_excel_attachments(message) -> list[Path]:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []

    for attachment in message.attachments:
        if not isinstance(attachment, FileAttachment):
            continue

        filename = safe_filename(attachment.name)

        if not filename.lower().endswith(('.xlsx', '.xls')):
            continue

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = TEMP_DIR / f'{timestamp}_{filename}'

        with open(path, 'wb') as file:
            file.write(attachment.content)

        files.append(path)
        logger.info('EWS вложение: %s', path)

    return files


def mark_as_read(message) -> None:
    message.is_read = True
    message.save(update_fields=['is_read'])
    logger.info('EWS письмо прочитано')