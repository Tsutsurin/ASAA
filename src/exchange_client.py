"""Модуль работы с Exchange Web Services (EWS): подключение."""

import logging

from exchangelib import (
    Account,
    Configuration,
    Credentials,
    DELEGATE,
    NTLM,
)
from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter

from src.config import EwsSettings

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