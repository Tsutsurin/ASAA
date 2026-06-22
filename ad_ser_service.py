import logging
from dataclasses import dataclass

from ldap3 import ALL, Connection, Server

from config import RecipientFilterSettings

logger = logging.getLogger('auto_responsible.ad_user_service')


@dataclass
class AdUser:
    email: str
    display_name: str
    title: str
    department: str


def split_emails(raw_emails: str) -> list[str]:
    result = []

    for email in str(raw_emails or '').replace(',', ';').split(';'):
        email = email.strip()

        if email:
            result.append(email)

    return list(dict.fromkeys(result))


def normalize(value: str) -> str:
    return str(value or '').strip().lower()


def title_allowed(
    title: str,
    allowed_keywords: list[str],
) -> bool:
    normalized_title = normalize(title)

    if not normalized_title:
        return False

    for keyword in allowed_keywords:
        if normalize(keyword) in normalized_title:
            return True

    return False


def get_ad_connection(settings: RecipientFilterSettings) -> Connection:
    if not settings.ldap_password:
        raise ValueError(
            f'Не найдена переменная окружения с LDAP-паролем: '
            f'{settings.ldap_password_env}'
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


def get_user_by_email(
    conn: Connection,
    search_base: str,
    email: str,
) -> AdUser | None:
    conn.search(
        search_base=search_base,
        search_filter=f'(mail={email})',
        attributes=[
            'displayName',
            'mail',
            'title',
            'department',
        ],
    )

    if not conn.entries:
        logger.warning(
            'AD: пользователь не найден по email: %s',
            email,
        )
        return None

    entry = conn.entries[0]

    return AdUser(
        email=str(entry.mail or email),
        display_name=str(entry.displayName or ''),
        title=str(entry.title or ''),
        department=str(entry.department or ''),
    )


def resolve_dispatch_recipients(
    raw_emails: str,
    default_to: str,
    settings: RecipientFilterSettings,
) -> tuple[str, str | None]:
    if not settings.enabled:
        return raw_emails or default_to, None

    source_emails = split_emails(raw_emails or default_to)

    if not source_emails:
        logger.warning(
            'Фильтр получателей: список почт пустой, используется fallback'
        )
        return settings.fallback_to, settings.fallback_cc

    conn = get_ad_connection(settings)

    try:
        allowed_emails = []

        for email in source_emails:
            user = get_user_by_email(
                conn=conn,
                search_base=settings.search_base,
                email=email,
            )

            if user is None:
                continue

            if title_allowed(
                title=user.title,
                allowed_keywords=settings.allowed_title_keywords,
            ):
                allowed_emails.append(user.email)

                logger.info(
                    'Получатель разрешен: %s | %s | %s',
                    user.email,
                    user.title,
                    user.department,
                )
            else:
                logger.info(
                    'Получатель исключен по должности: %s | %s | %s',
                    user.email,
                    user.title,
                    user.department,
                )

        allowed_emails = list(dict.fromkeys(allowed_emails))

        if not allowed_emails:
            logger.warning(
                'Фильтр получателей: подходящих должностей не найдено, '
                'используется fallback: %s',
                settings.fallback_to,
            )
            return settings.fallback_to, settings.fallback_cc

        limited_emails = allowed_emails[:settings.max_recipients]

        if len(allowed_emails) > settings.max_recipients:
            logger.warning(
                'Фильтр получателей: найдено %s подходящих адресатов, '
                'оставлено максимум %s',
                len(allowed_emails),
                settings.max_recipients,
            )

        return '; '.join(limited_emails), None

    finally:
        conn.unbind()