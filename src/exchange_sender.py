import logging
from pathlib import Path

from exchangelib import FileAttachment, HTMLBody, Mailbox, Message

logger = logging.getLogger('auto_responsible.exchange_sender')


def split_recipients(value: str | None) -> list[Mailbox]:
    if not value:
        return []

    result = []

    for item in value.replace(',', ';').split(';'):
        email = item.strip()

        if email:
            result.append(
                Mailbox(email_address=email)
            )

    return result


def send_html_email(
    account,
    to: str,
    subject: str,
    html_body: str,
    attachments: list[Path] | None = None,
    cc: str | None = None,
) -> None:
    attachments = attachments or []

    to_recipients = split_recipients(to)
    cc_recipients = split_recipients(cc)

    if not to_recipients:
        raise ValueError(
            f'Не указаны получатели письма. subject={subject}'
        )

    message = Message(
        account=account,
        folder=account.sent,
        subject=subject,
        body=HTMLBody(html_body),
        to_recipients=to_recipients,
        cc_recipients=cc_recipients,
    )

    for file_path in attachments:
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(
                f'Вложение не найдено: {file_path}'
            )

        with open(file_path, 'rb') as file:
            content = file.read()

        message.attach(
            FileAttachment(
                name=file_path.name,
                content=content,
            )
        )

    message.send_and_save()

    logger.info(
        'EWS письмо отправлено: to=%s | cc=%s | subject=%s | attachments=%s',
        to,
        cc,
        subject,
        len(attachments),
    )