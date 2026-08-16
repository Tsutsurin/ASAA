import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

TEMP_DIR = BASE_DIR / 'temp'
LOGS_DIR = BASE_DIR / 'logs'


@dataclass
class EwsSettings:
    enabled: bool
    service_endpoint: str
    username: str
    password_env: str
    password: str
    email: str
    auth_type: str
    verify_ssl: bool


@dataclass
class ApiSettings:
    enabled: bool
    base_url: str
    verify_ssl: bool
    timeout: int


@dataclass
class SendEmailSettings:
    enabled: bool
    to: str
    cc: str | None
    subject: str
    body: str


@dataclass
class RecipientFilterSettings:
    enabled: bool
    ldap_server: str
    ldap_user: str
    ldap_password_env: str
    ldap_password: str
    search_base: str
    max_recipients: int
    fallback_to: str
    fallback_cc: str | None
    allowed_titles: list[str]
    blacklist_file: str | None


@dataclass
class ServiceRoutingSettings:
    enabled: bool
    file: str


@dataclass
class DispatchSettings:
    enabled: bool
    template_path: str
    no_group_template_path: str
    service_template_path: str
    to: str
    cc: str | None
    no_group_to: str
    no_group_cc: str | None
    subject: str
    no_group_subject: str
    output_dir: str
    network_tasks_dir: str
    registry_file: str
    registry_columns: dict[str, str]
    group_column: str
    ip_column: str
    fqdn_column: str
    vulnerability_column: str
    placeholder: str
    status_value: str
    max_emails_per_run: int
    pause_between_emails_seconds: int
    recipient_filter: RecipientFilterSettings
    service_routing: ServiceRoutingSettings
    attachment_drop_columns: list[str]


@dataclass
class SearchDirectorySettings:
    enabled: bool
    input_dir: str
    output_dir: str
    archive_dir: str | None
    delete_after_processing: bool


@dataclass
class DispatchDirectorySettings:
    enabled: bool
    input_dir: str
    archive_dir: str | None
    delete_after_processing: bool
    error_dir: str | None


@dataclass
class Settings:
    subject_contains: str | None
    only_unread: bool
    ews: EwsSettings
    api: ApiSettings
    send_email: SendEmailSettings
    dispatch: DispatchSettings
    search_directory: SearchDirectorySettings
    dispatch_directory: DispatchDirectorySettings
    backend_mapping_file: str | None


def load_settings(path: str | Path | None = None) -> Settings:
    if path is None:
        path = BASE_DIR / 'settings.json'

    with open(path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    ews = data['ews']
    api = data['api']
    send_email = data['send_email']
    dispatch = data['dispatch']
    search_directory = data.get('search_directory', {})
    dispatch_directory = data.get('dispatch_directory', {})
    recipient_filter = dispatch.get('recipient_filter', {})
    service_routing = dispatch.get('service_routing', {})

    password_env = ews['password_env']
    password = os.environ.get(password_env)

    if not password:
        raise ValueError(
            f'Не найдена переменная окружения с паролем: {password_env}'
        )

    ldap_password_env = recipient_filter.get(
        'ldap_password_env',
        'VOC_PASSWORD',
    )
    ldap_password = os.environ.get(ldap_password_env, '')

    return Settings(
        subject_contains=data.get('subject_contains'),
        only_unread=data.get('only_unread', True),

        ews=EwsSettings(
            enabled=ews['enabled'],
            service_endpoint=ews['service_endpoint'],
            username=ews['username'],
            password_env=password_env,
            password=password,
            email=ews['email'],
            auth_type=ews.get('auth_type', 'NTLM'),
            verify_ssl=ews.get('verify_ssl', True),
        ),

        api=ApiSettings(
            enabled=api['enabled'],
            base_url=api['base_url'],
            verify_ssl=api['verify_ssl'],
            timeout=api['timeout'],
        ),

        send_email=SendEmailSettings(
            enabled=send_email['enabled'],
            to=send_email.get('to', ''),
            cc=send_email.get('cc'),
            subject=send_email['subject'],
            body=send_email['body'],
        ),

        dispatch=DispatchSettings(
            enabled=dispatch['enabled'],
            template_path=dispatch['template_path'],
            no_group_template_path=dispatch['no_group_template_path'],
            service_template_path=dispatch['service_template_path'],
            to=dispatch['to'],
            cc=dispatch.get('cc'),
            no_group_to=dispatch['no_group_to'],
            no_group_cc=dispatch.get('no_group_cc'),
            subject=dispatch['subject'],
            no_group_subject=dispatch['no_group_subject'],
            output_dir=dispatch['output_dir'],
            network_tasks_dir=dispatch['network_tasks_dir'],
            registry_file=dispatch['registry_file'],
            registry_columns=dispatch['registry_columns'],
            group_column=dispatch['group_column'],
            ip_column=dispatch.get('ip_column', 'IP-адрес'),
            fqdn_column=dispatch.get('fqdn_column', 'Доменное имя'),
            vulnerability_column=dispatch.get(
                'vulnerability_column',
                'Идентификатор уязвимости VM',
            ),
            placeholder=dispatch.get('placeholder', 'text'),
            status_value=dispatch.get('status_value', 'Направлено'),
            max_emails_per_run=dispatch.get('max_emails_per_run', 0),
            pause_between_emails_seconds=dispatch.get(
                'pause_between_emails_seconds',
                2,
            ),
            recipient_filter=RecipientFilterSettings(
                enabled=recipient_filter.get('enabled', False),
                ldap_server=recipient_filter.get('ldap_server', ''),
                ldap_user=recipient_filter.get('ldap_user', ews['username']),
                ldap_password_env=ldap_password_env,
                ldap_password=ldap_password,
                search_base=recipient_filter.get('search_base', ''),
                max_recipients=recipient_filter.get('max_recipients', 10),
                fallback_to=recipient_filter.get(
                    'fallback_to',
                    dispatch.get('to', ''),
                ),
                fallback_cc=recipient_filter.get('fallback_cc'),
                allowed_titles=recipient_filter.get(
                    'allowed_titles',
                    [],
                ),
                blacklist_file=recipient_filter.get('blacklist_file'),
            ),
            service_routing=ServiceRoutingSettings(
                enabled=service_routing.get('enabled', False),
                file=service_routing.get('file', 'service_routing.json'),
            ),
            attachment_drop_columns=dispatch.get(
                'attachment_drop_columns',
                [],
            ),
        ),

        search_directory=SearchDirectorySettings(
            enabled=search_directory.get('enabled', False),
            input_dir=search_directory.get('input_dir', ''),
            output_dir=search_directory.get('output_dir', ''),
            archive_dir=search_directory.get('archive_dir'),
            delete_after_processing=search_directory.get(
                'delete_after_processing',
                False,
            ),
        ),

        dispatch_directory=DispatchDirectorySettings(
            enabled=dispatch_directory.get('enabled', False),
            input_dir=dispatch_directory.get('input_dir', ''),
            archive_dir=dispatch_directory.get('archive_dir'),
            error_dir=dispatch_directory.get('error_dir'),
            delete_after_processing=dispatch_directory.get(
                'delete_after_processing',
                False,
            ),
        ),
        backend_mapping_file=data.get('backend_mapping_file'),
    )


def load_columns(path: str | Path | None = None) -> dict[str, list[str]]:
    if path is None:
        path = BASE_DIR / 'columns.json'

    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file)