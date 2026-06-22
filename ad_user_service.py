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
    allowed_titles: list[str],
) -> bool:
    normalized_title = normalize(title)

    if not normalized_title:
        return False

    allowed_normalized = {
        normalize(value)
        for value in allowed_titles
        if normalize(value)
    }

    return normalized_title in allowed_normalized


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

    source_emails = split_emails(raw_emails or default_to)

    if not source_emails:
        logger.warning(
            'Фильтр получателей: список почт пустой, используется fallback: %s',
            settings.fallback_to,
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

            logger.info(
                'AD: %s | ФИО=%s | Должность=%s | Отдел=%s',
                user.email,
                user.display_name,
                user.title,
                user.department,
            )

            if title_allowed(
                title=user.title,
                allowed_titles=settings.allowed_titles,
            ):
                allowed_emails.append(user.email)

                logger.info(
                    'Получатель разрешен по должности: %s | %s',
                    user.email,
                    user.title,
                )
            else:
                logger.info(
                    'Получатель исключен по должности: %s | %s',
                    user.email,
                    user.title,
                )

        allowed_emails = list(dict.fromkeys(allowed_emails))

        if not allowed_emails:
            logger.warning(
                'Фильтр получателей: подходящих должностей не найдено. '
                'Используется fallback: %s',
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