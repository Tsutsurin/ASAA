"""Модуль фильтрации получателей через Active Directory (LDAP)."""

import logging
from dataclasses import dataclass

from ldap3 import ALL, Connection, Server
from ldap3.utils.conv import escape_filter_chars

from .blacklist_service import (
    is_blocked,
    load_blacklist,
)
from .config import RecipientFilterSettings
from .utils import normalize_text, split_emails

logger = logging.getLogger('auto_responsible.ad_user')


@dataclass
class AdUser:
    email: str
    display_name: str
    title: str
    department: str


def title_allowed(
    title: str,
    allowed_titles: list[str],
) -> bool:
    normalized_title = normalize_text(title)

    if not normalized_title:
        return False

    allowed = {
        normalize_text(item)
        for item in allowed_titles
        if normalize_text(item)
    }

    return normalized_title in allowed


def _get_ad_connection(
    settings: RecipientFilterSettings,
) -> Connection:
    if not settings.ldap_password:
        raise ValueError(
            'Не найдена переменная окружения '
            f'с LDAP-паролем: {settings.ldap_password_env}'
        )

    server = Server(
        settings.ldap_server,
        get_info=ALL,
    )

    return Connection(
        server=server,
        user=settings.ldap_user,
        password=settings.ldap_password,
        auto_bind=True,
    )


def _get_user_by_email(
    conn: Connection,
    search_base: str,
    email: str,
) -> AdUser | None:
    safe_email = escape_filter_chars(email)

    conn.search(
        search_base=search_base,
        search_filter=f'(mail={safe_email})',
        attributes=[
            'displayName',
            'mail',
            'title',
            'department',
        ],
    )

    if not conn.entries:
        logger.warning(
            'AD: пользователь не найден: %s',
            email,
        )
        return None

    entry = conn.entries[0]

    return AdUser(
        email=str(
            entry.mail or email
        ).strip(),
        display_name=str(
            entry.displayName or ''
        ).strip(),
        title=str(
            entry.title or ''
        ).strip(),
        department=str(
            entry.department or ''
        ).strip(),
    )


def _get_safe_fallback(
    settings: RecipientFilterSettings,
    blacklist: list[str],
) -> tuple[str, str]:
    fallback_to = str(
        settings.fallback_to or ''
    ).strip()

    if not fallback_to:
        raise RuntimeError(
            'Fallback получатель не настроен'
        )

    fallback_emails = split_emails(
        fallback_to
    )

    safe_emails = []

    for email in fallback_emails:
        if is_blocked(
            email=email,
            blacklist=blacklist,
        ):
            logger.error(
                'Fallback находится в черном списке: %s',
                email,
            )
            continue

        safe_emails.append(email)

    if not safe_emails:
        raise RuntimeError(
            'Все fallback-получатели находятся '
            'в черном списке'
        )

    fallback_cc = (
        str(settings.fallback_cc).strip()
        if settings.fallback_cc
        else ''
    )

    return (
        '; '.join(safe_emails),
        fallback_cc,
    )


def resolve_dispatch_recipients(
    raw_emails: str,
    default_to: str,
    settings: RecipientFilterSettings,
) -> tuple[str, str | None]:
    blacklist = load_blacklist(
        settings.blacklist_file
    )

    source_emails = split_emails(
        raw_emails or default_to
    )

    source_emails = [
        email
        for email in source_emails
        if not is_blocked(
            email=email,
            blacklist=blacklist,
        )
    ]

    if not settings.enabled:
        if source_emails:
            return '; '.join(source_emails), None

        return _get_safe_fallback(
            settings=settings,
            blacklist=blacklist,
        )

    logger.info(
        'AD-фильтр включен. '
        'Блэклист: %s адресов',
        len(blacklist),
    )

    if not source_emails:
        logger.warning(
            'AD-фильтр: список пуст. Используется fallback.'
        )

        return _get_safe_fallback(
            settings=settings,
            blacklist=blacklist,
        )

    conn = _get_ad_connection(settings)

    try:
        allowed_emails = []

        for email in source_emails:
            user = _get_user_by_email(
                conn=conn,
                search_base=settings.search_base,
                email=email,
            )

            if user is None:
                continue

            logger.info(
                'AD: %s | Должность=%s | Отдел=%s',
                user.email,
                user.title,
                user.department,
            )

            if title_allowed(
                title=user.title,
                allowed_titles=settings.allowed_titles,
            ):
                allowed_emails.append(
                    user.email
                )

                logger.info(
                    'Получатель разрешен: %s | %s',
                    user.email,
                    user.title,
                )

            else:
                logger.info(
                    'Получатель исключен по должности: %s | %s',
                    user.email,
                    user.title,
                )

        allowed_emails = list(
            dict.fromkeys(allowed_emails)
        )

        if not allowed_emails:
            logger.warning(
                'AD-фильтр: подходящих получателей нет. '
                'Используется fallback.'
            )

            return _get_safe_fallback(
                settings=settings,
                blacklist=blacklist,
            )

        max_recipients = settings.max_recipients

        if (
            max_recipients > 0
            and len(allowed_emails) > max_recipients
        ):
            logger.warning(
                'AD-фильтр: %s → %s получателей',
                len(allowed_emails),
                max_recipients,
            )

            allowed_emails = allowed_emails[
                :max_recipients
            ]

        return '; '.join(allowed_emails), None

    finally:
        conn.unbind()