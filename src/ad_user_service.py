"""Модуль фильтрации получателей через Active Directory (LDAP)."""

import logging
from dataclasses import dataclass

from ldap3 import ALL, Connection, Server

from src.blacklist_service import is_blocked, load_blacklist
from src.config import RecipientFilterSettings
from src.utils import normalize_text, split_emails

logger = logging.getLogger('auto_responsible.ad_user')


@dataclass
class AdUser:
    email: str
    display_name: str
    title: str
    department: str


def title_allowed(title: str, allowed_titles: list[str]) -> bool:
    normalized = normalize_text(title)
    if not normalized:
        return False
    allowed = {normalize_text(t) for t in allowed_titles if normalize_text(t)}
    return normalized in allowed


def _get_ad_connection(settings: RecipientFilterSettings) -> Connection:
    if not settings.ldap_password:
        raise ValueError(
            f'Не найдена переменная окружения с LDAP-паролем: '
            f'{settings.ldap_password_env}'
        )

    server = Server(settings.ldap_server, get_info=ALL)
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
    conn.search(
        search_base=search_base,
        search_filter=f'(mail={email})',
        attributes=['displayName', 'mail', 'title', 'department'],
    )

    if not conn.entries:
        logger.warning('AD: пользователь не найден: %s', email)
        return None

    entry = conn.entries[0]
    return AdUser(
        email=str(entry.mail or email).strip(),
        display_name=str(entry.displayName or '').strip(),
        title=str(entry.title or '').strip(),
        department=str(entry.department or '').strip(),
    )


def resolve_dispatch_recipients(
    raw_emails: str,
    default_to: str,
    settings: RecipientFilterSettings,
) -> tuple[str, str | None]:
    if not settings.enabled:
        return raw_emails or default_to, None

    blacklist = load_blacklist(settings.blacklist_file)

    logger.info(
        'AD-фильтр включен. Блэклист: %s адресов',
        len(blacklist),
    )

    source_emails = split_emails(raw_emails or default_to)

    if not source_emails:
        logger.warning('AD-фильтр: список пуст, fallback: %s', settings.fallback_to)
        return settings.fallback_to, settings.fallback_cc

    conn = _get_ad_connection(settings)

    try:
        allowed_emails = []

        for email in source_emails:
            if is_blocked(email=email, blacklist=blacklist):
                logger.warning('Заблокирован: %s', email)
                continue

            user = _get_user_by_email(
                conn=conn,
                search_base=settings.search_base,
                email=email,
            )

            if user is None:
                continue

            logger.info(
                'AD: %s | %s | %s | %s',
                user.email,
                user.display_name,
                user.title,
                user.department,
            )

            if title_allowed(title=user.title, allowed_titles=settings.allowed_titles):
                allowed_emails.append(user.email)
                logger.info('Разрешён: %s | %s', user.email, user.title)
            else:
                logger.info('Исключён: %s | %s', user.email, user.title)

        allowed_emails = list(dict.fromkeys(allowed_emails))

        if not allowed_emails:
            logger.warning('AD-фильтр: нет подходящих, fallback: %s', settings.fallback_to)
            return settings.fallback_to, settings.fallback_cc

        limited = allowed_emails[:settings.max_recipients]

        if len(allowed_emails) > settings.max_recipients:
            logger.warning(
                'AD-фильтр: %s → %s (лимит)',
                len(allowed_emails),
                settings.max_recipients,
            )

        return '; '.join(limited), None

    finally:
        conn.unbind()